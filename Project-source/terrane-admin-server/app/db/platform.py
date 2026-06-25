"""Second async connection to the platform database (terrane_main) — the dual-database decision.

admin-server operator assets live in terrane_admin (app/db/session.py); platform assets
(workspaces/users/memberships/system_settings/branding/audit_logs) live in terrane_main.
This module provides a separate engine + sessionmaker pointing at terrane_main + the FastAPI dependency get_platform_db().

host/port/user/pass reuse DATABASE_*, only the database name is swapped to settings.platform_database_name.
Creation/migration of platform tables is managed by terrane-server; admin only reads/writes, never creates tables (the platform ORM uses a separate
PlatformBase and never enters admin's own Base.metadata).
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
    """Platform database DSN: dialect+driver follow DATABASE_TYPE (same DB type as the primary database), only the database name is swapped."""
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
    """FastAPI dependency: one platform database (terrane_main) session per request."""
    async with get_platform_sessionmaker()() as session:
        yield session


def reset_platform_engine() -> None:
    """Clear caches (test support)."""
    global _engine, _sessionmaker
    _engine = None
    _sessionmaker = None
