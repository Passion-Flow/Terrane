"""Membership (platform DB terrane_main: memberships) — ORM mapping copy (admin manages read-only).

The authoritative schema lives in terrane-server/app/models/membership.py + migration 000001.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.platform import PlatformBase, PlatformTimestampMixin


class Membership(PlatformTimestampMixin, PlatformBase):
    __tablename__ = "memberships"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="Member")
