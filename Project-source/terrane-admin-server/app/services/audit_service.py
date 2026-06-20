"""审计写入（平台库 terrane_main：audit_logs，append-only）。

后台所有变更类操作落审计（02-database：append-only ≥1 年，仅元数据不含内容）。
before/after 必须脱敏（绝不含明文密钥/密码）。写入由调用方 commit（与业务同事务）。
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
