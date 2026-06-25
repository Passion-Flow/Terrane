"""Server-side session store (Redis) -- ported from Forge app/services/session_service.py.

A session is an opaque server-side record indexed by a random sid; the cookie carries only the sid. Sliding renewal up to an absolute TTL.
A per-user index set supports global logout (kicking all sessions on password change / reset / role change / disable).
Key prefix: terrane_session:
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any

from app.core.config import get_settings
from app.services import cache


class SessionService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.redis = cache.client(self.settings.cache_db_session)

    def _key(self, sid: str) -> str:
        return f"terrane_session:{sid}"

    def _user_index(self, user_id: str) -> str:
        return f"terrane_session:user:{user_id}"

    async def create(self, *, user_id: str, workspace_id: str, role: str, ip: str, ua: str,
                     twofa_verified: bool, absolute_ttl_seconds: int | None = None) -> str:
        sid = secrets.token_urlsafe(32)
        now = int(time.time())
        ttl = absolute_ttl_seconds if absolute_ttl_seconds is not None else self.settings.session_absolute_ttl_seconds
        data = {
            "sid": sid, "user_id": user_id, "workspace_id": workspace_id, "role": role,
            "ip": ip, "ua": ua, "twofa_verified": twofa_verified,
            "created_at": now, "last_activity_at": now,
            "absolute_expiry": now + ttl,
        }
        await self.redis.set(self._key(sid), json.dumps(data),
                             ex=self.settings.session_idle_ttl_seconds)
        await self.redis.sadd(self._user_index(user_id), sid)
        return sid

    async def get(self, sid: str) -> dict[str, Any] | None:
        raw = await self.redis.get(self._key(sid))
        if not raw:
            return None
        data = json.loads(raw)
        now = int(time.time())
        if now >= data["absolute_expiry"]:
            await self.destroy(sid)
            return None
        # Sliding renewal (capped by the absolute expiry)
        data["last_activity_at"] = now
        ttl = min(self.settings.session_idle_ttl_seconds, data["absolute_expiry"] - now)
        await self.redis.set(self._key(sid), json.dumps(data), ex=ttl)
        return data

    async def destroy(self, sid: str) -> None:
        raw = await self.redis.get(self._key(sid))
        if raw:
            user_id = json.loads(raw).get("user_id")
            if user_id:
                await self.redis.srem(self._user_index(user_id), sid)
        await self.redis.delete(self._key(sid))

    async def destroy_all_for_user(self, user_id: str) -> None:
        """Global logout -- called on password change / reset / role change / disable."""
        sids = await self.redis.smembers(self._user_index(user_id))
        for sid in sids:
            await self.redis.delete(self._key(sid))
        await self.redis.delete(self._user_index(user_id))
