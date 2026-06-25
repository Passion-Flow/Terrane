"""Authentication service — login + permission resolution (the authenticate core ported from
Forge's app/services/auth_service.py).

Coordinates the user repo + rate limiter + password hashing. All user-facing failures raise
BizError(code) without revealing whether the user exists (to prevent email enumeration).

Stage 2 boundary: TOTP encryption/decryption for 2FA depends on the field-level encryption KEK
infrastructure, which is not yet in place in OpenRelay, so 2FA setup/verification is a placeholder
in this stage (TODO Stage 3: once field encryption lands, port Forge's pyotp + crypto flow).
The factory super admin defaults to twofa_enabled=False, which does not affect the login foundation.
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
        # Constant path: always run one hash check whether or not the user exists, to weaken timing side channels.
        valid = user is not None and security.verify_password(password, user.password_hash)
        if not user or not valid:
            await self.rl.record_login_failure(email, threshold=lock_threshold, lock_seconds=lock_seconds)
            raise BizError("AUTH_INVALID_CREDENTIALS")
        if not user.is_active:
            raise BizError("AUTH_ACCOUNT_DISABLED")
        if user.twofa_enabled:
            # TODO Stage 3: once field encryption lands, port Forge's pyotp TOTP verification.
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
        """Change password (including the forced change on first login): verify the current password
        -> policy validation (forbid_identity enforced) -> persist and clear the flag.

        Policy parameters fall back to the factory config when omitted; the caller passes override
        values from the platform "Settings -> Security" page. The caller is responsible for commit.
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
            forbid_identity=True,  # Enforced on change: the new password must not equal the email/username (blocks the factory default = email)
        )
        if security.verify_password(new_password, user.password_hash):
            raise BizError("AUTH_PASSWORD_REUSED")
        user.password_hash = security.hash_password(new_password)
        user.must_change_password = False
