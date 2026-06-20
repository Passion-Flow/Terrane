"""Membership（用户 × Workspace × 角色）ORM — 平台库 terrane_main（02-database 实体 #3）。

(workspace_id,user_id) UNIQUE；硬删级联自 user/workspace。WS 角色见 ROLES（02-database §8）。
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, HardTimestampMixin, UUIDMixin

ROLES = ("Owner", "Admin", "Editor", "Member", "Reader")


class Membership(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "memberships"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="Member")
