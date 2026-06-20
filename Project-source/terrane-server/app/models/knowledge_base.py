"""KnowledgeBase + KbMember（平台库 terrane_main）—— 知识库实体 + 库级共享角色。

可见性三档:private(默认,仅 owner+显式 kb_members)/ shared(显式 kb_members 共享)/ workspace(本工作区可见)。
库级角色 KbMember:viewer/editor(与 Workspace 角色独立,实际权限取交集,PRD 4.1.6)。
硬删除铁律:workspace→库→kb_members 级联真删。
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
