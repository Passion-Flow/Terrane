"""AuditLog (audit log, append-only) ORM — platform DB terrane_main (02-database entity #33).

Compliance HARD RULE: append-only (REVOKE UPDATE, DELETE at the migration layer; one of the only
two exceptions to the hard-delete rule). Monthly RANGE partitioning (PG); composite primary key
(id, created_at) (the partition key must be part of the PK). No updated_at (immutable rows).
before/after are redacted JSON snapshots (never contain plaintext secrets/passwords/user content,
metadata only).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.db.base import Base, JSONType

ACTOR_TYPES = ("admin", "user", "system")


class AuditLog(Base):
    __tablename__ = "audit_logs"

    # Composite primary key (id, created_at): the partition key created_at must be part of the PK (PG partitioning rule).
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    # Platform-level events have no workspace → NULL.
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
