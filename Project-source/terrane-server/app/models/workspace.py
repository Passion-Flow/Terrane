"""Workspace（租户：个人 WS / 团队 WS）ORM — 平台库 terrane_main（02-database 实体 #1）。

硬删除铁律：无 deleted_at；删除 = 真删 + FK 级联（业务表 workspace_id ON DELETE CASCADE）。
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, HardTimestampMixin, UUIDMixin

KINDS = ("personal", "team")
STATUSES = ("active", "suspended")


class Workspace(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "workspaces"

    slug: Mapped[str] = mapped_column(String(64), nullable=False)  # UNIQUE（迁移层）
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="personal")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
