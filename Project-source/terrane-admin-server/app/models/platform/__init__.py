"""Platform DB (terrane_main) ORM copies — dual-database decision.

These tables are created/migrated by terrane-server; admin-server only maps them for read/write
and must **never** enter admin's Base.metadata (otherwise admin's alembic would mistakenly
create/drop platform tables). Hence a separate PlatformBase.

Column definitions must align word-for-word with terrane-server's migrations (schema drift =
runtime KeyError / type error).
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.base import JSONType  # portable JSON column (shared definition with admin, no side effects)

__all__ = ["PlatformBase", "PlatformTimestampMixin", "JSONType"]


class PlatformBase(DeclarativeBase):
    """Standalone declarative base for the platform DB (isolated from admin's Base)."""


class PlatformTimestampMixin:
    """Timestamps under the hard-delete rule (no deleted_at)."""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
