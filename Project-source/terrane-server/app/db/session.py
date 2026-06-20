"""异步 Engine + Session 工厂（信创 DB 适配矩阵；postgres / asyncpg 默认）。

照搬 Forge app/db/session.py 的 API 面（get_engine / get_sessionmaker / get_db_session /
reset_engine）。由字段化配置拼 async DSN（禁 connection-string env）。

DATABASE_TYPE（默认 postgres）经 app/db/dialects.py 映射为 SQLAlchemy 方言 + async 驱动，
支持信创国产库。默认 postgres 行为与原实现逐字一致（postgresql+asyncpg）。
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
from app.db.dialects import connect_args_for, ensure_driver, resolve_dialect

_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def build_dsn(*, hide_password: bool = False) -> URL:
    """由字段化配置拼 async DSN（按 DATABASE_TYPE 选方言+驱动；默认 postgres/asyncpg）。"""
    s = get_settings()
    spec = resolve_dialect(s.database_type)
    return URL.create(
        spec.drivername,
        username=s.database_username,
        password=s.database_password,
        host=s.database_host,
        port=s.database_port,
        database=s.database_name,
    )


def dsn_string(*, hide_password: bool = False) -> str:
    return build_dsn().render_as_string(hide_password=hide_password)


def _connect_args() -> dict:
    s = get_settings()
    spec = resolve_dialect(s.database_type)
    return connect_args_for(spec, ssl_mode=s.database_ssl_mode)


def get_engine() -> AsyncEngine:
    global _engine, _sessionmaker
    if _engine is None:
        s = get_settings()
        ensure_driver(resolve_dialect(s.database_type))  # 缺驱动 → 清晰 ImportError
        _engine = create_async_engine(
            build_dsn(),
            echo=s.database_echo,
            pool_size=s.database_pool_size,
            max_overflow=s.database_pool_max_overflow,
            pool_timeout=s.database_pool_timeout,
            pool_pre_ping=True,
            connect_args=_connect_args(),
        )
        _sessionmaker = async_sessionmaker(_engine, expire_on_commit=False, class_=AsyncSession)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    if _sessionmaker is None:
        get_engine()
    assert _sessionmaker is not None
    return _sessionmaker


async def get_db_session() -> AsyncIterator[AsyncSession]:
    """FastAPI 依赖：每请求一个 session。"""
    async with get_sessionmaker()() as session:
        yield session


def reset_engine() -> None:
    """清缓存（测试支持）。"""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
