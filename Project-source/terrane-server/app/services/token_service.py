"""One-time tokens (email verification / password reset) — stored in Redis, expire by TTL, deleted on consumption (single use).

key: terrane_token:{kind}:{token} -> user_id. kind in {email_verify, pwd_reset}.
Tokens are high-entropy url-safe; consumption uses GETDEL semantics (atomic fetch-and-delete to prevent replay).
"""

from __future__ import annotations

import secrets

from app.core.config import get_settings
from app.services import cache


def _key(kind: str, token: str) -> str:
    return f"terrane_token:{kind}:{token}"


async def issue(kind: str, user_id: str, *, ttl_seconds: int) -> str:
    token = secrets.token_urlsafe(32)
    r = cache.client(get_settings().cache_db_tokens)
    await r.set(_key(kind, token), user_id, ex=ttl_seconds)
    return token


async def consume(kind: str, token: str) -> str | None:
    """Fetch and delete (single use); returns None if missing/expired."""
    r = cache.client(get_settings().cache_db_tokens)
    key = _key(kind, token)
    user_id = await r.get(key)
    if user_id is None:
        return None
    await r.delete(key)
    return user_id
