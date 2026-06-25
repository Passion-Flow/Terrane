"""Async Engine + Session factory (Xinchuang (domestic) DB adaptation matrix; postgres / asyncpg default).

Ports the API surface of Forge app/db/session.py (get_engine / get_sessionmaker / get_db_session /
reset_engine). Builds the async DSN from field-based configuration (no connection-string env).

DATABASE_TYPE (default postgres) is mapped via app/db/dialects.py to a SQLAlchemy dialect + async driver
to support domestic Xinchuang databases. The default postgres behavior is byte-for-byte identical to the original (postgresql+asyncpg).
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
    """Build the async DSN from field-based configuration (dialect+driver chosen by DATABASE_TYPE; default postgres/asyncpg)."""
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
        ensure_driver(resolve_dialect(s.database_type))  # missing driver -> clear ImportError
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
    """FastAPI dependency: one session per request."""
    async with get_sessionmaker()() as session:
        yield session


def reset_engine() -> None:
    """Clear caches (test support)."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
