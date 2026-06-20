"""Workspace（平台库 terrane_main：workspaces）— ORM 映射拷贝（admin 只读管理）。

schema 权威在 terrane-server/app/models/workspace.py + 迁移 000001。
"""

from __future__ import annotations

import uuid

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.platform import PlatformBase, PlatformTimestampMixin


class Workspace(PlatformTimestampMixin, PlatformBase):
    __tablename__ = "workspaces"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="personal")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
