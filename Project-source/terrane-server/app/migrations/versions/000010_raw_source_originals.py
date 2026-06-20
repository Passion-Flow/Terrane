"""raw_source_originals（平台库 terrane_main：上传文件的原始字节,用于「原文/解析」对照预览）

Revision ID: 000010
Revises: 000009
Create Date: 2026-06-21

只存上传文件(file kind)的原始字节,粘贴文本无原文。随 raw_source 硬删级联。单独成表,使 list/get
不加载大字段(blob)。
"""
from __future__ import annotations

from alembic import op

revision = "000010"
down_revision = "000009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE raw_source_originals (
            raw_source_id uuid PRIMARY KEY REFERENCES raw_sources(id) ON DELETE CASCADE,
            mime varchar(128),
            size bigint NOT NULL DEFAULT 0,
            data bytea NOT NULL,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS raw_source_originals")
