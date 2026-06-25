"""Branding (deployment-level white-label) ORM — platform DB terrane_main (02-database: B2B baseline config).

A single global row (id fixed to SINGLETON_ID): product name / logo / accent color / login subtitle /
support link. Written by the "Branding" step of the setup wizard; the front end and admin console read it
to apply the white-label. Ships with built-in defaults (page-based zero-config rule).
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, HardTimestampMixin, UUIDMixin

# Fixed primary key for the singleton row (the one and only global white-label config row).
SINGLETON_ID = uuid.UUID("00000000-0000-0000-0000-0000000b5a0d")


class Branding(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "branding"

    product_name: Mapped[str] = mapped_column(String(120), nullable=False, default="Terrane")
    logo_data: Mapped[str | None] = mapped_column(Text, nullable=True)  # console/workspace logo (data URI or URL)
    login_logo: Mapped[str | None] = mapped_column(Text, nullable=True)  # login-page logo
    favicon: Mapped[str | None] = mapped_column(Text, nullable=True)     # site favicon
    accent_color: Mapped[str] = mapped_column(String(16), nullable=False, default="#0f9b8e")
    login_subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    support_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
