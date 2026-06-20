"""b2b 基线：system_settings / branding / audit_logs（平台库 terrane_main）

02-database：settings/branding（B 端基线配置）+ audit_logs（append-only，按月 RANGE 分区）。
audit_logs 合规 HARD RULE：REVOKE UPDATE,DELETE + BEFORE UPDATE/DELETE 触发器双重 append-only 加固。
非 PG 方言：audit_logs 退化为普通表（分区/REVOKE 为 PG 专属）。

Revision ID: 000002
Revises: 000001
Create Date: 2026-06-15
"""
from __future__ import annotations

import datetime

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "000002"
down_revision = "000001"
branch_labels = None
depends_on = None

_JSON = JSONB().with_variant(sa.JSON(), "mysql", "oracle")
_ACTOR_TYPES = ("admin", "user", "system")


def _month_bounds(d: datetime.date) -> tuple[str, str, str]:
    first = d.replace(day=1)
    nxt = (first.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
    return first.strftime("%Y_%m"), first.isoformat(), nxt.isoformat()


def _create_month_partition(parent: str, day: datetime.date) -> None:
    suffix, lo, hi = _month_bounds(day)
    op.execute(
        f"CREATE TABLE IF NOT EXISTS {parent}_{suffix} PARTITION OF {parent} "
        f"FOR VALUES FROM ('{lo}') TO ('{hi}')"
    )


def upgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"

    # —— system_settings：通用键值配置仓 ——
    op.create_table(
        "system_settings",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("key", sa.String(128), nullable=False),
        sa.Column("scope", sa.String(32), nullable=False, server_default="global"),
        sa.Column("scope_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("value", _JSON, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.UniqueConstraint("key", "scope", "scope_id", name="uq_system_settings_key_scope"),
    )

    # —— branding：部署级白标单行 ——
    op.create_table(
        "branding",
        sa.Column("id", sa.Uuid(as_uuid=True), primary_key=True),
        sa.Column("product_name", sa.String(120), nullable=False, server_default="Terrane"),
        sa.Column("logo_data", sa.Text, nullable=True),
        sa.Column("accent_color", sa.String(16), nullable=False, server_default="#0f9b8e"),
        sa.Column("login_subtitle", sa.String(255), nullable=True),
        sa.Column("support_url", sa.String(512), nullable=True),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
    )

    # —— audit_logs：append-only，按月 RANGE 分区 ——
    cols = [
        sa.Column("id", sa.Uuid(as_uuid=True), nullable=False),
        sa.Column("workspace_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor_type", sa.String(16), nullable=False),
        sa.Column("actor_id", sa.Uuid(as_uuid=True), nullable=True),
        sa.Column("actor_name", sa.String(255), nullable=True),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("target_type", sa.String(48), nullable=True),
        sa.Column("target_id", sa.String(64), nullable=True),
        sa.Column("before", _JSON, nullable=True),
        sa.Column("after", _JSON, nullable=True),
        sa.Column("ip", sa.String(64), nullable=True),
        sa.Column("user_agent", sa.String(512), nullable=True),
        sa.Column("request_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("CURRENT_TIMESTAMP")),
        sa.CheckConstraint("actor_type IN " + str(_ACTOR_TYPES), name="ck_audit_logs_actor_type"),
    ]
    if is_pg:
        cols.append(sa.PrimaryKeyConstraint("id", "created_at", name="pk_audit_logs"))
        op.create_table("audit_logs", *cols, postgresql_partition_by="RANGE (created_at)")
    else:
        cols.append(sa.PrimaryKeyConstraint("id", name="pk_audit_logs"))
        op.create_table("audit_logs", *cols)

    op.create_index("idx_audit_logs_workspace_id_created_at", "audit_logs",
                    ["workspace_id", sa.text("created_at DESC")])
    op.create_index("idx_audit_logs_actor_id", "audit_logs", ["actor_id"])
    op.create_index("idx_audit_logs_target", "audit_logs", ["target_type", "target_id"])
    if is_pg:
        op.execute("CREATE INDEX idx_audit_logs_created_at_brin "
                   "ON audit_logs USING brin (created_at)")
        today = datetime.date.today()
        nxt = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        _create_month_partition("audit_logs", today)
        _create_month_partition("audit_logs", nxt)
        # append-only 双重加固：REVOKE + 触发器（owner/superuser 绕过 REVOKE，触发器一律生效）。
        op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM PUBLIC")
        op.execute("REVOKE UPDATE, DELETE ON audit_logs FROM CURRENT_USER")
        op.execute(
            "CREATE OR REPLACE FUNCTION audit_logs_append_only() RETURNS trigger AS $$ "
            "BEGIN RAISE EXCEPTION 'audit_logs is append-only: % denied', TG_OP "
            "USING ERRCODE = 'insufficient_privilege'; END; $$ LANGUAGE plpgsql"
        )
        op.execute(
            "CREATE TRIGGER trg_audit_logs_append_only "
            "BEFORE UPDATE OR DELETE ON audit_logs "
            "FOR EACH ROW EXECUTE FUNCTION audit_logs_append_only()"
        )


def downgrade() -> None:
    bind = op.get_bind()
    is_pg = bind.dialect.name == "postgresql"
    if is_pg:
        op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_append_only ON audit_logs")
        op.execute("DROP FUNCTION IF EXISTS audit_logs_append_only()")
        today = datetime.date.today()
        nxt = (today.replace(day=28) + datetime.timedelta(days=4)).replace(day=1)
        for d in (today, nxt):
            suffix, _, _ = _month_bounds(d)
            op.execute(f"DROP TABLE IF EXISTS audit_logs_{suffix}")
    op.drop_index("idx_audit_logs_target", table_name="audit_logs")
    op.drop_index("idx_audit_logs_actor_id", table_name="audit_logs")
    op.drop_index("idx_audit_logs_workspace_id_created_at", table_name="audit_logs")
    if is_pg:
        op.execute("DROP INDEX IF EXISTS idx_audit_logs_created_at_brin")
    op.drop_table("audit_logs")
    op.drop_table("branding")
    op.drop_table("system_settings")
