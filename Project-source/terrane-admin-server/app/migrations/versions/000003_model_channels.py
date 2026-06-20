"""model_channels: 平台级模型渠道（admin 配置部署的 LLM 后端;六路收口的渠道侧）

Revision ID: 000003
Revises: 000002
Create Date: 2026-06-19
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000003"
down_revision = "000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_channels",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("provider", sa.String(32), nullable=False),     # openai_compatible/anthropic/tongyi/web_search/custom
        sa.Column("kind", sa.String(16), nullable=False, server_default="chat"),  # chat/embed/rerank/web_search
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=True),
        sa.Column("api_key", sa.Text, nullable=True),             # L5: 暂明文 + __enc 占位(KEK 落地后字段级加密)
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )
    op.create_index("uq_model_channels_name", "model_channels", ["name"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_model_channels_name", table_name="model_channels")
    op.drop_table("model_channels")
