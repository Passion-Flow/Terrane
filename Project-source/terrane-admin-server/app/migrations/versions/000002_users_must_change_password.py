"""users add must_change_password

Revision ID: 000002
Revises: 000001
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000002"
down_revision = "000001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("must_change_password", sa.Boolean, nullable=False,
                  server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("users", "must_change_password")
