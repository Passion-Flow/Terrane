"""ModelChannel（平台库 terrane_main）—— 模型渠道 schema 权威。

admin 后台经 PlatformBase mirror 写入;前台(摄入/检索/RAG/图谱/Agent)直读本表选渠道调模型。
kind: chat/embed/rerank/web_search。api_key=L5 敏感(暂明文,KEK 落地字段级加密)。硬删除(无 deleted_at)。
"""

from __future__ import annotations

import datetime
import uuid

from sqlalchemy import Boolean, DateTime, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base

PROVIDERS = ("openai_compatible", "anthropic", "tongyi", "web_search", "custom")
KINDS = ("chat", "embed", "rerank", "web_search", "vl", "asr")


class ModelChannel(Base):
    __tablename__ = "model_channels"

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="chat")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())
