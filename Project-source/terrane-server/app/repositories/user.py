"""User 仓储（平台库 terrane_main：users，硬删除无 deleted_at）。

邮箱在部署内全局唯一（应用层强制，跨 workspace 校验），故 get_by_email 不带 workspace 维度。
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
