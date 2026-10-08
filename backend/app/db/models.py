"""SQLAlchemy models.

Health data lands in three layers:

- ``raw_payloads``: every request body exactly as received, for debugging and re-parsing.
- ``health_samples``: one row per Apple Health sample, unique on (metric, start, end, category),
  so resending the same samples never duplicates them.
- ``daily_metrics``: one row per day, recomputed from ``health_samples`` whenever a day changes.
"""

from datetime import date, datetime

from sqlalchemy import JSON, Date, DateTime, Float, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class RawPayload(Base):
    __tablename__ = "raw_payloads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(32))
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    body: Mapped[dict] = mapped_column(JSON)


class HealthSample(Base):
    __tablename__ = "health_samples"
    __table_args__ = (
        UniqueConstraint("metric", "start_at", "end_at", "category", name="uq_health_sample"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    metric: Mapped[str] = mapped_column(String(32), index=True)
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    # Numeric samples fill value; sleep samples fill category ("deep", "rem", ...) instead.
    # category is "" rather than NULL for numeric samples so the unique constraint applies.
    value: Mapped[float | None] = mapped_column(Float)
    category: Mapped[str] = mapped_column(String(16), default="")
    # The day this sample counts toward, in the phone's local time (see ingest.shortcut).
    day: Mapped[date] = mapped_column(Date, index=True)


class DailyMetric(Base):
    __tablename__ = "daily_metrics"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    hrv_sdnn_ms: Mapped[float | None] = mapped_column(Float)
    resting_hr_bpm: Mapped[float | None] = mapped_column(Float)
    respiratory_rate_bpm: Mapped[float | None] = mapped_column(Float)
    wrist_temp_c: Mapped[float | None] = mapped_column(Float)
    active_energy_kcal: Mapped[float | None] = mapped_column(Float)
    vo2max: Mapped[float | None] = mapped_column(Float)
    ground_contact_ms: Mapped[float | None] = mapped_column(Float)
    vertical_oscillation_cm: Mapped[float | None] = mapped_column(Float)
    stride_length_m: Mapped[float | None] = mapped_column(Float)
    sleep_asleep_min: Mapped[float | None] = mapped_column(Float)
    sleep_core_min: Mapped[float | None] = mapped_column(Float)
    sleep_deep_min: Mapped[float | None] = mapped_column(Float)
    sleep_rem_min: Mapped[float | None] = mapped_column(Float)
    sleep_awake_min: Mapped[float | None] = mapped_column(Float)
    sleep_in_bed_min: Mapped[float | None] = mapped_column(Float)
    sleep_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    sleep_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
