"""User (front-end knowledge base user, WS-isolated) ORM — platform DB terrane_main (02-database entity #2).

(workspace_id, email) UNIQUE; hard-delete cascades from workspace. Email + argon2id (L3/L5 hashing);
enumeration-resistant. 2FA TOTP / backup-code ciphertext are placeholders for field-level encryption
(to be implemented once KEK lands, in a later stage).
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, HardTimestampMixin, JSONType, UUIDMixin

STATUSES = ("active", "disabled", "pending")  # pending = email not yet verified


class User(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "users"

    workspace_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    username: Mapped[str | None] = mapped_column(String(64), nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    avatar: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    email_verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    locale: Mapped[str] = mapped_column(String(16), nullable=False, default="zh-CN")
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="Asia/Shanghai")
    twofa_enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    totp_secret_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    backup_codes_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    signup_meta: Mapped[dict | None] = mapped_column(JSONType, nullable=True)  # signup risk control / source
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
