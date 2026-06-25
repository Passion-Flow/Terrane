"""SQLAlchemy 2.x declarative base + shared mixins (terrane-server platform DB terrane_main).

Platform business tables follow the hard-delete rule (02-database: no deleted_at,
delete = real delete + FK cascade) -> use HardTimestampMixin. TimestampMixin (with
deleted_at) is kept only for the compatibility port layer; platform tables should not use it.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

# Portable JSON column: JSONB on postgres, falls back to JSON on other dialects.
JSONType = JSONB().with_variant(JSON(), "mysql", "oracle")


class Base(DeclarativeBase):
    pass


class UUIDMixin:
    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)


class TimestampMixin:
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )


class HardTimestampMixin:
    """Timestamps under the hard-delete rule (no deleted_at) -- standard for platform business tables."""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AuthorMixin:
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
