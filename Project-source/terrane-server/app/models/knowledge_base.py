"""KnowledgeBase + KbMember (platform DB terrane_main) — knowledge base entity + KB-level sharing roles.

Three visibility tiers: private (default, owner + explicit kb_members only) / shared (shared with explicit
kb_members) / workspace (visible to the whole workspace).
KB-level role KbMember: viewer/editor (independent of the Workspace role; effective permissions are the
intersection of the two, PRD 4.1.6).
Hard-delete rule: workspace → KB → kb_members cascade as a real delete.
"""

from __future__ import annotations

import uuid

from sqlalchemy import String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, HardTimestampMixin, UUIDMixin

VISIBILITY = ("private", "shared", "workspace")
KB_ROLES = ("viewer", "editor")


class KnowledgeBase(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "knowledge_bases"

    workspace_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)   # FK→workspaces (CASCADE)
    owner_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)  # FK→users (SET NULL)
    slug: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    visibility: Mapped[str] = mapped_column(String(16), nullable=False, default="private")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")


class KbMember(UUIDMixin, HardTimestampMixin, Base):
    __tablename__ = "kb_members"

    kb_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)    # FK→knowledge_bases (CASCADE)
    user_id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), nullable=False)  # FK→users (CASCADE)
    role: Mapped[str] = mapped_column(String(16), nullable=False, default="viewer")
