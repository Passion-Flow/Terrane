"""User (admin operator) ORM model — Super Admin / Admin / Auditor (ported from Forge)."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import AuthorMixin, Base, TimestampMixin, UUIDMixin

ROLES = ("super_admin", "admin", "auditor")


class User(UUIDMixin, TimestampMixin, AuthorMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), nullable=False)
    username: Mapped[str] = mapped_column(String(64), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="admin")
    # Self-service avatar — small-image data URI (or URL); nullable, UI falls back to the initial.
    avatar: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Forced password change on first launch (setup wizard super-admin step): factory super-admin password = email → must change password before the console is unlocked.
    must_change_password: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    twofa_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    twofa_secret_ciphertext: Mapped[str | None] = mapped_column(String, nullable=True)
    twofa_dek_wrapped: Mapped[str | None] = mapped_column(String, nullable=True)
    backup_codes_ciphertext: Mapped[str | None] = mapped_column(String, nullable=True)
    backup_codes_dek_wrapped: Mapped[str | None] = mapped_column(String, nullable=True)
    last_login_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
