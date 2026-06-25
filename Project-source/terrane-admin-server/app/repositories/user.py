"""User repository (ported from Forge)."""

from __future__ import annotations

from sqlalchemy import select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str, *, include_deleted: bool = False) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        if not include_deleted:
            stmt = stmt.where(User.deleted_at.is_(None))
        return (await self.db.execute(stmt)).scalar_one_or_none()
