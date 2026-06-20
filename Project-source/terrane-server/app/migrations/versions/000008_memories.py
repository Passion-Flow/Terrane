"""memories（平台库 terrane_main：per-user 记忆,语义唤回）

Revision ID: 000008
Revises: 000007
Create Date: 2026-06-20

记忆严格 per-user(user_id),永不跨用户共享。embedding(halfvec 1024)做语义唤回。硬删除随 user 级联。
"""
from __future__ import annotations

from alembic import op

revision = "000008"
down_revision = "000007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE memories (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            content text NOT NULL,
            kind varchar(16) NOT NULL DEFAULT 'fact',     -- fact/preference/event
            source varchar(16) NOT NULL DEFAULT 'manual',  -- manual/extracted
            embedding halfvec(1024),
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_memories_user ON memories(user_id)")
    op.execute("CREATE INDEX idx_memories_hnsw ON memories USING hnsw (embedding halfvec_cosine_ops)")
    op.execute("CREATE INDEX idx_memories_trgm ON memories USING gin(content gin_trgm_ops)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS memories")
