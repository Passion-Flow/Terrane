"""Redis 客户端工厂 — 按逻辑库返回异步连接（替代 Forge 的 cache adapter 层）。

Terrane 仅 redis 提供方，故简化为单文件工厂；保留 `client(db)` 接口，
让 session_service / ratelimit 照搬 Forge 实现即可。
"""

from __future__ import annotations

from typing import Any

import redis.asyncio as aioredis

from app.core.config import get_settings

_clients: dict[int, Any] = {}


def client(db: int) -> Any:
    """返回绑定到指定逻辑库的异步 redis 客户端（连接池缓存）。"""
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
    """清缓存（测试支持）。"""
    _clients.clear()
