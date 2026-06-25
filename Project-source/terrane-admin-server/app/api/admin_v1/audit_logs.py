"""Admin audit log query API — reads audit_logs (platform DB terrane_main), page-based pagination. Mounted at /admin-api/v1.

Platform role: require_perm(P.AUDIT_READ) (super_admin + auditor). The audit table is append-only; this endpoint is read-only.
Filters: actor (actor_id) / action (prefix or exact) / target_type / from / to (created_at range).
Pagination: page (1-based) + page_size; returns items + total (for the paginated UI to show "X-Y / Z total").
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
    """Human-readable name of the target (audit is append-only: use the write-time snapshot, so it survives hard-deleted objects).

    user -> email; workspace -> name. The snapshot lives in after (create/update) or before (delete).
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
        # Trailing dot -> prefix match (e.g. 'wizard.' matches wizard.email.configure/wizard.complete).
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
