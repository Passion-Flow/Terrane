"""平台库（terrane_main）第二个异步连接 — 双库决策。

admin-server 操作员资产在 terrane_admin（app/db/session.py）；平台资产
（workspaces/users/memberships/system_settings/branding/audit_logs）在 terrane_main。
本模块提供指向 terrane_main 的独立 engine + sessionmaker + FastAPI 依赖 get_platform_db()。

host/port/user/pass 复用 DATABASE_*，仅库名换为 settings.platform_database_name。
平台表的建表/迁移由 terrane-server 管理；admin 只读写、不建表（platform ORM 用独立
PlatformBase，绝不进 admin 自己的 Base.metadata）。
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import URL
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings
from app.db.dialects import connect_args_for, resolve_dialect

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def build_platform_dsn() -> URL:
    """平台库 DSN：方言+驱动随 DATABASE_TYPE（与主库同库类型），仅库名换。"""
    s = get_settings()
    spec = resolve_dialect(s.database_type)
    return URL.create(
        spec.drivername,
        username=s.database_username,
        password=s.database_password,
        host=s.database_host,
        port=s.database_port,
        database=s.platform_database_name,
    )


def _connect_args() -> dict:
    s = get_settings()
    spec = resolve_dialect(s.database_type)
    return connect_args_for(spec, ssl_mode=s.database_ssl_mode)


def get_platform_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        s = get_settings()
        _engine = create_async_engine(
            build_platform_dsn(),
            echo=s.database_echo,
            pool_size=s.database_pool_size,
            max_overflow=s.database_pool_max_overflow,
            pool_timeout=s.database_pool_timeout,
            pool_pre_ping=True,
            connect_args=_connect_args(),
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_platform_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_platform_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_platform_db() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每请求一个平台库（terrane_main）session。"""
    async with get_platform_sessionmaker()() as session:
        yield session


def reset_platform_engine() -> None:
    """清缓存（测试支持）。"""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
