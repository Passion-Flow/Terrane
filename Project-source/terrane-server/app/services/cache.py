"""Redis client factory — returns async connections per logical DB (replaces Forge's cache adapter layer).

Terrane only has the redis provider, so this is simplified to a single-file factory; the `client(db)`
interface is preserved so session_service / ratelimit can reuse the Forge implementation directly.
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

_clients: dict[int, Any] = {}


def client(db: int) -> Any:
    """Return an async redis client bound to the given logical DB (connection pool cached)."""
    if db not in _clients:
        s = get_settings()
        _clients[db] = aioredis.Redis(
            host=s.cache_host,
            port=s.cache_port,
            password=s.cache_password or None,
            db=db,
            ssl=s.cache_use_ssl,
            max_connections=s.cache_max_connections,
            decode_responses=True,
        )
    return _clients[db]


async def health_check() -> bool:
    try:
        return bool(await client(get_settings().cache_db_session).ping())
    except Exception:
        return False


def reset() -> None:
    """Clear the cache (test support)."""
    _clients.clear()
