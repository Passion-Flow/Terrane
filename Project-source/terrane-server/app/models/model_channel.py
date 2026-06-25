"""ModelChannel (platform DB terrane_main) — authoritative schema for model channels.

The admin console writes via the PlatformBase mirror; the front end (ingestion/retrieval/RAG/graph/Agent)
reads this table directly to pick a channel and call the model.
kind: chat/embed/rerank/web_search. api_key = L5 sensitive (plaintext for now; field-level encryption
once KEK lands). Hard delete (no deleted_at).
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
