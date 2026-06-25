"""Fixed-window rate limiting + login-failure lockout (Redis) — ported from Forge app/services/ratelimit.py."""

from __future__ import annotations

import time

from app.core.config import get_settings
from app.core.errors import BizError
from app.services import cache


class RateLimiter:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = cache.client(self.settings.cache_db_ratelimit)

    async def hit(self, key: str, *, limit: int, window: int,
                  code: str = "RATE_LIMIT_EXCEEDED") -> None:
        """Increment the fixed-window counter; raises BizError(code) when over the limit."""
        now = int(time.time())
        bucket = f"rl:{key}:{now // window}"
        count = await self.redis.incr(bucket)
        if count == 1:
            await self.redis.expire(bucket, window)
        if count > limit:
            raise BizError(code, {"retry_after": window - (now % window)})

    async def record_login_failure(self, email: str, *, threshold: int | None = None,
                                   lock_seconds: int | None = None) -> None:
        """Record a login failure; lock the account once the threshold is reached. Threshold/duration default to config; callers may pass platform security-policy overrides."""
        threshold = threshold if threshold is not None else self.settings.login_lock_threshold
        lock_seconds = lock_seconds if lock_seconds is not None else self.settings.login_lock_seconds
        key = f"login_fail:{email.lower()}"
        count = await self.redis.incr(key)
        if count == 1:
            await self.redis.expire(key, lock_seconds)
        if count >= threshold:
            await self.redis.set(f"login_locked:{email.lower()}", "1", ex=lock_seconds)

    async def assert_not_locked(self, email: str) -> None:
        if await self.redis.get(f"login_locked:{email.lower()}"):
            raise BizError("AUTH_ACCOUNT_LOCKED")

    async def clear_login_failures(self, email: str) -> None:
        await self.redis.delete(f"login_fail:{email.lower()}", f"login_locked:{email.lower()}")
