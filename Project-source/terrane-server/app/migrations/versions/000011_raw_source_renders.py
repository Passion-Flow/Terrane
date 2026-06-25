"""raw_source_renders (platform DB terrane_main: render status of per-page WebP layout images of the original) + make original data nullable

Revision ID: 000011
Revises: 000010
Create Date: 2026-06-24

Page-image bytes are stored in object storage (pages/{rid}/{n}.webp); this table only stores page count +
per-page dimensions, and the front end lazy-loads single pages by viewport.
Also makes raw_source_originals.data nullable: original bytes go to object storage first (originals/{rid}),
and data is only used for legacy data / fallback. Hard-deleted by cascade from raw_source.
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
