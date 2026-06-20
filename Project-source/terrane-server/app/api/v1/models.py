"""可用模型 API（前台 /api/v1/models）—— 列后台「模型渠道」里启用的模型,供前台「模型设置」下拉选。"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db_session
from app.services import model_channels

router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.get("")
async def list_models(_=Depends(get_current_user),
                      db: AsyncSession = Depends(get_db_session)) -> dict:
    """各用途的可选模型(name=渠道名,model=模型标识)。前台主要用 chat 列表做下拉。"""
    out: dict[str, list[dict]] = {}
    for kind in ("chat", "vl", "embed", "rerank"):
        chans = await model_channels.list_channels(db, kind)
        out[kind] = [{"name": c.name, "model": c.model} for c in chans if c.model]
    return {"data": out}
