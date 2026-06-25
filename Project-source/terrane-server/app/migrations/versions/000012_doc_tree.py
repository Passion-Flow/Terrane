"""doc_tree_nodes (Retrieval 2.0: structural ToC tree + RAPTOR semantic summary tree) + chunks.tree_node_id

Revision ID: 000012
Revises: 000011
Create Date: 2026-06-25

Retrieval 2.0 adds a per-document hierarchical tree index (PageIndex-style "table of contents")
and an optional RAPTOR-style semantic summary tree. Both live in doc_tree_nodes, distinguished by
kind ('structural' | 'semantic'). The structural tree is built from the VL-parsed Markdown headings
(falling back to the PDF outline, then an LLM); the semantic tree is recursive cluster+summarize.
Node titles+summaries are embedded (halfvec, raw SQL ::halfvec, same as chunks) so they can feed both
reasoning-based tree search and vector candidate routing. chunks.tree_node_id back-links each chunk to
its structural node so retrieval can attach a "document > section > page" citation path.
"""
from __future__ import annotations

from alembic import op

revision = "000012"
down_revision = "000011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE doc_tree_nodes (
            id            uuid PRIMARY KEY,
            kb_id         uuid NOT NULL,
            raw_source_id uuid REFERENCES raw_sources(id) ON DELETE CASCADE,
            parent_id     uuid REFERENCES doc_tree_nodes(id) ON DELETE CASCADE,
            kind          varchar(16) NOT NULL DEFAULT 'structural',
            node_no       varchar(24) NOT NULL DEFAULT '',
            depth         integer NOT NULL DEFAULT 0,
            ord           integer NOT NULL DEFAULT 0,
            title         text NOT NULL DEFAULT '',
            summary       text,
            page_start    integer,
            page_end      integer,
            char_start    integer,
            char_end      integer,
            token_count   integer NOT NULL DEFAULT 0,
            path_titles   jsonb NOT NULL DEFAULT '[]'::jsonb,
            meta          jsonb NOT NULL DEFAULT '{}'::jsonb,
            created_at    timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_dtn_source ON doc_tree_nodes(raw_source_id, ord)")
    op.execute("CREATE INDEX ix_dtn_parent ON doc_tree_nodes(parent_id)")
    op.execute("CREATE INDEX ix_dtn_kb_kind ON doc_tree_nodes(kb_id, kind)")
    # Tree-node embedding (title+summary). halfvec(1024) like chunks; guarded so envs without
    # pgvector still migrate (vector recall simply degrades — structural reasoning does not need it).
    op.execute("""
        DO $$ BEGIN
            BEGIN
                ALTER TABLE doc_tree_nodes ADD COLUMN embedding halfvec(1024);
                CREATE INDEX ix_dtn_embedding ON doc_tree_nodes
                    USING hnsw (embedding halfvec_cosine_ops);
            EXCEPTION WHEN undefined_object OR feature_not_supported THEN
                RAISE NOTICE 'halfvec/hnsw unavailable; doc_tree_nodes.embedding skipped';
            END;
        END $$;
    """)
    op.execute("ALTER TABLE chunks ADD COLUMN tree_node_id uuid "
               "REFERENCES doc_tree_nodes(id) ON DELETE SET NULL")
    op.execute("CREATE INDEX ix_chunks_node ON chunks(tree_node_id)")


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_chunks_node")
    op.execute("ALTER TABLE chunks DROP COLUMN IF EXISTS tree_node_id")
    op.execute("DROP TABLE IF EXISTS doc_tree_nodes")
