"""后台工作区列表 API（平台库 terrane_main：workspaces + memberships 计数）。

挂 /admin-api/v1/workspaces。权限 WORKSPACE_READ（super_admin + admin）。页码分页 + 名称/slug 搜索。
"""

from __future__ import annotations

import secrets
import uuid
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, Path, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, audit_ctx
from app.core.errors import BizError
from app.db.platform import get_platform_db
from app.models.platform.membership import Membership
from app.models.platform.workspace import Workspace
from app.permissions.deps import require_perm
from app.permissions.registry import P
from app.services import audit_service

log = structlog.get_logger("terrane.admin.workspaces")

router = APIRouter(prefix="/admin-api/v1", tags=["workspaces"])


def _slug(name: str) -> str:
    base = "".join(c if c.isalnum() else "-" for c in name.lower()).strip("-")[:40] or "ws"
    return f"{base}-{secrets.token_hex(3)}"


class CreateWorkspaceIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str = Field(min_length=1, max_length=255)
    kind: Literal["personal", "team"] = "team"


@router.post("/workspaces", status_code=201)
async def create_workspace(
    body: CreateWorkspaceIn, request: Request,
    user: CurrentUser = Depends(require_perm(P.WORKSPACE_WRITE)),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    ws = Workspace(slug=_slug(body.name), name=body.name, kind=body.kind, status="active")
    db.add(ws)
    await db.flush()
    await audit_service.record(
        db, action="workspace.create", actor_id=user.user_id, actor_name=user.name,
        target_type="workspace", target_id=str(ws.id),
        after={"name": body.name, "kind": body.kind, "slug": ws.slug}, **audit_ctx(request))
    await db.commit()
    log.info("workspace_created", workspace_id=str(ws.id), actor_id=user.user_id)
    return {"id": str(ws.id), "slug": ws.slug, "name": ws.name, "kind": ws.kind,
            "status": ws.status, "member_count": 0,
            "created_at": ws.created_at.isoformat() if ws.created_at else None}


async def _get_ws(db: AsyncSession, ws_id: str) -> Workspace:
    try:
        ws = await db.get(Workspace, uuid.UUID(ws_id))
    except ValueError:
        ws = None
    if ws is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "workspace"})
    return ws


class UpdateWorkspaceIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str | None = Field(default=None, min_length=1, max_length=255)
    status: Literal["active", "suspended"] | None = None


@router.patch("/workspaces/{ws_id}")
async def update_workspace(
    body: UpdateWorkspaceIn, ws_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.WORKSPACE_WRITE)),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    ws = await _get_ws(db, ws_id)
    before = {"name": ws.name, "status": ws.status}
    if body.name is not None:
        ws.name = body.name
    if body.status is not None:
        ws.status = body.status
    await audit_service.record(
        db, action="workspace.update", actor_id=user.user_id, actor_name=user.name,
        target_type="workspace", target_id=str(ws.id),
        before=before, after={"name": ws.name, "status": ws.status}, **audit_ctx(request))
    await db.commit()
    return {"id": str(ws.id), "name": ws.name, "status": ws.status}


@router.delete("/workspaces/{ws_id}")
async def delete_workspace(
    ws_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.WORKSPACE_WRITE)),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    """硬删除工作区（铁律：真删 + FK 级联，连带删除其下用户/成员）。"""
    ws = await _get_ws(db, ws_id)
    await audit_service.record(
        db, action="workspace.delete", actor_id=user.user_id, actor_name=user.name,
        target_type="workspace", target_id=str(ws.id),
        before={"name": ws.name, "kind": ws.kind}, **audit_ctx(request))
    await db.delete(ws)  # 级联删 users + memberships（ON DELETE CASCADE）
    await db.commit()
    log.info("workspace_deleted", workspace_id=ws_id, actor_id=user.user_id)
    return {"ok": True}


@router.get("/workspaces")
async def list_workspaces(
    _=Depends(require_perm(P.WORKSPACE_READ)),
    q: str | None = Query(default=None, description="按名称/slug 模糊搜索"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    conds = []
    if q:
        like = f"%{q}%"
        conds.append(or_(Workspace.name.ilike(like), Workspace.slug.ilike(like)))

    total = int((await db.execute(
        select(func.count()).select_from(Workspace).where(*conds))).scalar_one())
    rows = (await db.execute(
        select(Workspace).where(*conds)
        .order_by(Workspace.created_at.desc())
        .limit(page_size).offset((page - 1) * page_size))).scalars().all()

    # 当前页工作区的成员计数（一次聚合查询）。
    ws_ids = [w.id for w in rows]
    counts: dict = {}
    if ws_ids:
        cres = await db.execute(
            select(Membership.workspace_id, func.count(Membership.id))
            .where(Membership.workspace_id.in_(ws_ids))
            .group_by(Membership.workspace_id))
        counts = {wid: int(n) for wid, n in cres.all()}

    items = [{
        "id": str(w.id), "slug": w.slug, "name": w.name, "kind": w.kind, "status": w.status,
        "member_count": counts.get(w.id, 0),
        "created_at": w.created_at.isoformat() if w.created_at else None,
    } for w in rows]
    return {"items": items, "total": total, "page": page, "page_size": page_size}
