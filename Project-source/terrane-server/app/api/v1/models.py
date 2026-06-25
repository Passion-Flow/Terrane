"""Available models API (frontend /api/v1/models) — lists the models enabled under "Model Channels" in the admin console, for the frontend's "Model Settings" dropdown."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.services import model_channels

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.get("")
async def list_models(_=Depends(get_current_user),
                      db: AsyncSession = Depends(get_db_session)) -> dict:
    """Selectable models per purpose (name=channel name, model=model identifier). The frontend mainly uses the chat list as a dropdown."""
    out: dict[str, list[dict]] = {}
    for kind in ("chat", "vl", "embed", "rerank"):
        chans = await model_channels.list_channels(db, kind)
        out[kind] = [{"name": c.name, "model": c.model} for c in chans if c.model]
    return {"data": out}
