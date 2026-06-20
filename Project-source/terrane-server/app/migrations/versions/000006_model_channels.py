"""model_channels（平台库 terrane_main：模型渠道，admin 管理 / 前台消费）

Revision ID: 000006
Revises: 000005
Create Date: 2026-06-20

挪到 terrane_main(原在 terrane_admin):admin 经 PlatformBase mirror 管理,前台(摄入/检索/RAG/图谱)直读同库。
六路收口渠道侧:chat/embed/rerank/web_search。api_key=L5(暂明文+__enc 占位,KEK 落地字段级加密)。硬删除。
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000006"
down_revision = "000005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_channels",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="chat"),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=True),
        sa.Column("api_key", sa.Text, nullable=True),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("uq_model_channels_name", "model_channels", ["name"], unique=True)
    op.create_index("idx_model_channels_kind", "model_channels", ["kind", "enabled"])


def downgrade() -> None:
    op.drop_index("idx_model_channels_kind", table_name="model_channels")
    op.drop_index("uq_model_channels_name", table_name="model_channels")
    op.drop_table("model_channels")
