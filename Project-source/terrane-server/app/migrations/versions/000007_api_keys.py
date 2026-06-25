"""api_keys (platform DB terrane_main: MCP / programmatic access keys, scoped to a KB)

Revision ID: 000007
Revises: 000006
Create Date: 2026-06-20

Bearer tokens for the MCP server and programmatic access: scoped to a single KB, granting retrieval/Q&A
(read-only). The token is shown once at creation time; the DB stores sha256. Hard delete: cascades from user/kb.
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000007"
down_revision = "000006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "api_keys",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("user_id", sa.Uuid(as_uuid=True), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kb_id", sa.Uuid(as_uuid=True), sa.ForeignKey("knowledge_bases.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("token_prefix", sa.String(16), nullable=False),   # for display (trn_xxxx…)
        sa.Column("token_hash", sa.String(64), nullable=False),     # sha256 hex
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
    )
    op.create_index("uq_api_keys_hash", "api_keys", ["token_hash"], unique=True)
    op.create_index("idx_api_keys_kb", "api_keys", ["kb_id"])


def downgrade() -> None:
    op.drop_table("api_keys")
