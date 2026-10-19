"""Market Scout: scans, rug-test cache, alerts.

Revision ID: 0009
Revises: 0008
Create Date: 2026-10-19
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "scout_scans",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("ran_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("pools_seen", sa.Integer(), nullable=False),
        sa.Column("young", sa.Integer(), nullable=False),
        sa.Column("screened", sa.Integer(), nullable=False),
        sa.Column("alerts", sa.Integer(), nullable=False),
        sa.Column("near_misses", sa.JSON(), nullable=False),
        sa.Column("errors", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scout_scans_ran_at", "scout_scans", ["ran_at"])
    op.create_table(
        "scout_checks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain", sa.String(length=16), nullable=False),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain", "token_address", name="uq_scout_checks_token"),
    )
    op.create_table(
        "scout_alerts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("chain", sa.String(length=16), nullable=False),
        sa.Column("token_address", sa.String(length=64), nullable=False),
        sa.Column("pool_address", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=32), nullable=False),
        sa.Column("alerted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_usd", sa.Float(), nullable=True),
        sa.Column("fdv_usd", sa.Float(), nullable=True),
        sa.Column("liquidity_usd", sa.Float(), nullable=True),
        sa.Column("volume_h24_usd", sa.Float(), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("chain", "token_address", name="uq_scout_alerts_token"),
    )
    op.create_index("ix_scout_alerts_alerted_at", "scout_alerts", ["alerted_at"])


def downgrade() -> None:
    op.drop_index("ix_scout_alerts_alerted_at", table_name="scout_alerts")
    op.drop_table("scout_alerts")
    op.drop_table("scout_checks")
    op.drop_index("ix_scout_scans_ran_at", table_name="scout_scans")
    op.drop_table("scout_scans")
