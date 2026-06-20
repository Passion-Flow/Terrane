"""后台审计日志查询 API — 读 audit_logs（平台库 terrane_main），页码分页。挂 /admin-api/v1。

平台角色：require_perm(P.AUDIT_READ)（super_admin + auditor）。审计表 append-only，本端点只读。
过滤：actor（actor_id）/ action（前缀或精确）/ target_type / from / to（created_at 区间）。
分页：page（1 起）+ page_size；返回 items + total（供页码分页 UI 显示「X–Y / 共 Z 条」）。
"""

from __future__ import annotations

import datetime
import uuid

import structlog
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.platform import get_platform_db
from app.models.platform.audit_log import AuditLog
from app.permissions.deps import require_perm
from app.permissions.registry import P

log = structlog.get_logger("terrane.admin.audit")

router = APIRouter(prefix="/admin-api/v1", tags=["audit-logs"])


def _parse_dt(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _target_name(r: AuditLog) -> str | None:
    """目标的可读名（审计 append-only：取写入时快照，兼容硬删除后的对象）。

    user → 邮箱；workspace → 名称。快照存于 after（创建/改）或 before（删除）。
    """
    snap = r.after or r.before or {}
    if r.target_type == "user":
        return snap.get("email")
    if r.target_type == "workspace":
        return snap.get("name")
    return snap.get("name") or snap.get("email")


def _row_out(r: AuditLog) -> dict:
    return {
        "id": str(r.id),
        "workspace_id": str(r.workspace_id) if r.workspace_id else None,
        "actor_type": r.actor_type,
        "actor_id": str(r.actor_id) if r.actor_id else None,
        "actor_name": r.actor_name,
        "action": r.action,
        "target_type": r.target_type,
        "target_id": r.target_id,
        "target_name": _target_name(r),
        "before": r.before,
        "after": r.after,
        "ip": r.ip,
        "user_agent": r.user_agent,
        "request_id": r.request_id,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


@router.get("/audit-logs")
async def list_audit_logs(
    _=Depends(require_perm(P.AUDIT_READ)),
    actor: str | None = Query(default=None, description="actor_id (UUID)"),
    action: str | None = Query(default=None, description="exact action or prefix ending with '.'"),
    target_type: str | None = Query(default=None),
    from_: str | None = Query(default=None, alias="from"),
    to: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: AsyncSession = Depends(get_platform_db),
) -> dict:
    conds = []
    if actor:
        try:
            conds.append(AuditLog.actor_id == uuid.UUID(actor))
        except ValueError:
            return {"items": [], "total": 0, "page": page, "page_size": page_size}
    if action:
        # 末尾点 → 前缀匹配（如 'wizard.' 命中 wizard.email.configure/wizard.complete）。
        conds.append(AuditLog.action.like(f"{action}%") if action.endswith(".")
                     else AuditLog.action == action)
    if target_type:
        conds.append(AuditLog.target_type == target_type)
    dt_from = _parse_dt(from_)
    dt_to = _parse_dt(to)
    if dt_from:
        conds.append(AuditLog.created_at >= dt_from)
    if dt_to:
        conds.append(AuditLog.created_at <= dt_to)

    total = int((await db.execute(
        select(func.count()).select_from(AuditLog).where(*conds))).scalar_one())

    stmt = (select(AuditLog).where(*conds)
            .order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .limit(page_size).offset((page - 1) * page_size))
    rows = (await db.execute(stmt)).scalars().all()
    return {"items": [_row_out(r) for r in rows], "total": total,
            "page": page, "page_size": page_size}
