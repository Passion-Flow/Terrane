"""Workspace (tenant: personal WS / team WS) ORM — platform DB terrane_main (02-database entity #1).

Hard-delete rule: no deleted_at; delete = real delete + FK cascade (business tables use
workspace_id ON DELETE CASCADE).
"""

from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, HardTimestampMixin, UUIDMixin

KINDS = ("personal", "team")
STATUSES = ("active", "suspended")


class Workspace(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "workspaces"

    slug: Mapped[str] = mapped_column(String(64), nullable=False)  # UNIQUE (migration layer)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="personal")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
