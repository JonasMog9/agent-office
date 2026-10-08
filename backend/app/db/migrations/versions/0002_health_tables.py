"""Health tables: raw_payloads, health_samples, daily_metrics.

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-08
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: str | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "daily_metrics",
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("hrv_sdnn_ms", sa.Float(), nullable=True),
        sa.Column("resting_hr_bpm", sa.Float(), nullable=True),
        sa.Column("respiratory_rate_bpm", sa.Float(), nullable=True),
        sa.Column("wrist_temp_c", sa.Float(), nullable=True),
        sa.Column("active_energy_kcal", sa.Float(), nullable=True),
        sa.Column("vo2max", sa.Float(), nullable=True),
        sa.Column("ground_contact_ms", sa.Float(), nullable=True),
        sa.Column("vertical_oscillation_cm", sa.Float(), nullable=True),
        sa.Column("stride_length_m", sa.Float(), nullable=True),
        sa.Column("sleep_asleep_min", sa.Float(), nullable=True),
        sa.Column("sleep_core_min", sa.Float(), nullable=True),
        sa.Column("sleep_deep_min", sa.Float(), nullable=True),
        sa.Column("sleep_rem_min", sa.Float(), nullable=True),
        sa.Column("sleep_awake_min", sa.Float(), nullable=True),
        sa.Column("sleep_in_bed_min", sa.Float(), nullable=True),
        sa.Column("sleep_start", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sleep_end", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("day"),
    )
    op.create_table(
        "health_samples",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("metric", sa.String(length=32), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("category", sa.String(length=16), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("metric", "start_at", "end_at", "category", name="uq_health_sample"),
    )
    op.create_index(op.f("ix_health_samples_day"), "health_samples", ["day"], unique=False)
    op.create_index(op.f("ix_health_samples_metric"), "health_samples", ["metric"], unique=False)
    op.create_table(
        "raw_payloads",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column(
            "received_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("body", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )


def downgrade() -> None:
    op.drop_table("raw_payloads")
    op.drop_index(op.f("ix_health_samples_metric"), table_name="health_samples")
    op.drop_index(op.f("ix_health_samples_day"), table_name="health_samples")
    op.drop_table("health_samples")
    op.drop_table("daily_metrics")
