"""ingest_jobs resume/checkpoint + chunk/source content_sha (large-file streaming ingest, P3/F4)

Revision ID: 000014
Revises: 000013
Create Date: 2026-06-27

Bounded-memory streaming ingest for very large documents (400-500+ pages, hundreds of MB):
- ingest_jobs becomes the durable source of truth for a file ingest. New resume columns let an
  interrupted/restarted process continue from the last completed page batch instead of silently
  losing the in-flight `asyncio.create_task`, and let the UI show real per-batch progress on a
  450-page file: total_pages / pages_done (resume cursor) / batch_size / content_sha (file dedup) /
  attempts / heartbeat_at / checkpoint (jsonb, free-form batch state).
- chunks.content_sha = sha256 of the chunk's normalised content -> incremental dedup on reingest:
  only chunks whose hash changed are re-embedded; unchanged chunks keep their vector.
- raw_sources.content_sha = sha256 of the original bytes -> file-level dedup (skip parse+embed on an
  identical re-upload).
All additive, raw SQL, IF NOT EXISTS where possible -> never breaks existing rows/behaviour.
"""
from __future__ import annotations

from alembic import op

revision = "000014"
down_revision = "000013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ingest_jobs resume/checkpoint columns (durable job state for streaming ingest + restart sweeper).
    op.execute("ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS total_pages int NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS pages_done int NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS batch_size int NOT NULL DEFAULT 16")
    op.execute("ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS content_sha varchar(64)")
    op.execute("ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS attempts int NOT NULL DEFAULT 0")
    op.execute("ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS heartbeat_at timestamptz")
    op.execute("ALTER TABLE ingest_jobs ADD COLUMN IF NOT EXISTS checkpoint jsonb NOT NULL DEFAULT '{}'::jsonb")
    # Sweeper looks up still-`running` jobs by status; index keeps the startup scan cheap.
    op.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON ingest_jobs(status)")

    # chunk-level content hash -> incremental re-embed (only changed chunks). Indexed for diff lookups.
    op.execute("ALTER TABLE chunks ADD COLUMN IF NOT EXISTS content_sha varchar(64)")
    op.execute("CREATE INDEX IF NOT EXISTS idx_chunks_sha ON chunks(raw_source_id, content_sha)")

    # file-level content hash -> skip parse+embed on an identical re-upload.
    op.execute("ALTER TABLE raw_sources ADD COLUMN IF NOT EXISTS content_sha varchar(64)")


def downgrade() -> None:
    op.execute("ALTER TABLE raw_sources DROP COLUMN IF EXISTS content_sha")
    op.execute("DROP INDEX IF EXISTS idx_chunks_sha")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS content_sha")
    op.execute("DROP INDEX IF EXISTS idx_jobs_status")
    for col in ("checkpoint", "heartbeat_at", "attempts", "content_sha", "batch_size", "pages_done", "total_pages"):
        op.execute(f"ALTER TABLE ingest_jobs DROP COLUMN IF EXISTS {col}")
