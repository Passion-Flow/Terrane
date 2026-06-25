"""FrontUser (platform DB terrane_main: users, frontend knowledge-base users) — ORM mapping copy (admin manages read-only).

The class is named FrontUser to distinguish it from the admin operator User; __tablename__ is still 'users'.
The authoritative schema lives in terrane-server/app/models/user.py + migration 000001. Sensitive columns
such as the password hash are not exposed externally.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.platform import PlatformBase, PlatformTimestampMixin


class FrontUser(PlatformTimestampMixin, PlatformBase):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    email_verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    twofa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
