"""knowledge_bases + kb_members（平台库 terrane_main：知识库实体 + 库级共享角色）

Revision ID: 000004
Revises: 000003
Create Date: 2026-06-19

02-database 实体:库(WS 隔离、可见性三档 private/shared/workspace)、库级角色 KbMember(viewer/editor)。
硬删除铁律:workspace 删 → 库级联删 → kb_members 级联删。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000004"
down_revision = "000003"
branch_labels = None
depends_on = None

_NOW = sa.text("CURRENT_TIMESTAMP")


def upgrade() -> None:
    op.create_table(
        "knowledge_bases",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("owner_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.String(1024), nullable=True),
        sa.Column("visibility", sa.String(16), nullable=False, server_default="private"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("visibility in ('private','shared','workspace')", name="ck_kb_visibility"),
    )
    op.create_index("uq_kb_workspace_slug", "knowledge_bases", ["workspace_id", "slug"], unique=True)
    op.create_index("idx_kb_workspace", "knowledge_bases", ["workspace_id"])

    op.create_table(
        "kb_members",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("kb_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="viewer"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=_NOW),
        sa.CheckConstraint("role in ('viewer','editor')", name="ck_kbmember_role"),
    )
    op.create_index("uq_kbmember_kb_user", "kb_members", ["kb_id", "user_id"], unique=True)


def downgrade() -> None:
    op.drop_table("kb_members")
    op.drop_table("knowledge_bases")
