"""AuditLog（平台库 terrane_main：audit_logs，append-only 分区）— ORM 映射拷贝。

schema 权威在 terrane-server/app/models/audit_log.py + 迁移 000002（按月 RANGE 分区 + append-only
触发器）。admin 仅 INSERT（写审计）/ SELECT（审计查询页）；UPDATE/DELETE 被 DB 触发器一律拒绝。
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
