"""KnowledgeBase (platform DB terrane_main) — ORM mapping copy (admin platform overview, read-only).

The authoritative schema lives in terrane-server/app/models/knowledge_base.py + migration 000004.
The admin console only views metadata; there is no content-read surface.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.models.platform import PlatformBase, PlatformTimestampMixin


class KnowledgeBase(PlatformTimestampMixin, PlatformBase):
    __tablename__ = "knowledge_bases"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True)
    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
