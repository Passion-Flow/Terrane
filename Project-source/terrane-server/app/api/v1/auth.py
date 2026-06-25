"""Frontend auth API — register / login / logout / me / verify-email / reset / change-password.

Mounted at /api/v1/auth. Cookie sessions (HttpOnly terrane_session). Anti-enumeration: login and reset
requests do not reveal whether a user exists. Registration automatically creates a personal workspace +
Owner membership and sends an email-verification message (email verification is enforced by default).
"""

from __future__ import annotations

import uuid

import structlog
from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.core.config import get_settings
from app.core.errors import BizError
from app.models.membership import Membership
from app.models.user import User
from app.repositories.user import UserRepository
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    MeOut,
    RegisterOut,
    RegisterRequest,
    RequestResetRequest,
    ResetPasswordRequest,
    VerifyEmailRequest,
)
from app.services.auth_service import AuthService
from app.services.platform_settings import get_security_policy
from app.services.ratelimit import RateLimiter
from app.services.session_service import SessionService

log = structlog.get_logger("terrane.api.auth")

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


def _public_base_url(request: Request) -> str | None:
    """The frontend address used in email links. If FRONTEND_BASE_URL is explicitly set to a non-localhost value,
    use it (fixed production domain + Host-injection protection); otherwise follow this request's Host —— whatever
    IP/domain the deployment is accessed at, the email link uses that, no configuration needed."""
    cfg = (get_settings().frontend_base_url or "").rstrip("/")
    if cfg and "localhost" not in cfg and "127.0.0.1" not in cfg:
        return cfg
    host = request.headers.get("x-forwarded-host") or request.headers.get("host")
    if host:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "http"
        return f"{proto}://{host}"
    return cfg or None


def _set_session_cookie(response: Response, sid: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.session_cookie_name, value=sid, httponly=True, secure=s.session_cookie_secure,
        samesite=s.session_cookie_samesite, max_age=s.session_absolute_ttl_seconds, path="/")


async def _role_in(db: AsyncSession, workspace_id: uuid.UUID, user_id: uuid.UUID) -> str:
    stmt = select(Membership.role).where(
        Membership.workspace_id == workspace_id, Membership.user_id == user_id)
    return (await db.execute(stmt)).scalar_one_or_none() or "Member"


def _me(user: User, role: str) -> MeOut:
    return MeOut(id=str(user.id), email=user.email, username=user.username, avatar=user.avatar,
                 status=user.status, workspace_id=str(user.workspace_id), role=role,
                 twofa_enabled=user.twofa_enabled)


@router.post("/register", status_code=201)
async def register(body: RegisterRequest, request: Request,
                   db: AsyncSession = Depends(get_db_session)) -> RegisterOut:
    ip = request.client.host if request.client else None
    await RateLimiter().hit(f"register_ip:{ip}",
                            limit=get_settings().register_max_per_ip_per_hour, window=3600,
                            code="RATE_LIMIT_EXCEEDED")
    user = await AuthService(db).register(body.email, body.password, body.username,
                                          base_url=_public_base_url(request))
    log.info("user_registered", user_id=str(user.id), ip=ip)
    return RegisterOut(id=str(user.id), email=user.email, status=user.status)


@router.post("/verify-email")
async def verify_email(body: VerifyEmailRequest,
                       db: AsyncSession = Depends(get_db_session)) -> dict:
    await AuthService(db).verify_email(body.token)
    return {"data": {"ok": True}}


@router.post("/login")
async def login(body: LoginRequest, request: Request, response: Response,
                db: AsyncSession = Depends(get_db_session)) -> MeOut:
    auth = AuthService(db)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")
    await RateLimiter().hit(f"login_ip:{ip}", limit=get_settings().login_max_per_ip_per_min,
                            window=60, code="RATE_LIMIT_LOGIN_BLOCKED")
    user = await auth.authenticate(body.email, body.password, body.code)
    role = await _role_in(db, user.workspace_id, user.id)
    pol = await get_security_policy(db)  # Platform security policy (editable under admin "Settings → Security")
    sid = await SessionService().create(user_id=str(user.id), workspace_id=str(user.workspace_id),
                                        role=role, ip=ip or "", ua=ua,
                                        twofa_verified=user.twofa_enabled,
                                        absolute_ttl_seconds=pol["session_absolute_ttl_seconds"])
    log.info("login_success", user_id=str(user.id), ip=ip)
    _set_session_cookie(response, sid)
    return _me(user, role)


