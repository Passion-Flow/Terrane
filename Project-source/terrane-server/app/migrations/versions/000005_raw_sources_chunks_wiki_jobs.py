"""raw_sources + chunks + wiki_pages + ingest_jobs (platform DB terrane_main: knowledge base storage foundation)

Revision ID: 000005
Revises: 000004
Create Date: 2026-06-19

Compounding knowledge storage: raw sources (originals/parsed text) → chunks (splits + halfvec vectors + lexical)
→ wiki_pages (compiled projection) + ingest_jobs (pipeline jobs).
Vectors: halfvec(1024) = Qwen3-Embedding dimensionality, half precision to save space; HNSW cosine.
Full text: this image lacks zhparser → use tsvector('simple') + pg_trgm (Chinese substring) dual GIN; zhparser
will come with the official offline-package image.
Hard delete: deleting a KB → cascade-delete raw/chunks/wiki/jobs as real deletes. Extensions use IF NOT EXISTS,
so new deployments get them automatically.
"""
from __future__ import annotations

from alembic import op

revision = "000005"
down_revision = "000004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE EXTENSION IF NOT EXISTS age")

    op.execute("""
        CREATE TABLE raw_sources (
            id uuid PRIMARY KEY,
            kb_id uuid NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            workspace_id uuid NOT NULL,
            kind varchar(16) NOT NULL DEFAULT 'file',          -- file/url/text/connector
            title varchar(512) NOT NULL,
            uri text,                                           -- storage path / original URL
            mime varchar(128),
            size_bytes bigint NOT NULL DEFAULT 0,
            status varchar(16) NOT NULL DEFAULT 'pending',      -- pending/parsing/parsed/failed
            parsed_text text,                                   -- parsed plain text (L4)
            error text,
            meta jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_raw_kind CHECK (kind in ('file','url','text','connector')),
            CONSTRAINT ck_raw_status CHECK (status in ('pending','parsing','parsed','failed'))
        )
    """)
    op.execute("CREATE INDEX idx_raw_kb ON raw_sources(kb_id)")

    # chunks: splits + vectors + lexical. content_tsv is a simple generated column; halfvec vector HNSW cosine.
    op.execute("""
        CREATE TABLE chunks (
            id uuid PRIMARY KEY,
            kb_id uuid NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            raw_source_id uuid NOT NULL REFERENCES raw_sources(id) ON DELETE CASCADE,
            ord int NOT NULL DEFAULT 0,
            content text NOT NULL,
            content_tsv tsvector GENERATED ALWAYS AS (to_tsvector('simple', content)) STORED,
            embedding halfvec(1024),
            token_count int NOT NULL DEFAULT 0,
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_chunks_kb ON chunks(kb_id)")
    op.execute("CREATE INDEX idx_chunks_raw ON chunks(raw_source_id)")
    op.execute("CREATE INDEX idx_chunks_tsv ON chunks USING gin(content_tsv)")
    op.execute("CREATE INDEX idx_chunks_trgm ON chunks USING gin(content gin_trgm_ops)")
    op.execute("CREATE INDEX idx_chunks_hnsw ON chunks USING hnsw (embedding halfvec_cosine_ops)")

    op.execute("""
        CREATE TABLE wiki_pages (
            id uuid PRIMARY KEY,
            kb_id uuid NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            workspace_id uuid NOT NULL,
            slug varchar(128) NOT NULL,
            title varchar(512) NOT NULL,
            body_md text NOT NULL DEFAULT '',
            source varchar(16) NOT NULL DEFAULT 'agent',        -- agent (compiled) / user (taken over)
            status varchar(16) NOT NULL DEFAULT 'draft',        -- draft/published
            inferred boolean NOT NULL DEFAULT false,            -- mark paragraphs with no source support as "inferred"
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_wiki_source CHECK (source in ('agent','user')),
            CONSTRAINT ck_wiki_status CHECK (status in ('draft','published'))
        )
    """)
    op.execute("CREATE UNIQUE INDEX uq_wiki_kb_slug ON wiki_pages(kb_id, slug)")

    op.execute("""
        CREATE TABLE ingest_jobs (
            id uuid PRIMARY KEY,
            kb_id uuid NOT NULL REFERENCES knowledge_bases(id) ON DELETE CASCADE,
            raw_source_id uuid REFERENCES raw_sources(id) ON DELETE CASCADE,
            kind varchar(16) NOT NULL DEFAULT 'parse',          -- parse/embed/graph/lint
            status varchar(16) NOT NULL DEFAULT 'queued',       -- queued/running/done/failed
            progress int NOT NULL DEFAULT 0,
            error text,
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_job_status CHECK (status in ('queued','running','done','failed'))
        )
    """)
    op.execute("CREATE INDEX idx_jobs_kb_status ON ingest_jobs(kb_id, status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS ingest_jobs")
    op.execute("DROP TABLE IF EXISTS wiki_pages")
    op.execute("DROP TABLE IF EXISTS chunks")
    op.execute("DROP TABLE IF EXISTS raw_sources")
