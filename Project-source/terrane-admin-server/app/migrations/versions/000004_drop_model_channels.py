"""drop model_channels from terrane_admin (moved to terrane_main / 000006)

Revision ID: 000004
Revises: 000003
Create Date: 2026-06-20
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000004"
down_revision = "000003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP TABLE IF EXISTS model_channels")


def downgrade() -> None:
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
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("CURRENT_TIMESTAMP")),
    )
