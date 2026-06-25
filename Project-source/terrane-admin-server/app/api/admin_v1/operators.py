"""Admin operators (System Users) management API (admin DB terrane_admin: users).

Mounted at /admin-api/v1/operators. Permission platform.user.* (the registry explicitly labels this "admin operator management"; super_admin writes, admin reads only).
List / create / edit (role, status) / reset password / delete admin accounts. Audit records land in terrane_main (cross-DB orchestration with the business data).
Safety guardrails: you cannot disable/demote/delete yourself; you cannot delete/disable/demote the last active super_admin (prevents self-lockout).
"""

from __future__ import annotations

import uuid
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, audit_ctx, get_db_session
from app.core import security
from app.core.errors import BizError
from app.db.platform import get_platform_db
from app.models.user import ROLES, User
from app.permissions.deps import require_perm
from app.permissions.registry import P
from app.services import audit_service
from app.services.platform_settings import get_security_policy
from app.services.session_service import SessionService

log = structlog.get_logger("terrane.admin.operators")

router = APIRouter(prefix="/admin-api/v1/operators", tags=["operators"])

RoleLit = Literal["super_admin", "admin", "auditor"]


def _out(u: User) -> dict:
    return {
        "id": str(u.id),
        "email": u.email,
        "username": u.username,
        "role": u.role,
        "status": "active" if u.is_active else "disabled",
        "twofa_enabled": u.twofa_enabled,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    }


async def _active_super_admins(db: AsyncSession) -> int:
    return int((await db.execute(select(func.count()).select_from(User).where(
        User.role == "super_admin", User.is_active.is_(True)))).scalar_one())


def _operator_uuid(operator_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(operator_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "operator"})


async def _get(db: AsyncSession, operator_id: str) -> User:
    u = await db.get(User, _operator_uuid(operator_id))
    if u is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "operator"})
    return u


class CreateOperatorIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    email: EmailStr
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(default="", max_length=256)  # leave blank = auto-generate a strong password (forced change on first login)
    role: RoleLit = "admin"


