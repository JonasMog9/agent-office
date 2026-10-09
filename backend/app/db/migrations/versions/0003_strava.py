"""Strava: strava_tokens and workouts.

Revision ID: 0003
Revises: 0002
Create Date: 2026-10-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003"
down_revision: str | None = "0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "strava_tokens",
        sa.Column("athlete_id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("access_token", sa.String(length=128), nullable=False),
        sa.Column("refresh_token", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.BigInteger(), nullable=False),
        sa.Column("scope", sa.String(length=128), nullable=False),
        sa.Column("subscription_id", sa.BigInteger(), nullable=True),
        sa.Column("backfill_status", sa.String(length=64), nullable=False),
        sa.Column("backfill_imported", sa.Integer(), nullable=False),
        sa.Column("backfill_error", sa.Text(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("athlete_id"),
    )
    op.create_table(
        "workouts",
        sa.Column("id", sa.BigInteger(), autoincrement=False, nullable=False),
        sa.Column("source", sa.String(length=16), nullable=False),
        sa.Column("sport_type", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("elapsed_s", sa.Integer(), nullable=True),
        sa.Column("moving_s", sa.Integer(), nullable=True),
        sa.Column("distance_m", sa.Float(), nullable=True),
        sa.Column("elevation_gain_m", sa.Float(), nullable=True),
        sa.Column("avg_hr", sa.Float(), nullable=True),
        sa.Column("max_hr", sa.Float(), nullable=True),
        sa.Column("avg_speed_mps", sa.Float(), nullable=True),
        sa.Column("avg_cadence", sa.Float(), nullable=True),
        sa.Column("avg_watts", sa.Float(), nullable=True),
        sa.Column("calories", sa.Float(), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=False),
        sa.Column("streams", sa.JSON(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_workouts_day"), "workouts", ["day"], unique=False)
    op.create_index(op.f("ix_workouts_sport_type"), "workouts", ["sport_type"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_workouts_sport_type"), table_name="workouts")
    op.drop_index(op.f("ix_workouts_day"), table_name="workouts")
    op.drop_table("workouts")
    op.drop_table("strava_tokens")
