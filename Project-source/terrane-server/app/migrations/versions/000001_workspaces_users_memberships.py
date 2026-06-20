"""workspaces / users / memberships create（平台库 terrane_main b2b 基线）

02-database 实体 #1/#2/#3。硬删除铁律：无 deleted_at；FK ON DELETE CASCADE。
users WS 隔离：(workspace_id,email) 部分唯一不需要（无软删）→ 直接 UNIQUE。

Revision ID: 000001
Revises:
Create Date: 2026-06-15
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "000001"
down_revision = None
branch_labels = None
depends_on = None

_JSON = JSONB().with_variant(sa.JSON(), "mysql", "oracle")


def upgrade() -> None:
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False, server_default="personal"),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("kind IN ('personal','team')", name="ck_workspaces_kind"),
        sa.CheckConstraint("status IN ('active','suspended')", name="ck_workspaces_status"),
        sa.UniqueConstraint("slug", name="uq_workspaces_slug"),
    )

    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("username", sa.String(64), nullable=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("avatar", sa.Text, nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("email_verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("locale", sa.String(16), nullable=False, server_default="zh-CN"),
        sa.Column("timezone", sa.String(64), nullable=False, server_default="Asia/Shanghai"),
        sa.Column("twofa_enabled", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("totp_secret_enc", sa.Text, nullable=True),
        sa.Column("backup_codes_enc", sa.Text, nullable=True),
        sa.Column("signup_meta", _JSON, nullable=True),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("status IN ('active','disabled','pending')", name="ck_users_status"),
        sa.UniqueConstraint("workspace_id", "email", name="uq_users_workspace_email"),
    )
    op.create_index("idx_users_workspace_id", "users", ["workspace_id"])

    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Uuid(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(16), nullable=False, server_default="Member"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("role IN ('Owner','Admin','Editor','Member','Reader')",
                           name="ck_memberships_role"),
        sa.UniqueConstraint("workspace_id", "user_id", name="uq_memberships_workspace_user"),
    )


def downgrade() -> None:
    op.drop_table("memberships")
    op.drop_index("idx_users_workspace_id", table_name="users")
    op.drop_table("users")
    op.drop_table("workspaces")
