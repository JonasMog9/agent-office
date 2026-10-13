"""Training plans.

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-13
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "training_plans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("race_distance", sa.String(length=16), nullable=True),
        sa.Column("race_date", sa.Date(), nullable=True),
        sa.Column("params", sa.JSON(), nullable=False),
        sa.Column("plan", sa.JSON(), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_training_plans_active", "training_plans", ["active"])


def downgrade() -> None:
    op.drop_index("ix_training_plans_active", table_name="training_plans")
    op.drop_table("training_plans")
