"""branding breakdown: add login_logo + favicon (aligned with Dify's four branding slots).

product_name = app title, logo_data = console/workspace logo (unchanged), login_logo = login-page logo,
favicon = site icon. All nullable, with default fallbacks (favicon → logo_data → factory favicon.svg;
login_logo → default mark). Platform DB terrane_main.
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
