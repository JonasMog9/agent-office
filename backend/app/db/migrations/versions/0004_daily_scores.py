"""Daily scores: recovery, strain and sleep per day, with their breakdowns.

Revision ID: 0004
Revises: 0003
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004"
down_revision: str | None = "0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_scores",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("recovery", sa.Float(), nullable=True),
        sa.Column("recovery_label", sa.String(length=8), nullable=True),
        sa.Column("strain", sa.Float(), nullable=True),
        sa.Column("sleep_need_min", sa.Float(), nullable=True),
        sa.Column("sleep_debt_min", sa.Float(), nullable=True),
        sa.Column("sleep_performance", sa.Float(), nullable=True),
        sa.Column("sleep_consistency", sa.Float(), nullable=True),
        sa.Column("hr_rest_used", sa.Float(), nullable=True),
        sa.Column("hr_max_used", sa.Float(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("day"),
    )


def downgrade() -> None:
    op.drop_table("daily_scores")
