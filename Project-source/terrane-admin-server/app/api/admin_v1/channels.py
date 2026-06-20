"""模型渠道管理 API（平台库 terrane_main：model_channels）。挂 /admin-api/v1/channels。

模型渠道(六路收口渠道侧)存 terrane_main:admin 经 PlatformBase mirror 管理,前台(摄入/检索/RAG/图谱/Agent)
直读同表消费模型。权限 platform.channel.*。变体范式:GET /providers 给「新建渠道」下拉类型;每类型居中模态。
api_key = L5:暂明文存(__enc 占位,KEK 落地字段级加密),GET 一律脱敏(只回 has_key)。审计同库 terrane_main。
"""

from __future__ import annotations

import uuid
from typing import Literal

import structlog
from fastapi import APIRouter, Depends, Path, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import CurrentUser, audit_ctx
from app.core.errors import BizError
from app.db.platform import get_platform_db
from app.models.platform.model_channel import KINDS, PROVIDERS, ModelChannel
from app.permissions.deps import require_perm
from app.permissions.registry import P
from app.services import audit_service
from app.services.channel_presets import all_presets

log = structlog.get_logger("terrane.admin.channels")

router = APIRouter(prefix="/admin-api/v1/channels", tags=["channels"])

ProviderLit = Literal["openai_compatible", "anthropic", "tongyi", "web_search", "custom"]
KindLit = Literal["chat", "embed", "rerank", "web_search", "vl", "asr"]


def _out(c: ModelChannel) -> dict:
    return {
        "id": str(c.id), "provider": c.provider, "kind": c.kind, "name": c.name,
        "base_url": c.base_url, "model": c.model, "enabled": c.enabled,
        "has_key": bool(c.api_key),  # 脱敏:绝不回传 api_key
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _cid(channel_id: str) -> uuid.UUID:
    try:
        return uuid.UUID(channel_id)
    except ValueError:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "channel"})


async def _get(db: AsyncSession, channel_id: str) -> ModelChannel:
    c = await db.get(ModelChannel, _cid(channel_id))
    if c is None:
        raise BizError("RESOURCE_NOT_FOUND", {"resource": "channel"})
    return c


@router.get("/providers")
async def providers(_=Depends(require_perm(P.CHANNEL_READ))) -> dict:
    """「新建渠道」下拉的类型预设(变体范式)。"""
    return {"providers": all_presets()}


@router.get("")
async def list_channels(
    _=Depends(require_perm(P.CHANNEL_READ)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    rows = (await pdb.execute(select(ModelChannel).order_by(ModelChannel.created_at.desc()))).scalars().all()
    return {"items": [_out(c) for c in rows]}


class CreateChannelIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    provider: ProviderLit
    kind: KindLit = "chat"
    name: str = Field(min_length=1, max_length=120)
    base_url: str = Field(default="", max_length=512)
    api_key: str = Field(default="", max_length=4096)
    model: str = Field(default="", max_length=128)


@router.post("", status_code=201)
async def create_channel(
    body: CreateChannelIn, request: Request,
    user: CurrentUser = Depends(require_perm(P.CHANNEL_WRITE)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    if body.provider not in PROVIDERS or body.kind not in KINDS:
        raise BizError("VALIDATION_FAILED", {"reason": "provider_or_kind"})
    if int((await pdb.execute(select(func.count()).select_from(ModelChannel)
                              .where(func.lower(ModelChannel.name) == body.name.lower()))).scalar_one()) > 0:
        raise BizError("RESOURCE_CONFLICT", {"resource": "channel_name"})
    ch = ModelChannel(provider=body.provider, kind=body.kind, name=body.name,
                      base_url=body.base_url or None, api_key=body.api_key or None,
                      model=body.model or None, enabled=True)
    pdb.add(ch)
    await pdb.flush()
    await audit_service.record(
        pdb, action="channel.create", actor_id=user.user_id, actor_name=user.name,
        target_type="channel", target_id=str(ch.id),
        after={"provider": body.provider, "kind": body.kind, "name": body.name,
               "model": body.model, "has_key": bool(body.api_key)}, **audit_ctx(request))
    await pdb.commit()
    log.info("channel_created", channel_id=str(ch.id), actor_id=user.user_id)
    return _out(ch)


class UpdateChannelIn(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    name: str | None = Field(default=None, max_length=120)
    base_url: str | None = Field(default=None, max_length=512)
    api_key: str | None = Field(default=None, max_length=4096)  # 留空/None = 不变
    model: str | None = Field(default=None, max_length=128)
    kind: KindLit | None = None
    enabled: bool | None = None


@router.patch("/{channel_id}")
async def update_channel(
    body: UpdateChannelIn, channel_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.CHANNEL_WRITE)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    ch = await _get(pdb, channel_id)
    if body.name is not None:
        ch.name = body.name or ch.name
    if body.base_url is not None:
        ch.base_url = body.base_url or None
    if body.model is not None:
        ch.model = body.model or None
    if body.kind is not None:
        ch.kind = body.kind
    if body.enabled is not None:
        ch.enabled = body.enabled
    if body.api_key:  # 仅非空才覆盖(脱敏回填不覆盖既有 key)
        ch.api_key = body.api_key
    await audit_service.record(
        pdb, action="channel.update", actor_id=user.user_id, actor_name=user.name,
        target_type="channel", target_id=str(ch.id),
        after={"name": ch.name, "model": ch.model, "kind": ch.kind, "enabled": ch.enabled,
               "has_key": bool(ch.api_key)}, **audit_ctx(request))
    await pdb.commit()
    return _out(ch)


@router.delete("/{channel_id}")
async def delete_channel(
    channel_id: str = Path(...), request: Request = None,  # type: ignore[assignment]
    user: CurrentUser = Depends(require_perm(P.CHANNEL_WRITE)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    ch = await _get(pdb, channel_id)
    await audit_service.record(
        pdb, action="channel.delete", actor_id=user.user_id, actor_name=user.name,
        target_type="channel", target_id=str(ch.id),
        before={"name": ch.name, "provider": ch.provider}, **audit_ctx(request))
    await pdb.delete(ch)
    await pdb.commit()
    log.info("channel_deleted", channel_id=channel_id, actor_id=user.user_id)
    return {"ok": True}


async def _probe(ch: ModelChannel) -> tuple[bool, str]:
    """真实连通性探测:openai 兼容/通义 → GET /models;anthropic → /v1/models;无 base_url 直接失败。"""
    if not ch.base_url:
        return False, "no_base_url"
    import httpx

    base = ch.base_url.rstrip("/")
    if ch.provider == "anthropic":
        url, headers = f"{base}/v1/models", {"x-api-key": ch.api_key or "", "anthropic-version": "2023-06-01"}
    else:
        url, headers = f"{base}/models", ({"Authorization": f"Bearer {ch.api_key}"} if ch.api_key else {})
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.get(url, headers=headers)
    except Exception:
        return False, "connect_failed"
    if r.status_code < 400:
        return True, f"ok_{r.status_code}"
    if r.status_code in (401, 403):
        return False, "auth_failed"
    return False, f"http_{r.status_code}"


@router.post("/{channel_id}/test")
async def test_channel(
    channel_id: str = Path(...),
    _: CurrentUser = Depends(require_perm(P.CHANNEL_WRITE)),
    pdb: AsyncSession = Depends(get_platform_db),
) -> dict:
    ch = await _get(pdb, channel_id)
    ok, detail = await _probe(ch)
    return {"data": {"ok": ok, "detail": detail}}
