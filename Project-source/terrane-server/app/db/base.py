"""SQLAlchemy 2.x declarative base + 共享 mixin（terrane-server 平台库 terrane_main）。

平台业务表遵硬删除铁律（02-database：无 deleted_at，删除=真删+FK 级联）→ 用 HardTimestampMixin。
保留 TimestampMixin（含 deleted_at）仅为兼容拷贝层，平台表不应使用。
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import JSON, DateTime, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.core.ids import uuid7

# 可移植 JSON 列：postgres 用 JSONB，其他方言回退 JSON。
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
    """硬删除铁律下的时间戳（无 deleted_at）——平台业务表标配。"""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class AuthorMixin:
    created_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(nullable=True)
