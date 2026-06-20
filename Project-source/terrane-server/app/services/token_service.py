"""一次性 token（邮箱验证 / 密码重置）— Redis 存储，TTL 过期，消费即删（单次有效）。

key：terrane_token:{kind}:{token} → user_id。kind ∈ {email_verify, pwd_reset}。
token 高熵 url-safe；消费走 GETDEL 语义（原子取出并删除，防重放）。
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
    """取出并删除（单次有效）；不存在/过期返回 None。"""
    r = cache.client(get_settings().cache_db_tokens)
    key = _key(kind, token)
    user_id = await r.get(key)
    if user_id is None:
        return None
    await r.delete(key)
    return user_id
