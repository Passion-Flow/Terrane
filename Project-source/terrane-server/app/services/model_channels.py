"""前台读模型渠道（平台库 terrane_main，admin 在后台配置）。按 kind 取启用渠道。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.model_channel import ModelChannel


def _norm(ch: ModelChannel | None) -> ModelChannel | None:
    """防御性清洗：base_url/api_key/model 去首尾空白(后台复制粘贴常带空格/换行,否则请求直接挂)。
    仅清洗内存对象、不落库；读路径无 commit，安全。"""
    if ch is not None:
        if ch.base_url:
            ch.base_url = ch.base_url.strip()
        if ch.api_key:
            ch.api_key = ch.api_key.strip()
        if ch.model:
            ch.model = ch.model.strip()
    return ch


async def get_channel(db: AsyncSession, kind: str) -> ModelChannel | None:
    """取某用途(chat/embed/rerank)最新启用渠道;未配置返回 None(调用方据此优雅降级)。"""
    return _norm((await db.execute(
        select(ModelChannel).where(ModelChannel.kind == kind, ModelChannel.enabled.is_(True))
        .order_by(ModelChannel.created_at.desc()).limit(1))).scalar_one_or_none())


async def list_channels(db: AsyncSession, kind: str) -> list[ModelChannel]:
    """列某用途的所有启用渠道(供前台「模型设置」下拉选)。"""
    return list((await db.execute(
        select(ModelChannel).where(ModelChannel.kind == kind, ModelChannel.enabled.is_(True))
        .order_by(ModelChannel.created_at.asc()))).scalars().all())


async def get_channel_by_model(db: AsyncSession, kind: str, model: str) -> ModelChannel | None:
    """按用户选定的 model 取启用渠道(校验前台选择合法)。"""
    if not model:
        return None
    return _norm((await db.execute(
        select(ModelChannel).where(ModelChannel.kind == kind, ModelChannel.enabled.is_(True),
                                   ModelChannel.model == model).limit(1))).scalar_one_or_none())
