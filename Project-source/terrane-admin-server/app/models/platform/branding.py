"""Branding (platform DB terrane_main: single-row branding) — ORM mapping copy.

The authoritative schema lives in terrane-server/app/models/branding.py + migration 000002.
Written by admin (the setup wizard).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.platform import PlatformBase, PlatformTimestampMixin

# Fixed primary key for the singleton row (matches terrane-server).
SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-0000000b5a0d")


class Branding(PlatformTimestampMixin, PlatformBase):
    __tablename__ = "branding"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    product_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Terrane")
    logo_data: Mapped[str | None] = mapped_column(Text, nullable=True)   # console/workspace logo
    login_logo: Mapped[str | None] = mapped_column(Text, nullable=True)  # login page logo
    favicon: Mapped[str | None] = mapped_column(Text, nullable=True)     # site favicon
    accent_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#0f9b8e")
    login_subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
