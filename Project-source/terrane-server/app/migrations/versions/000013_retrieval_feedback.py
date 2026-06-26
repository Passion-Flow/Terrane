"""retrieval_feedback (online-learning moat: log impressions + implicit/explicit feedback per deployment)

Revision ID: 000013
Revises: 000012
Create Date: 2026-06-26

Every Deep/Fast retrieval logs an impression (query, mode, shown chunks with rank + per-path scores).
The frontend later attaches implicit feedback (clicked chunk + dwell) and explicit feedback (thumb,
answer-accepted). This log is the whole asset for the self-developed learning-to-rank loop: a per-
deployment fusion ranker (IPS-debiased) trains on it without touching any foundation model. Building
the log now (no model, no data needed) lays the foundation; the learner activates once feedback accrues.
"""
from __future__ import annotations

from alembic import op

revision = "000013"
down_revision = "000012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE retrieval_feedback (
            id              uuid PRIMARY KEY,
            kb_id           uuid NOT NULL,
            user_id         uuid,
            query           text NOT NULL,
            mode            varchar(8),
            shown           jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{chunk_id, rank, score, source_id}]
            clicked         jsonb NOT NULL DEFAULT '[]'::jsonb,   -- [{chunk_id, rank, dwell_ms}]
            thumb           smallint,                              -- -1 / 0 / 1
            answer_accepted boolean,
            created_at      timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX ix_rf_kb ON retrieval_feedback(kb_id, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS retrieval_feedback")
