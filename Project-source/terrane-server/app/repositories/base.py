"""Generic repository -- CRUD + soft-delete-aware queries (ported from Forge app/repositories/base.py).

No business rules or external calls live here. Queries exclude soft-deleted rows by default.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.base import Base

T = TypeVar("T", bound=Base)


class BaseRepository(Generic[T]):
    model: type[T]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, id_: uuid.UUID, *, include_deleted: bool = False) -> T | None:
        stmt = select(self.model).where(self.model.id == id_)
        if not include_deleted and hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list(self, *, limit: int = 20, offset: int = 0, order_by=None):
        stmt = select(self.model)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        if order_by is not None:
            stmt = stmt.order_by(order_by)
        elif hasattr(self.model, "created_at"):
            stmt = stmt.order_by(self.model.created_at.desc())
        stmt = stmt.limit(limit).offset(offset)
        return list((await self.db.execute(stmt)).scalars().all())

    async def count(self) -> int:
        stmt = select(func.count()).select_from(self.model)
        if hasattr(self.model, "deleted_at"):
            stmt = stmt.where(self.model.deleted_at.is_(None))
        return int((await self.db.execute(stmt)).scalar_one())

    def add(self, obj: T) -> T:
        self.db.add(obj)
        return obj

    async def soft_delete(self, obj: T, *, actor_id: uuid.UUID | None = None) -> None:
        if not hasattr(obj, "deleted_at"):
            raise TypeError(f"{self.model.__name__} does not support soft delete")
        obj.deleted_at = datetime.datetime.now(datetime.timezone.utc)
        if hasattr(obj, "updated_by"):
            obj.updated_by = actor_id
