"""model_channels (platform DB terrane_main: model channels, managed by admin / consumed by the front end)

Revision ID: 000006
Revises: 000005
Create Date: 2026-06-20

Moved into terrane_main (was in terrane_admin): the admin manages via the PlatformBase mirror, and the front
end (ingestion/retrieval/RAG/graph) reads the same DB directly.
Channel side of the six pathways: chat/embed/rerank/web_search. api_key = L5 (plaintext + __enc placeholder
for now; field-level encryption once KEK lands). Hard delete.
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