@router.get("")
async def list_operators(
    _=Depends(require_perm(P.USER_READ)),
    q: str | None = Query(default=None, description="Fuzzy search by email/username"),
    status: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    conds = []
    if q:
        like = f"%{q}%"
        conds.append(or_(User.email.ilike(like), User.username.ilike(like)))
    if status == "active":
        conds.append(User.is_active.is_(True))
    elif status == "disabled":
        conds.append(User.is_active.is_(False))

    total = int((await db.execute(
        select(func.count()).select_from(User).where(*conds))).scalar_one())
    rows = (await db.execute(
        select(User).where(*conds).order_by(User.created_at.desc())
        .limit(page_size).offset((page - 1) * page_size))).scalars().all()
    return {"items": [_out(u) for u in rows], "total": total, "page": page, "page_size": page_size}


@router.post("", status_code=201)
async def create_operator(
    body: CreateOperatorIn, request: Request,
    user: CurrentUser = Depends(require_perm(P.USER_WRITE)),
    db: AsyncSession = Depends(get_db_session),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    """Create an admin operator. Blank password = auto-generate a strong password, returned once + forced change on first login."""
    if body.role not in ROLES:
        raise BizError("VALIDATION_FAILED", {"reason": "role"})
    email = str(body.email).lower()
    if int((await db.execute(select(func.count()).select_from(User)
                             .where(func.lower(User.email) == email))).scalar_one()) > 0:
        raise BizError("AUTH_EMAIL_TAKEN")

    generated: str | None = None
    if body.password:
        pol = await get_security_policy(pdb)
        security.validate_password_policy(
            body.password, min_length=pol["password_min_length"], email=email,
            username=body.username, require_char_classes=pol["password_require_char_classes"],
            forbid_identity=True)
        pw, must_change = body.password, False
    else:
        pw = generated = security.new_token(9)
        must_change = True  # auto-generated -> force password change on first login

    op = User(email=email, username=body.username, role=body.role,
              password_hash=security.hash_password(pw), is_active=True,
              must_change_password=must_change)
    db.add(op)
    await db.flush()
    await audit_service.record(
        pdb, action="operator.create", actor_id=user.user_id, actor_name=user.name,
        target_type="operator", target_id=str(op.id),
        after={"email": email, "role": body.role}, **audit_ctx(request))
    await db.commit()
    await pdb.commit()
    log.info("operator_created", operator_id=str(op.id), actor_id=user.user_id)
    return {"id": str(op.id), "email": email, "generated_password": generated}


class UpdateOperatorIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    username: str | None = Field(default=None, max_length=64)
    role: RoleLit | None = None
    status: Literal["active", "disabled"] | None = None


@router.patch("/{operator_id}")
async def update_operator(
    body: UpdateOperatorIn, operator_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.USER_WRITE)),
    db: AsyncSession = Depends(get_db_session),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    op = await _get(db, operator_id)
    is_self = str(op.id) == user.user_id
    demoting = body.role is not None and op.role == "super_admin" and body.role != "super_admin"
    disabling = body.status == "disabled" and op.is_active

    if is_self and (demoting or disabling):
        raise BizError("OPERATOR_SELF_FORBIDDEN")
    # The last active super_admin cannot be demoted/disabled (prevents self-lockout).
    if (demoting or disabling) and op.role == "super_admin" and op.is_active \
            and await _active_super_admins(db) <= 1:
        raise BizError("OPERATOR_LAST_SUPER_ADMIN")

    before = {"username": op.username, "role": op.role, "status": "active" if op.is_active else "disabled"}
    if body.username is not None:
        op.username = body.username or op.username
    if body.role is not None:
        op.role = body.role
    if body.status is not None:
        op.is_active = body.status == "active"
    after = {"username": op.username, "role": op.role, "status": "active" if op.is_active else "disabled",
             "email": op.email}
    await audit_service.record(
        pdb, action="operator.update", actor_id=user.user_id, actor_name=user.name,
        target_type="operator", target_id=str(op.id), before=before, after=after, **audit_ctx(request))
    # Disable/demote -> kill all of this operator's sessions.
    if disabling or demoting:
        await SessionService().destroy_all_for_user(str(op.id))
    await db.commit()
    await pdb.commit()
    return {"id": str(op.id), **after}


@router.post("/{operator_id}/reset-password")
async def reset_operator_password(
    operator_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.USER_WRITE)),
    db: AsyncSession = Depends(get_db_session),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    """Reset an operator's password -> generate a new strong password, returned once + forced change on first login + kill all sessions."""
    op = await _get(db, operator_id)
    pw = security.new_token(9)
    op.password_hash = security.hash_password(pw)
    op.must_change_password = True
    await audit_service.record(
        pdb, action="operator.reset_password", actor_id=user.user_id, actor_name=user.name,
        target_type="operator", target_id=str(op.id), after={"email": op.email}, **audit_ctx(request))
    await SessionService().destroy_all_for_user(str(op.id))
    await db.commit()
    await pdb.commit()
    log.info("operator_password_reset", operator_id=str(op.id), actor_id=user.user_id)
    return {"generated_password": pw}


@router.delete("/{operator_id}")
async def delete_operator(
    operator_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.USER_DELETE)),
    db: AsyncSession = Depends(get_db_session),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    """Hard-delete an operator (iron rule: real deletion). Guardrails: cannot delete yourself / the last active super_admin."""
    op = await _get(db, operator_id)
    if str(op.id) == user.user_id:
        raise BizError("OPERATOR_SELF_FORBIDDEN")
    if op.role == "super_admin" and op.is_active and await _active_super_admins(db) <= 1:
        raise BizError("OPERATOR_LAST_SUPER_ADMIN")
    await audit_service.record(
        pdb, action="operator.delete", actor_id=user.user_id, actor_name=user.name,
        target_type="operator", target_id=str(op.id),
        before={"email": op.email, "role": op.role}, **audit_ctx(request))
    await SessionService().destroy_all_for_user(str(op.id))
    await db.delete(op)
    await db.commit()
    await pdb.commit()
    log.info("operator_deleted", operator_id=operator_id, actor_id=user.user_id)
    return {"ok": True}
