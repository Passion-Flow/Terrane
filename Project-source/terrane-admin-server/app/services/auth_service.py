"""认证服务 — 登录 + 权限解析（照搬 Forge app/services/auth_service.py 的 authenticate 核心）。

协调 user repo + 限流器 + 密码哈希。所有面向用户失败抛 BizError(code)，不区分用户是否存在
（防邮箱枚举）。

阶段②边界：2FA 的 TOTP 加解密依赖字段级加密 KEK 基建，OpenRelay 尚未落地，故本阶段
twofa 设置/校验为占位（TODO 阶段③接字段加密后照搬 Forge 的 pyotp + crypto 流程）。
出厂超管默认 twofa_enabled=False，不影响登录地基。
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.core.errors import BizError
from app.models.user import User
from app.permissions.roles import PLATFORM_ROLES
from app.repositories.user import UserRepository
from app.services.ratelimit import RateLimiter


def _permissions_for(role: str) -> list[str]:
    perms = PLATFORM_ROLES.get(role, set())
    return ["*"] if "*" in perms else sorted(perms)


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.rl = RateLimiter()
        self.settings = get_settings()

    async def authenticate(self, email: str, password: str, code: str | None,
                           *, lock_threshold: int | None = None,
                           lock_seconds: int | None = None) -> User:
        await self.rl.assert_not_locked(email)
        user = await self.users.get_by_email(email)
        # 恒定路径：无论用户是否存在都做一次哈希校验，削弱计时旁路。
        valid = user is not None and security.verify_password(password, user.password_hash)
        if not user or not valid:
            await self.rl.record_login_failure(email, threshold=lock_threshold, lock_seconds=lock_seconds)
            raise BizError("AUTH_INVALID_CREDENTIALS")
        if not user.is_active:
            raise BizError("AUTH_ACCOUNT_DISABLED")
        if user.twofa_enabled:
            # TODO 阶段③：接字段加密后照搬 Forge 的 pyotp TOTP 校验。
            if not code:
                raise BizError("AUTH_2FA_REQUIRED")
            raise BizError("AUTH_2FA_INVALID")
        await self.rl.clear_login_failures(email)
        return user

    def permissions_for(self, user: User) -> list[str]:
        return _permissions_for(user.role)

    async def change_password(self, user: User, current_password: str, new_password: str,
                              *, min_length: int | None = None,
                              require_char_classes: int | None = None) -> None:
        """改密（含首登强制改密）：校验当前密码 → 策略校验（强制 forbid_identity）→ 落库清标记。

        策略参数缺省回退出厂 config；调用方传入平台「设置→安全」覆盖值。调用方负责 commit。
        """
        if not security.verify_password(current_password, user.password_hash):
            raise BizError("AUTH_INVALID_CREDENTIALS")
        security.validate_password_policy(
            new_password,
            min_length=min_length if min_length is not None else self.settings.password_min_length,
            email=user.email,
            username=user.username,
            require_char_classes=(require_char_classes if require_char_classes is not None
                                  else self.settings.password_require_char_classes),
            forbid_identity=True,  # 改密强制：新密码不得等于邮箱/用户名（堵出厂默认=邮箱）
        )
        if security.verify_password(new_password, user.password_hash):
            raise BizError("AUTH_PASSWORD_REUSED")
        user.password_hash = security.hash_password(new_password)
        user.must_change_password = False
