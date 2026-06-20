"""Alembic async env — engine 由字段化配置拼装（照搬 Forge，去 multi-DB 适配层）。"""

from __future__ import annotations

import asyncio

from alembic import context
from sqlalchemy.ext.asyncio import AsyncEngine

from app.db.base import Base
from app.db.session import dsn_string, get_engine

# 导入所有模型，让 autogenerate / metadata 能看到。
from app.models import user  # noqa: F401

target_metadata = Base.metadata


def _run_sync(connection) -> None:
    context.configure(connection=connection, target_metadata=target_metadata, compare_type=True)
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine: AsyncEngine = get_engine()
    async with engine.connect() as connection:
        await connection.run_sync(_run_sync)
    await engine.dispose()


def run_migrations_offline() -> None:
    context.configure(
        url=dsn_string(hide_password=False),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async())
