"""平台库（terrane_main）ORM 拷贝 — 双库决策。

这些表由 terrane-server 建表/迁移；admin-server 仅读写映射，**绝不**进 admin 的 Base.metadata
（否则 admin 的 alembic 会误建/误删平台表）。故用独立 PlatformBase。

列定义须与 terrane-server 的迁移逐字对齐（schema 漂移 = 运行期 KeyError/类型错）。
"""

from __future__ import annotations

import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.db.base import JSONType  # 可移植 JSON 列（与 admin 共用定义，无副作用）

__all__ = ["PlatformBase", "PlatformTimestampMixin", "JSONType"]


class PlatformBase(DeclarativeBase):
    """平台库独立 declarative base（与 admin 的 Base 隔离）。"""


class PlatformTimestampMixin:
    """硬删除铁律下的时间戳（无 deleted_at）。"""

    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
