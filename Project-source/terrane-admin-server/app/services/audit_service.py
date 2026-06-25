"""Audit writes (platform database terrane_main: audit_logs, append-only).

All mutating admin operations are recorded to the audit log (02-database: append-only,
retained ≥1 year, metadata only with no content). before/after must be redacted (must never
contain plaintext keys/passwords). The caller is responsible for the commit (in the same
transaction as the business operation).
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.platform.audit_log import AuditLog


async def record(
    db: AsyncSession,
    *,
    action: str,
    actor_id: str | None,
    actor_name: str | None = None,
    actor_type: str = "admin",
    target_type: str | None = None,
    target_id: str | None = None,
    before: dict[str, Any] | None = None,
    after: dict[str, Any] | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    request_id: str | None = None,
) -> None:
    db.add(AuditLog(
        action=action,
        actor_type=actor_type,
        actor_id=uuid.UUID(actor_id) if actor_id else None,
        actor_name=actor_name,
        target_type=target_type,
        target_id=target_id,
        before=before,
        after=after,
        ip=ip,
        user_agent=(user_agent or "")[:512] or None,
        request_id=request_id,
    ))
