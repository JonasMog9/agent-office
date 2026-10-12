"""Race predictions per day and distance.

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "predictions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("distance", sa.String(length=16), nullable=False),
        sa.Column("predicted_s", sa.Float(), nullable=True),
        sa.Column("low_s", sa.Float(), nullable=True),
        sa.Column("high_s", sa.Float(), nullable=True),
        sa.Column("confidence", sa.String(length=8), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("day", "distance", name="uq_prediction"),
    )
    op.create_index("ix_predictions_day", "predictions", ["day"])


def downgrade() -> None:
    op.drop_index("ix_predictions_day", table_name="predictions")
    op.drop_table("predictions")
