"""raw_source_renders（平台库 terrane_main：原文逐页 WebP 版面图渲染状态）+ 原文 data 可空

Revision ID: 000011
Revises: 000010
Create Date: 2026-06-24

页面图字节存对象存储（pages/{rid}/{n}.webp），本表只存页数 + 每页尺寸，前端按视口懒加载单页。
同时把 raw_source_originals.data 改可空：原文字节优先入对象存储（originals/{rid}），data 仅旧数据/降级用。
随 raw_source 硬删级联。
"""
from __future__ import annotations

from alembic import op

revision = "000011"
down_revision = "000010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE raw_source_originals ALTER COLUMN data DROP NOT NULL")
    op.execute("""
        CREATE TABLE raw_source_renders (
            raw_source_id uuid PRIMARY KEY REFERENCES raw_sources(id) ON DELETE CASCADE,
            status varchar(16) NOT NULL DEFAULT 'pending',
            page_count integer NOT NULL DEFAULT 0,
            pages jsonb NOT NULL DEFAULT '[]'::jsonb,
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS raw_source_renders")
    op.execute("UPDATE raw_source_originals SET data = '\\x'::bytea WHERE data IS NULL")
    op.execute("ALTER TABLE raw_source_originals ALTER COLUMN data SET NOT NULL")
