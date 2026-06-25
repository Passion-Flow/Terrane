"""AuditLog (platform DB terrane_main: audit_logs, append-only partitioned) — ORM mapping copy.

The authoritative schema lives in terrane-server/app/models/audit_log.py + migration 000002
(monthly RANGE partitions + append-only trigger). admin only performs INSERT (write audit) /
SELECT (audit query page); UPDATE/DELETE are unconditionally rejected by the DB trigger.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.platform import JSONType, PlatformBase

ACTOR_TYPES = ("admin", "user", "system")


class AuditLog(PlatformBase):
    __tablename__ = "audit_logs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    actor_type: Mapped[str] = mapped_column(String(16), nullable=False)
    actor_id: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    actor_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(48), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    after: Mapped[dict | None] = mapped_column(JSONType, nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(512), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), primary_key=True, server_default=func.now(), nullable=False
    )
