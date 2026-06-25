"""ModelChannel (platform DB terrane_main: model channels) — ORM mapping copy (admin reads/writes through this).

The authoritative schema lives in terrane-server/app/models/model_channel.py + migration 000006.
The frontend reads the same table directly to consume models.
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
