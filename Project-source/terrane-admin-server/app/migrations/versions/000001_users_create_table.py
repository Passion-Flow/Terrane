"""users create table

Revision ID: 000001
Revises:
Create Date: 2026-06-13
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("username", sa.String(64), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False, server_default="admin"),
        sa.Column("avatar", sa.String, nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("twofa_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("twofa_secret_ciphertext", sa.String(2048), nullable=True),
        sa.Column("twofa_dek_wrapped", sa.String(512), nullable=True),
        sa.Column("backup_codes_ciphertext", sa.String(2048), nullable=True),
        sa.Column("backup_codes_dek_wrapped", sa.String(512), nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("updated_by", sa.Uuid(as_uuid=True), nullable=True),
        sa.CheckConstraint("role IN ('super_admin','admin','auditor')", name="ck_users_role"),
    )
    op.create_index("idx_users_deleted_at", "users", ["deleted_at"])
    # postgres uses a partial unique index (email can be reused after soft delete); other dialects fall back to a plain unique index.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.create_index("uq_users_email", "users", ["email"], unique=True,
                        postgresql_where=sa.text("deleted_at IS NULL"))
    else:
        op.create_index("uq_users_email", "users", ["email"], unique=True)


def downgrade() -> None:
    op.drop_index("uq_users_email", table_name="users")
    op.drop_index("idx_users_deleted_at", table_name="users")
    op.drop_table("users")
