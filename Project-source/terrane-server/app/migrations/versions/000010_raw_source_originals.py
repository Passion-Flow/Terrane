"""raw_source_originals (platform DB terrane_main: raw bytes of uploaded files, for the "original vs. parsed" side-by-side preview)

Revision ID: 000010
Revises: 000009
Create Date: 2026-06-21

Stores raw bytes only for uploaded files (file kind); pasted text has no original. Hard-deleted by cascade
from raw_source. Kept in a separate table so list/get don't load the large field (blob).
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
