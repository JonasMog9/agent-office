"""Training load per day: TRIMP, fitness (CTL), fatigue (ATL), form and ACWR.

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

COLUMNS = ["trimp", "ctl", "atl", "form", "acwr"]


def upgrade() -> None:
    with op.batch_alter_table("daily_scores") as batch:
        for name in COLUMNS:
            batch.add_column(sa.Column(name, sa.Float(), nullable=True))
        batch.add_column(sa.Column("load_details", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("daily_scores") as batch:
        for name in [*COLUMNS, "load_details"]:
            batch.drop_column(name)
