"""User repository (platform DB terrane_main: users, hard-delete, no deleted_at).

Email is globally unique within a deployment (enforced at the application layer, validated
across workspaces), so get_by_email does not take a workspace dimension.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models.user import User
from app.repositories.base import BaseRepository


class UserRepository(BaseRepository[User]):
    model = User

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def email_exists(self, email: str) -> bool:
        stmt = select(func.count()).select_from(User).where(func.lower(User.email) == email.lower())
        return int((await self.db.execute(stmt)).scalar_one()) > 0
