"""conversations + messages（平台库 terrane_main：个人 AI 助手的对话持久化/聊天记录）

Revision ID: 000009
Revises: 000008
Create Date: 2026-06-20

全局助手:跨用户全部知识库自动检索 + 记忆唤回 + 持久化对话历史。per-user,硬删级联。
"""
from __future__ import annotations

from alembic import op

revision = "000009"
down_revision = "000008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE conversations (
            id uuid PRIMARY KEY,
            user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            title varchar(200) NOT NULL DEFAULT '新对话',
            created_at timestamptz NOT NULL DEFAULT now(),
            updated_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_conv_user ON conversations(user_id, updated_at DESC)")
    op.execute("""
        CREATE TABLE messages (
            id uuid PRIMARY KEY,
            conversation_id uuid NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
            role varchar(16) NOT NULL,                 -- user/assistant
            content text NOT NULL,
            meta jsonb NOT NULL DEFAULT '{}'::jsonb,    -- 引用来源等
            created_at timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("CREATE INDEX idx_msg_conv ON messages(conversation_id, created_at)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS messages")
    op.execute("DROP TABLE IF EXISTS conversations")
