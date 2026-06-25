"""SQLAlchemy 2.x declarative base + shared mixins (ported from Forge app/db/base.py).

Terrane admin-server single-tenant backend foundation, without workspace_id.
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

# Portable JSON column: postgres uses JSONB, other dialects fall back to JSON.
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


class AuthorMixin:
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
