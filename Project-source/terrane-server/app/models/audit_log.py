"""AuditLog（审计日志，append-only）ORM — 平台库 terrane_main（02-database 实体 #33）。

合规 HARD RULE：append-only（迁移层 REVOKE UPDATE,DELETE；硬删除铁律的唯二例外之一）。
按月 RANGE 分区（PG）；复合主键 (id, created_at)（分区键必入 PK）。无 updated_at（不可变行）。
before/after 为脱敏 JSON 快照（绝不含明文密钥/密码/用户内容，仅元数据）。
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

    # 复合主键 (id, created_at)：分区键 created_at 必入 PK（PG 分区规则）。
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    # 平台级事件无 workspace → NULL。
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
