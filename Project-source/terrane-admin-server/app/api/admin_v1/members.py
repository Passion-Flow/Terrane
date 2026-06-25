"""Admin members (front-end knowledge-base users) listing API (platform DB terrane_main: users + workspaces + memberships).

Mounted at /admin-api/v1/members. Permission USER_READ (super_admin + admin). Page-number pagination + email/username search + status filter.
Read-only: lists registered users, their workspace, role, status, and last login. Sensitive columns (password_hash, etc.) are not exposed.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, EmailStr, Field
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, audit_ctx
from app.core import security
from app.core.config import get_settings
from app.core.errors import BizError
from app.db.platform import get_platform_db
from app.services.platform_settings import get_security_policy
from app.models.platform.front_user import FrontUser
from app.models.platform.membership import Membership
from app.models.platform.workspace import Workspace
from app.permissions.deps import require_perm
from app.permissions.registry import P
from app.services import audit_service

log = structlog.get_logger("terrane.admin.members")

router = APIRouter(prefix="/admin-api/v1", tags=["members"])

_STATUSES = {"active", "disabled", "pending"}
_ROLES = ("Owner", "Admin", "Editor", "Member", "Reader")


class CreateMemberIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    email: EmailStr
    username: str | None = Field(default=None, max_length=64)
    password: str = Field(default="", max_length=256)  # leave blank = auto-generate a strong password
    workspace_id: str
    role: Literal["Owner", "Admin", "Editor", "Member", "Reader"] = "Member"


@router.post("/members", status_code=201)
async def create_member(
    body: CreateMemberIn, request: Request,
    user: CurrentUser = Depends(require_perm(P.USER_WRITE)),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    """Admin creates a front-end user (trusted: directly active + email pre-verified, so they can log in without email verification).

    The selected workspace becomes their home + a membership(role) in that workspace. If the password is left blank, a strong password is auto-generated and returned once.
    """
    settings = get_settings()
    email = str(body.email).lower()
    if int((await db.execute(select(func.count()).select_from(FrontUser)
                             .where(func.lower(FrontUser.email) == email))).scalar_one()) > 0:
        raise BizError("AUTH_EMAIL_TAKEN")
    try:
        ws = await db.get(Workspace, uuid.UUID(body.workspace_id))
    except ValueError:
        ws = None
    if ws is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "workspace"})

    generated: str | None = None
    if body.password:
        pol = await get_security_policy(db)  # platform security policy (editable in admin "Settings -> Security")
        security.validate_password_policy(
            body.password, min_length=pol["password_min_length"], email=email,
            username=body.username or "",
            require_char_classes=pol["password_require_char_classes"], forbid_identity=True)
        pw = body.password
    else:
        pw = generated = security.new_token(9)  # url-safe, alphanumeric, sufficient for login

    now = datetime.datetime.now(datetime.timezone.utc)
    fu = FrontUser(workspace_id=ws.id, email=email, username=body.username,
                   password_hash=security.hash_password(pw), status="active",
                   email_verified_at=now)
    db.add(fu)
    await db.flush()
    db.add(Membership(workspace_id=ws.id, user_id=fu.id, role=body.role))
    await audit_service.record(
        db, action="user.create", actor_id=user.user_id, actor_name=user.name,
        target_type="user", target_id=str(fu.id),
        after={"email": email, "workspace": ws.name, "role": body.role}, **audit_ctx(request))
    await db.commit()
    log.info("member_created", user_id=str(fu.id), actor_id=user.user_id)
    return {"id": str(fu.id), "email": email, "generated_password": generated}


def _member_uuid(member_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(member_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "user"})


async def _get_member(db: AsyncSession, member_id: str) -> FrontUser:
    fu = await db.get(FrontUser, _member_uuid(member_id))
    if fu is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "user"})
    return fu


class UpdateMemberIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    username: str | None = Field(default=None, max_length=64)
    status: Literal["active", "disabled"] | None = None


@router.patch("/members/{member_id}")
async def update_member(
    body: UpdateMemberIn, member_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.USER_WRITE)),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    fu = await _get_member(db, member_id)
    before = {"username": fu.username, "status": fu.status}
    if body.username is not None:
        fu.username = body.username or None
    if body.status is not None:
        fu.status = body.status
    after = {"username": fu.username, "status": fu.status}
    await audit_service.record(
        db, action="user.update", actor_id=user.user_id, actor_name=user.name,
        target_type="user", target_id=str(fu.id),
        before={**before, "email": fu.email}, after={**after, "email": fu.email}, **audit_ctx(request))
    await db.commit()
    return {"id": str(fu.id), "username": fu.username, "status": fu.status}


@router.post("/members/{member_id}/reset-password")
async def reset_member_password(
    member_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.USER_WRITE)),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    """Admin resets a member's password -> generate a new strong password, returned once (the old password is invalidated immediately)."""
    fu = await _get_member(db, member_id)
    pw = security.new_token(9)
    fu.password_hash = security.hash_password(pw)
    await audit_service.record(
        db, action="user.reset_password", actor_id=user.user_id, actor_name=user.name,
        target_type="user", target_id=str(fu.id), after={"email": fu.email}, **audit_ctx(request))
    await db.commit()
    log.info("member_password_reset", user_id=str(fu.id), actor_id=user.user_id)
    return {"generated_password": pw}


