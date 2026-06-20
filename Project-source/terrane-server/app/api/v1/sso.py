"""SSO（OIDC 授权码流)—— 前台企业登录。挂 /api/v1/auth/sso。

配置存 system_settings['sso']（admin 后台配,client_secret 经 KEK 加密)。
login → discovery → authorize 重定向;callback → 换 token → JWKS 验 id_token → 配置用户 → 建会话。
"""

from __future__ import annotations

import secrets
from urllib.parse import urlencode

import structlog
from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.config import get_settings
from app.core.errors import BizError
from app.models.membership import Membership
from app.services import crypto
from app.services.auth_service import AuthService
from app.services.platform_settings import get_setting
from app.services.session_service import SessionService
from sqlalchemy import select

log = structlog.get_logger("terrane.sso")
router = APIRouter(prefix="/api/v1/auth/sso", tags=["sso"])

SSO_KEY = "sso"


async def _discover(issuer: str) -> dict:
    import httpx
    url = issuer.rstrip("/") + "/.well-known/openid-configuration"
    async with httpx.AsyncClient(timeout=10.0) as c:
        r = await c.get(url)
    r.raise_for_status()
    return r.json()


def _redirect_uri() -> str:
    base = (get_settings().frontend_base_url or "").rstrip("/")
    # 回调走后端;前台与后端同源(网关/nginx 反代 /api)→ 用前台 origin
    return f"{base}/api/v1/auth/sso/callback"


@router.get("/status")
async def sso_status(db: AsyncSession = Depends(get_db_session)) -> dict:
    """公开:前台登录页据此决定是否显示「企业 SSO 登录」。"""
    cfg = await get_setting(db, SSO_KEY) or {}
    return {"data": {"enabled": bool(cfg.get("enabled") and cfg.get("issuer") and cfg.get("client_id")),
                     "label": cfg.get("label") or "企业 SSO"}}


@router.get("/login")
async def sso_login(db: AsyncSession = Depends(get_db_session)) -> RedirectResponse:
    cfg = await get_setting(db, SSO_KEY) or {}
    if not cfg.get("enabled"):
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "sso"})
    disc = await _discover(cfg["issuer"])
    state, nonce = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    params = {"response_type": "code", "client_id": cfg["client_id"],
              "redirect_uri": _redirect_uri(), "scope": cfg.get("scopes", "openid email profile"),
              "state": state, "nonce": nonce}
    resp = RedirectResponse(disc["authorization_endpoint"] + "?" + urlencode(params), status_code=302)
    resp.set_cookie("sso_state", state, httponly=True, max_age=600, path="/", samesite="lax")
    resp.set_cookie("sso_nonce", nonce, httponly=True, max_age=600, path="/", samesite="lax")
    return resp


@router.get("/callback")
async def sso_callback(request: Request, code: str = "", state: str = "",
                       db: AsyncSession = Depends(get_db_session)) -> RedirectResponse:
    s = get_settings()
    front = (s.frontend_base_url or "").rstrip("/")
    if not code or state != request.cookies.get("sso_state"):
        return RedirectResponse(f"{front}/login?sso_error=state", status_code=302)
    cfg = await get_setting(db, SSO_KEY) or {}
    disc = await _discover(cfg["issuer"])

    import httpx
    import jwt
    from jwt import PyJWKClient

    secret = crypto.decrypt(cfg.get("client_secret"))
    async with httpx.AsyncClient(timeout=10.0) as c:
        tok = await c.post(disc["token_endpoint"], data={
            "grant_type": "authorization_code", "code": code, "redirect_uri": _redirect_uri(),
            "client_id": cfg["client_id"], "client_secret": secret})
    if tok.status_code >= 400:
        log.warning("sso_token_failed", status=tok.status_code, body=tok.text[:200])
        return RedirectResponse(f"{front}/login?sso_error=token", status_code=302)
    id_token = tok.json().get("id_token")
    if not id_token:
        return RedirectResponse(f"{front}/login?sso_error=no_id_token", status_code=302)
    try:
        key = PyJWKClient(disc["jwks_uri"]).get_signing_key_from_jwt(id_token).key
        claims = jwt.decode(id_token, key, algorithms=["RS256"], audience=cfg["client_id"],
                            issuer=disc["issuer"], options={"verify_aud": True})
    except Exception as e:  # noqa: BLE001
        log.warning("sso_verify_failed", error=str(e))
        return RedirectResponse(f"{front}/login?sso_error=verify", status_code=302)

    email = claims.get("email") or f"{claims.get('sub', 'user')}@sso.local"
    name = claims.get("name") or claims.get("preferred_username")
    try:
        user = await AuthService(db).provision_sso_user(email, name)
    except BizError:
        return RedirectResponse(f"{front}/login?sso_error=account", status_code=302)

    role = (await db.execute(select(Membership.role).where(
        Membership.user_id == user.id, Membership.workspace_id == user.workspace_id))).scalar_one_or_none() or "Owner"
    pol = await get_setting(db, "security") or {}
    sid = await SessionService().create(
        user_id=str(user.id), workspace_id=str(user.workspace_id), role=role,
        ip=request.client.host if request.client else "", ua=request.headers.get("user-agent", ""),
        twofa_verified=True, absolute_ttl_seconds=pol.get("session_absolute_ttl_seconds"))
    resp = RedirectResponse(f"{front}/", status_code=302)
    resp.set_cookie(key=s.session_cookie_name, value=sid, httponly=True, secure=s.session_cookie_secure,
                    samesite=s.session_cookie_samesite, max_age=s.session_absolute_ttl_seconds, path="/")
    resp.delete_cookie("sso_state", path="/")
    resp.delete_cookie("sso_nonce", path="/")
    return resp
