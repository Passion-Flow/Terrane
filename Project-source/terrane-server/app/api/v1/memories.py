"""记忆 API（前台 /api/v1/memories）。严格 per-user —— 一切按当前登录用户隔离,永不跨用户。"""

from __future__ import annotations

import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Path
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, get_current_user, get_db_session
from app.core.errors import BizError
from app.models.memory import Memory
from app.services import memory_service

router = APIRouter(prefix="/api/v1/memories", tags=["memories"])


class RememberIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    content: str = Field(min_length=1, max_length=2000)
    kind: Literal["fact", "preference", "event"] = "fact"


@router.post("", status_code=201)
async def add_memory(body: RememberIn, user: CurrentUser = Depends(get_current_user),
                     db: AsyncSession = Depends(get_db_session)) -> dict:
    m = await memory_service.remember(db, uuid.UUID(user.user_id), body.content, kind=body.kind)
    return {"id": str(m.id), "content": m.content, "kind": m.kind, "source": m.source}


@router.get("")
async def list_memories(user: CurrentUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db_session)) -> dict:
    rows = (await db.execute(select(Memory).where(Memory.user_id == uuid.UUID(user.user_id))
                             .order_by(Memory.created_at.desc()).limit(200))).scalars().all()
    return {"items": [{"id": str(m.id), "content": m.content, "kind": m.kind, "source": m.source,
                       "created_at": m.created_at.isoformat() if m.created_at else None} for m in rows]}


@router.get("/settings")
async def get_memory_settings(user: CurrentUser = Depends(get_current_user),
                              db: AsyncSession = Depends(get_db_session)) -> dict:
    """读自动记忆开关(默认开)。"""
    return {"auto": await memory_service.auto_enabled(db, uuid.UUID(user.user_id))}


class MemorySettingsIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    auto: bool


@router.put("/settings")
async def update_memory_settings(body: MemorySettingsIn,
                                 user: CurrentUser = Depends(get_current_user),
                                 db: AsyncSession = Depends(get_db_session)) -> dict:
    """开/关自动记忆(从聊天与上传文档自动抽取)。"""
    await memory_service.set_auto(db, uuid.UUID(user.user_id), body.auto)
    return {"auto": body.auto}


class RecallIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    query: str = Field(min_length=1, max_length=2000)
    limit: int = Field(default=5, ge=1, le=20)


@router.post("/recall")
async def recall_memories(body: RecallIn, user: CurrentUser = Depends(get_current_user),
                          db: AsyncSession = Depends(get_db_session)) -> dict:
    hits = await memory_service.recall(db, uuid.UUID(user.user_id), body.query, limit=body.limit)
    return {"hits": hits, "total": len(hits)}


class ExtractIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    text: str = Field(min_length=1, max_length=8000)


@router.post("/extract")
async def extract_memories(body: ExtractIn, user: CurrentUser = Depends(get_current_user),
                           db: AsyncSession = Depends(get_db_session)) -> dict:
    n = await memory_service.extract(db, uuid.UUID(user.user_id), body.text)
    return {"added": n}


@router.delete("/{memory_id}")
async def delete_memory(memory_id: str = Path(...), user: CurrentUser = Depends(get_current_user),
                        db: AsyncSession = Depends(get_db_session)) -> dict:
    try:
        mid = uuid.UUID(memory_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "memory"})
    m = await db.get(Memory, mid)
    if m is None or str(m.user_id) != user.user_id:   # 越权即视为不存在
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "memory"})
    await db.delete(m)
    await db.commit()
    return {"ok": True}
