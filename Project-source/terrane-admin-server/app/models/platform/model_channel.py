"""ModelChannel（平台库 terrane_main：模型渠道）— ORM 映射拷贝（admin 经此读写）。

schema 权威在 terrane-server/app/models/model_channel.py + 迁移 000006。前台直读同表消费模型。
"""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.core.ids import uuid7
from app.models.platform import PlatformBase, PlatformTimestampMixin

PROVIDERS = ("openai_compatible", "anthropic", "tongyi", "web_search", "custom")
KINDS = ("chat", "embed", "rerank", "web_search", "vl", "asr")


class ModelChannel(PlatformTimestampMixin, PlatformBase):
    __tablename__ = "model_channels"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid7)
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="chat")
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
