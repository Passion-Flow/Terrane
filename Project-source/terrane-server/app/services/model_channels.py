"""Frontend reads of model channels (platform DB terrane_main, configured by admin). Fetches enabled channels by kind."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_channel import ModelChannel


def _norm(ch: ModelChannel | None) -> ModelChannel | None:
    """Defensive sanitization: strip leading/trailing whitespace from base_url/api_key/model (admin copy-paste often carries spaces/newlines, otherwise requests fail outright).
    Only sanitizes the in-memory object, never persists; the read path has no commit, so it's safe."""
    if ch is not None:
        if ch.base_url:
            ch.base_url = ch.base_url.strip()
        if ch.api_key:
            ch.api_key = ch.api_key.strip()
        if ch.model:
            ch.model = ch.model.strip()
    return ch


async def get_channel(db: AsyncSession, kind: str) -> ModelChannel | None:
    """Fetch the latest enabled channel for a given purpose (chat/embed/rerank); returns None if unconfigured (callers degrade gracefully)."""
    return _norm((await db.execute(
        select(ModelChannel).where(ModelChannel.kind == kind, ModelChannel.enabled.is_(True))
        .order_by(ModelChannel.created_at.desc()).limit(1))).scalar_one_or_none())


async def list_channels(db: AsyncSession, kind: str) -> list[ModelChannel]:
    """List all enabled channels for a given purpose (for the frontend "Model Settings" dropdown)."""
    return list((await db.execute(
        select(ModelChannel).where(ModelChannel.kind == kind, ModelChannel.enabled.is_(True))
        .order_by(ModelChannel.created_at.asc()))).scalars().all())


async def get_channel_by_model(db: AsyncSession, kind: str, model: str) -> ModelChannel | None:
    """Fetch an enabled channel by the user-selected model (validates the frontend selection is legitimate)."""
    if not model:
        return None
    return _norm((await db.execute(
        select(ModelChannel).where(ModelChannel.kind == kind, ModelChannel.enabled.is_(True),
                                   ModelChannel.model == model).limit(1))).scalar_one_or_none())
