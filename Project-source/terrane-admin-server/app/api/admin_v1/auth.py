"""Admin auth API — login / logout / me (ported from Forge auth.py + me.py, mounted at /admin-api/v1).

Auditing: stage 2 logs login success/failure via structlog for now (TODO stage 3: write to the audit_logs table in the same transaction).
"""

from __future__ import annotations

import datetime
import uuid

import structlog
from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.core.config import get_settings
from app.core.errors import BizError
from app.db.platform import get_platform_db
from app.repositories.user import UserRepository
from app.schemas.auth import ChangePasswordRequest, LoginRequest, MeOut
from app.services.auth_service import AuthService
from app.services.platform_settings import get_security_policy
from app.services.ratelimit import RateLimiter
from app.services.session_service import SessionService

log = structlog.get_logger("terrane.admin.auth")

router = APIRouter(prefix="/admin-api/v1", tags=["auth"])


def _set_session_cookie(response: Response, sid: str) -> None:
    s = get_settings()
    response.set_cookie(
        key=s.session_cookie_name, value=sid, httponly=True, secure=s.session_cookie_secure,
        samesite=s.session_cookie_samesite, max_age=s.session_absolute_ttl_seconds, path="/",
    )


@router.post("/auth/login")
async def login(body: LoginRequest, request: Request, response: Response,
                db: AsyncSession = Depends(get_db_session),
                pdb: AsyncSession = Depends(get_platform_db)) -> MeOut:
    auth = AuthService(db)
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")
    request_id = getattr(request.state, "request_id", "")
    pol = await get_security_policy(pdb)  # platform security policy (editable in admin "Settings -> Security")
    await RateLimiter().hit(f"login_ip:{ip}", limit=get_settings().login_max_per_ip_per_min,
                            window=60, code="RATE_LIMIT_LOGIN_BLOCKED")
    try:
        user = await auth.authenticate(body.email, body.password, body.code,
                                       lock_threshold=pol["login_lock_threshold"],
                                       lock_seconds=pol["login_lock_seconds"])
    except Exception as exc:
        # TODO stage 3: write the audit record to the audit_logs table (same transaction). For now, log structured events.
        log.warning("login_failure", actor_name=body.email,
                    reason=getattr(exc, "code", "AUTH_INVALID_CREDENTIALS"),
                    ip=ip, request_id=request_id)
        raise
    user.last_login_at = datetime.datetime.now(datetime.timezone.utc)
    perms = auth.permissions_for(user)
    sid = await SessionService().create(user_id=str(user.id), role=user.role, ip=ip or "", ua=ua,
                                        twofa_verified=user.twofa_enabled, permissions=perms,
                                        name=user.username or user.email,
                                        absolute_ttl_seconds=pol["session_absolute_ttl_seconds"])
    log.info("login_success", actor_id=str(user.id), actor_name=user.username,
             ip=ip, request_id=request_id)
    await db.commit()
    _set_session_cookie(response, sid)
    return MeOut(id=str(user.id), email=user.email, username=user.username, role=user.role,
                 avatar=user.avatar, twofa_enabled=user.twofa_enabled,
                 must_change_password=user.must_change_password, permissions=perms)


@router.post("/auth/logout")
async def logout(request: Request, response: Response,
                 user: CurrentUser = Depends(get_current_user)) -> dict:
    sid = request.cookies.get(get_settings().session_cookie_name)
    if sid:
        await SessionService().destroy(sid)
    response.delete_cookie(get_settings().session_cookie_name, path="/")
    return {"data": {"ok": True}, "request_id": getattr(request.state, "request_id", "")}


@router.get("/me")
async def me(user: CurrentUser = Depends(get_current_user),
             db: AsyncSession = Depends(get_db_session)) -> MeOut:
    db_user = await UserRepository(db).get(uuid.UUID(user.user_id))
    if not db_user:
        raise BizError("AUTH_REQUIRED")
    return MeOut(id=str(db_user.id), email=db_user.email, username=db_user.username,
                 role=db_user.role, avatar=db_user.avatar, twofa_enabled=db_user.twofa_enabled,
                 must_change_password=db_user.must_change_password, permissions=user.permissions)


@router.post("/auth/change-password")
async def change_password(body: ChangePasswordRequest, request: Request, response: Response,
                          user: CurrentUser = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db_session),
                          pdb: AsyncSession = Depends(get_platform_db)) -> MeOut:
    """Change password (also the entry point for forced first-login password change): verify old password -> policy check -> persist -> kill all old sessions and issue a new one.

    Session rotation (destroy_all + new sid) defends against session-fixation after a password change; the current request gets a fresh cookie, so no re-login is needed.
    """
    auth = AuthService(db)
    db_user = await UserRepository(db).get(uuid.UUID(user.user_id))
    if not db_user:
        raise BizError("AUTH_REQUIRED")
    pol = await get_security_policy(pdb)  # platform security policy (editable in admin "Settings -> Security")
    await auth.change_password(db_user, body.current_password, body.new_password,
                              min_length=pol["password_min_length"],
                              require_char_classes=pol["password_require_char_classes"])
    await db.commit()
    ip = request.client.host if request.client else None
    ua = request.headers.get("user-agent", "")
    perms = auth.permissions_for(db_user)
    sessions = SessionService()
    await sessions.destroy_all_for_user(str(db_user.id))  # kill all old sessions (including the current one)
    sid = await sessions.create(user_id=str(db_user.id), role=db_user.role, ip=ip or "", ua=ua,
                                twofa_verified=db_user.twofa_enabled, permissions=perms,
                                name=db_user.username or db_user.email,
                                absolute_ttl_seconds=pol["session_absolute_ttl_seconds"])
    log.info("password_changed", actor_id=str(db_user.id), actor_name=db_user.username,
             ip=ip, request_id=getattr(request.state, "request_id", ""))
    _set_session_cookie(response, sid)
    return MeOut(id=str(db_user.id), email=db_user.email, username=db_user.username,
                 role=db_user.role, avatar=db_user.avatar, twofa_enabled=db_user.twofa_enabled,
                 must_change_password=db_user.must_change_password, permissions=perms)
