"""SQLAlchemy models.

Health data lands in three layers:

- ``raw_payloads``: every request body exactly as received, for debugging and re-parsing.
- ``health_samples``: one row per Apple Health sample, unique on (metric, start, end, category),
  so resending the same samples never duplicates them.
- ``daily_metrics``: one row per day, recomputed from ``health_samples`` whenever a day changes.

Workouts come from Strava: ``strava_tokens`` holds the owner's OAuth tokens (refreshed and
rotated by the app) and ``workouts`` one row per activity, with its second-by-second streams.
"""

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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


class StravaToken(Base):
    """The owner's Strava OAuth tokens plus webhook and backfill bookkeeping. One row."""

    __tablename__ = "strava_tokens"

    athlete_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    access_token: Mapped[str] = mapped_column(String(128))
    refresh_token: Mapped[str] = mapped_column(String(128))
    expires_at: Mapped[int] = mapped_column(BigInteger)  # epoch seconds, as Strava returns it
    scope: Mapped[str] = mapped_column(String(128), default="")
    subscription_id: Mapped[int | None] = mapped_column(BigInteger)
    backfill_status: Mapped[str] = mapped_column(String(64), default="not started")
    backfill_imported: Mapped[int] = mapped_column(Integer, default=0)
    backfill_error: Mapped[str | None] = mapped_column(Text)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Workout(Base):
    """One Strava activity. Strava is the source of truth for workouts (see CLAUDE.md)."""

    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    source: Mapped[str] = mapped_column(String(16), default="strava")
    sport_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    day: Mapped[date] = mapped_column(Date, index=True)  # local date where the activity started
    elapsed_s: Mapped[int | None] = mapped_column(Integer)
    moving_s: Mapped[int | None] = mapped_column(Integer)
    distance_m: Mapped[float | None] = mapped_column(Float)
    elevation_gain_m: Mapped[float | None] = mapped_column(Float)
    avg_hr: Mapped[float | None] = mapped_column(Float)
    max_hr: Mapped[float | None] = mapped_column(Float)
    avg_speed_mps: Mapped[float | None] = mapped_column(Float)
    avg_cadence: Mapped[float | None] = mapped_column(Float)
    avg_watts: Mapped[float | None] = mapped_column(Float)
    calories: Mapped[float | None] = mapped_column(Float)
    summary: Mapped[dict] = mapped_column(
        JSON
    )  # the full Strava activity, incl. splits and best efforts
    streams: Mapped[dict | None] = mapped_column(JSON)  # {"heartrate": [...], "time": [...], ...}
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class DailyScore(Base):
    """Recovery, strain, sleep and training load for one day, recomputed as inputs change.

    ``details`` holds every score's component breakdown (the "reasons") for the agents.
    """

    __tablename__ = "daily_scores"

    day: Mapped[date] = mapped_column(Date, primary_key=True)
    recovery: Mapped[float | None] = mapped_column(Float)
    recovery_label: Mapped[str | None] = mapped_column(String(8))
    strain: Mapped[float | None] = mapped_column(Float)
    sleep_need_min: Mapped[float | None] = mapped_column(Float)  # for the coming night
    sleep_debt_min: Mapped[float | None] = mapped_column(Float)
    sleep_performance: Mapped[float | None] = mapped_column(Float)  # last night, % of need
    sleep_consistency: Mapped[float | None] = mapped_column(Float)
    hr_rest_used: Mapped[float | None] = mapped_column(Float)
    hr_max_used: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON)
    # Training load (coach.load): rebuilt over the whole history whenever scores change.
    trimp: Mapped[float | None] = mapped_column(Float)
    ctl: Mapped[float | None] = mapped_column(Float)  # fitness
    atl: Mapped[float | None] = mapped_column(Float)  # fatigue
    form: Mapped[float | None] = mapped_column(Float)  # yesterday's CTL − ATL
    acwr: Mapped[float | None] = mapped_column(Float)
    load_details: Mapped[dict | None] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Prediction(Base):
    """A race prediction as of one day, one row per distance. Kept so predictions can be
    charted over time and compared with real races later."""

    __tablename__ = "predictions"
    __table_args__ = (UniqueConstraint("day", "distance", name="uq_prediction"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    distance: Mapped[str] = mapped_column(String(16))  # "5K", "10K", "half marathon", "marathon"
    predicted_s: Mapped[float | None] = mapped_column(Float)
    low_s: Mapped[float | None] = mapped_column(Float)
    high_s: Mapped[float | None] = mapped_column(Float)
    confidence: Mapped[str | None] = mapped_column(String(8))
    details: Mapped[dict] = mapped_column(JSON)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class TrainingPlan(Base):
    """A generated training plan. Only one is active; making a new one retires the old."""

    __tablename__ = "training_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    race_distance: Mapped[str | None] = mapped_column(String(16))
    race_date: Mapped[date | None] = mapped_column(Date)
    params: Mapped[dict] = mapped_column(JSON)  # the inputs it was built from
    plan: Mapped[dict] = mapped_column(JSON)  # coach.plan.plan_as_dict output
    active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)


class AppState(Base):
    """Small key/value facts the app must remember across restarts (e.g. last morning push)."""

    __tablename__ = "app_state"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(String(255))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ScoutScan(Base):
    """One Market Scout scan: how much it looked at and what came close, for "anything up?"."""

    __tablename__ = "scout_scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ran_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    pools_seen: Mapped[int] = mapped_column(Integer)
    young: Mapped[int] = mapped_column(Integer)  # pools at most 48 h old
    screened: Mapped[int] = mapped_column(Integer)  # passed the market screen
    alerts: Mapped[int] = mapped_column(Integer)
    near_misses: Mapped[list] = mapped_column(JSON)  # best young pools and the rules they failed
    errors: Mapped[list] = mapped_column(JSON)


class ScoutCheck(Base):
    """A rug test run on one token (cached so a scan doesn't re-ask the API every 10 minutes)."""

    __tablename__ = "scout_checks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain: Mapped[str] = mapped_column(String(16))
    token_address: Mapped[str] = mapped_column(String(64))
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    passed: Mapped[bool] = mapped_column(Boolean)
    details: Mapped[dict] = mapped_column(JSON)  # the rug ScoreResult

    __table_args__ = (UniqueConstraint("chain", "token_address", name="uq_scout_checks_token"),)


class ScoutAlert(Base):
    """A potential runner the owner was told about. One per token, ever."""

    __tablename__ = "scout_alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    chain: Mapped[str] = mapped_column(String(16))
    token_address: Mapped[str] = mapped_column(String(64))
    pool_address: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32))
    alerted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    # Market numbers when alerted, so later we can check how the call played out.
    price_usd: Mapped[float | None] = mapped_column(Float)
    fdv_usd: Mapped[float | None] = mapped_column(Float)
    liquidity_usd: Mapped[float | None] = mapped_column(Float)
    volume_h24_usd: Mapped[float | None] = mapped_column(Float)
    details: Mapped[dict] = mapped_column(JSON)  # screen + rug breakdowns
    message: Mapped[str] = mapped_column(Text, default="")

    __table_args__ = (UniqueConstraint("chain", "token_address", name="uq_scout_alerts_token"),)


class PaperTrade(Base):
    """A pretend trade on one alert: no real money. See app/scout/paper.py for the rules."""

    __tablename__ = "paper_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alert_id: Mapped[int] = mapped_column(Integer, unique=True)
    chain: Mapped[str] = mapped_column(String(16))
    pool_address: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(32))
    opened_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    stake_usd: Mapped[float] = mapped_column(Float)
    entry_price: Mapped[float] = mapped_column(Float)
    last_price: Mapped[float | None] = mapped_column(Float)
    peak_price: Mapped[float | None] = mapped_column(Float)
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    exit_price: Mapped[float | None] = mapped_column(Float)
    exit_reason: Mapped[str | None] = mapped_column(String(32))
    pnl_usd: Mapped[float | None] = mapped_column(Float)