@router.delete("/members/{member_id}")
async def delete_member(
    member_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.USER_DELETE)),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    """Hard-delete a member (iron rule: real deletion + FK cascade). A personal workspace is deleted along with them; for a team workspace only this member is removed."""
    fu = await _get_member(db, member_id)
    ws = await db.get(Workspace, fu.workspace_id)
    await audit_service.record(
        db, action="user.delete", actor_id=user.user_id, actor_name=user.name,
        target_type="user", target_id=str(fu.id),
        before={"email": fu.email, "workspace": ws.name if ws else None}, **audit_ctx(request))
    if ws is not None and ws.kind == "personal":
        await db.delete(ws)   # cascade-deletes user + membership
    else:
        await db.delete(fu)   # cascade-deletes membership
    await db.commit()
    log.info("member_deleted", user_id=member_id, actor_id=user.user_id)
    return {"ok": True}


@router.get("/members")
async def list_members(
    _=Depends(require_perm(P.USER_READ)),
    q: str | None = Query(default=None, description="Fuzzy search by email/username"),
    status: str | None = Query(default=None),
    workspace_id: str | None = Query(default=None, description="Members of this workspace only"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    conds = []
    if q:
        like = f"%{q}%"
        conds.append(or_(FrontUser.email.ilike(like), FrontUser.username.ilike(like)))
    if status in _STATUSES:
        conds.append(FrontUser.status == status)
    if workspace_id:
        try:
            conds.append(FrontUser.workspace_id == uuid.UUID(workspace_id))
        except ValueError:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

    total = int((await db.execute(
        select(func.count()).select_from(FrontUser).where(*conds))).scalar_one())

    # users + their workspace name + role in that workspace (the home workspace membership).
    stmt = (
        select(FrontUser, Workspace.name, Workspace.slug, Membership.role)
        .join(Workspace, Workspace.id == FrontUser.workspace_id)
        .outerjoin(Membership, and_(Membership.workspace_id == FrontUser.workspace_id,
                                    Membership.user_id == FrontUser.id))
        .where(*conds)
        .order_by(FrontUser.created_at.desc())
        .limit(page_size).offset((page - 1) * page_size)
    )
    rows = (await db.execute(stmt)).all()

    items = [{
        "id": str(u.id),
        "email": u.email,
        "username": u.username,
        "status": u.status,
        "workspace_id": str(u.workspace_id),
        "workspace_name": ws_name,
        "workspace_slug": ws_slug,
        "role": role or "Member",
        "twofa_enabled": u.twofa_enabled,
        "email_verified": u.email_verified_at is not None,
        "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
        "created_at": u.created_at.isoformat() if u.created_at else None,
    } for (u, ws_name, ws_slug, role) in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