@router.post("/logout")
async def logout(request: Request, response: Response,
                 user: CurrentUser = Depends(get_current_user)) -> dict:
    sid = request.cookies.get(get_settings().session_cookie_name)
    if sid:
        await SessionService().destroy(sid)
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return {"data": {"ok": True}}


class _TwofaCode(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    code: str = Field(min_length=4, max_length=16)


async def _load_user(db: AsyncSession, user: CurrentUser) -> User:
    u = await db.get(User, uuid.UUID(user.user_id))
    if u is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "user"})
    return u


@router.post("/2fa/begin")
async def twofa_begin(user: CurrentUser = Depends(get_current_user),
                      db: AsyncSession = Depends(get_db_session)) -> dict:
    secret, uri = await AuthService(db).twofa_begin(await _load_user(db, user))
    return {"data": {"secret": secret, "uri": uri}}


@router.post("/2fa/enable")
async def twofa_enable(body: _TwofaCode, user: CurrentUser = Depends(get_current_user),
                       db: AsyncSession = Depends(get_db_session)) -> dict:
    backups = await AuthService(db).twofa_enable(await _load_user(db, user), body.code)
    return {"data": {"backup_codes": backups}}


@router.post("/2fa/disable")
async def twofa_disable(body: _TwofaCode, user: CurrentUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db_session)) -> dict:
    await AuthService(db).twofa_disable(await _load_user(db, user), body.code)
    return {"data": {"ok": True}}


class ProfileIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    username: str | None = Field(default=None, max_length=64)
    avatar: str | None = Field(default=None, max_length=3_000_000)  # base64 data URL; empty string = clear


@router.patch("/profile")
async def update_profile(body: ProfileIn, user: CurrentUser = Depends(get_current_user),
                         db: AsyncSession = Depends(get_db_session)) -> dict:
    u = await _load_user(db, user)
    if body.username is not None and body.username.strip():
        u.username = body.username.strip()
    if body.avatar is not None:
        u.avatar = body.avatar or None
    await db.commit()
    return {"data": {"ok": True}}


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user),
             db: AsyncSession = Depends(get_db_session)) -> MeOut:
    db_user = await UserRepository(db).get(uuid.UUID(user.user_id))
    if not db_user:
        raise BizError("AUTH_REQUIRED")
    return _me(db_user, user.role)


@router.post("/request-reset")
async def request_reset(body: RequestResetRequest, request: Request,
                        db: AsyncSession = Depends(get_db_session)) -> dict:
    ip = request.client.host if request.client else None
    await RateLimiter().hit(f"reset_ip:{ip}", limit=get_settings().login_max_per_ip_per_min,
                            window=60, code="RATE_LIMIT_EXCEEDED")
    await AuthService(db).request_reset(body.email,  # Anti-enumeration: always silently succeeds
                                        base_url=_public_base_url(request))
    return {"data": {"ok": True}}


@router.post("/reset-password")
async def reset_password(body: ResetPasswordRequest,
                         db: AsyncSession = Depends(get_db_session)) -> dict:
    user = await AuthService(db).reset_password(body.token, body.new_password)
    await SessionService().destroy_all_for_user(str(user.id))  # Kick all sessions after reset
    return {"data": {"ok": True}}


@router.post("/change-password")
async def change_password(body: ChangePasswordRequest, request: Request, response: Response,
                          user: CurrentUser = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db_session)) -> MeOut:
    db_user = await UserRepository(db).get(uuid.UUID(user.user_id))
    if not db_user:
        raise BizError("AUTH_REQUIRED")
    auth = AuthService(db)
    await auth.change_password(db_user, body.current_password, body.new_password)
    # Session rotation (anti-fixation): kick all old sessions + issue a new cookie.
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")
    role = await _role_in(db, db_user.workspace_id, db_user.id)
    pol = await get_security_policy(db)
    sessions = SessionService()
    await sessions.destroy_all_for_user(str(db_user.id))
    sid = await sessions.create(user_id=str(db_user.id), workspace_id=str(db_user.workspace_id),
                                role=role, ip=ip or "", ua=ua, twofa_verified=db_user.twofa_enabled,
                                absolute_ttl_seconds=pol["session_absolute_ttl_seconds"])
    _set_session_cookie(response, sid)
    return _me(db_user, role)
