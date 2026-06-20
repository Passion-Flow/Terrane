"""branding 细分:新增 login_logo + favicon（对齐 Dify 品牌四块）。

product_name=应用标题、logo_data=控制台/工作区 Logo（沿用）、login_logo=登录页 Logo、favicon=站点图标。
均可空，缺省回退（favicon→logo_data→出厂 favicon.svg；login_logo→默认标记）。平台库 terrane_main。
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "000003"
down_revision = "000002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("branding", sa.Column("login_logo", sa.Text, nullable=True))
    op.add_column("branding", sa.Column("favicon", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("branding", "favicon")
    op.drop_column("branding", "login_logo")
