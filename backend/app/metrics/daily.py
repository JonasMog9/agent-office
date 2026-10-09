"""Compute and store each day's scores from ``daily_metrics`` and ``workouts``.

This is the only part of ``metrics`` that touches the database: it gathers a day's inputs,
calls the pure scoring functions, and upserts one ``daily_scores`` row.

    recovery(d)     today's metrics vs the 60 days before d
    strain(d)       TRIMP of d's workouts
    sleep debt(d)   running balance over the 14 nights ending the morning of d
    performance(d)  last night's sleep vs the need computed the day before
    need(d)         sleep for the coming night: base + strain(d) + debt repayment

Because baselines look back, changing one day can change the next 60; ``days_affected_by``
returns that range so callers recompute what actually depends on a change.
"""

import logging
import threading
from collections.abc import Iterable
from datetime import date, timedelta
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import DailyMetric, DailyScore, Workout
from app.db.upsert import insert_for
from app.metrics.recovery import BASELINE_DAYS, recovery
from app.metrics.sleep import (
    DEBT_NIGHTS,
    DEBT_WINDOW,
    sleep_consistency,
    sleep_debt,
    sleep_need,
    sleep_performance,
)
from app.metrics.strain import daily_strain

log = logging.getLogger(__name__)
HR_MAX_WINDOW_DAYS = 365
HR_MAX_PERCENTILE = 0.99  # per workout, so a one-second optical spike doesn't set max HR
_METRIC_COLUMNS = [
    c.key for c in DailyMetric.__table__.columns if c.key not in ("day", "updated_at")
]
_recompute_lock = threading.Lock()
# Estimating max HR reads every stream of the past year, so it's cached until a workout changes.
_hr_max_cache: dict[date, float | None] = {}


def invalidate_hr_max() -> None:
    _hr_max_cache.clear()


def _row(m: DailyMetric | None) -> dict:
    return {c: getattr(m, c) for c in _METRIC_COLUMNS} if m else {}


def estimate_hr_max(session: Session, as_of: date) -> float | None:
    """Highest per-workout 99th-percentile heart rate in the past year, or the setting."""
    if get_settings().max_hr:
        return float(get_settings().max_hr)
    if as_of not in _hr_max_cache:
        _hr_max_cache.clear()
        _hr_max_cache[as_of] = _estimate_hr_max(session, as_of)
    return _hr_max_cache[as_of]


def _estimate_hr_max(session: Session, as_of: date) -> float | None:
    since = as_of - timedelta(days=HR_MAX_WINDOW_DAYS)
    best = None
    for streams, max_hr in session.execute(
        select(Workout.streams, Workout.max_hr).where(Workout.day.between(since, as_of))
    ):
        hr = sorted(v for v in (streams or {}).get("heartrate", []) if v)
        if hr:
            peak = hr[min(len(hr) - 1, int(len(hr) * HR_MAX_PERCENTILE))]
        elif max_hr:
            peak = max_hr
        else:
            continue
        best = peak if best is None else max(best, peak)
    return float(best) if best else None


def _strain_for(session: Session, day: date, hr_rest: float | None, hr_max: float | None):
    workouts = session.scalars(select(Workout).where(Workout.day == day)).all()
    rows = [
        {
            "sport_type": w.sport_type,
            "name": w.name,
            "streams": w.streams,
            "avg_hr": w.avg_hr,
            "moving_s": w.moving_s,
        }
        for w in workouts
    ]
    return daily_strain(rows, hr_rest, hr_max, get_settings().athlete_sex)


def compute_day(session: Session, day: date, hr_max: float | None) -> dict:
    """All of ``day``'s scores and their breakdowns, as ``daily_scores`` column values."""
    base_need = get_settings().sleep_need_min
    since = day - timedelta(days=BASELINE_DAYS + DEBT_WINDOW)
    metrics = {
        m.day: _row(m)
        for m in session.scalars(select(DailyMetric).where(DailyMetric.day.between(since, day)))
    }
    today = metrics.get(day, {})
    history = [metrics.get(day - timedelta(days=i), {}) for i in range(BASELINE_DAYS, 0, -1)]

    past_rhr = [h["resting_hr_bpm"] for h in history if h.get("resting_hr_bpm")]
    hr_rest = today.get("resting_hr_bpm") or (median(past_rhr) if past_rhr else None)

    rec = recovery(today, history, base_need)
    strain = _strain_for(session, day, hr_rest, hr_max)
    yesterday_strain = _strain_for(session, day - timedelta(days=1), hr_rest, hr_max)

    def asleep_nights(end: date) -> list:
        return [
            metrics.get(end - timedelta(days=i), {}).get("sleep_asleep_min")
            for i in range(DEBT_WINDOW - 1, -1, -1)
        ]

    debt = sleep_debt(asleep_nights(day), base_need)
    debt_before = sleep_debt(asleep_nights(day - timedelta(days=1)), base_need)
    need_last_night = sleep_need(base_need, yesterday_strain.value, debt_before.value)
    performance = sleep_performance(today.get("sleep_asleep_min"), need_last_night.value)
    consistency = sleep_consistency(
        [
            metrics.get(day - timedelta(days=i), {}).get("sleep_start")
            for i in range(DEBT_NIGHTS - 1, -1, -1)
        ]
    )
    need = sleep_need(base_need, strain.value, debt.value)

    return {
        "recovery": rec.value,
        "recovery_label": rec.label,
        "strain": strain.value,
        "sleep_need_min": need.value,
        "sleep_debt_min": debt.value,
        "sleep_performance": performance.value,
        "sleep_consistency": consistency.value,
        "hr_rest_used": hr_rest,
        "hr_max_used": hr_max,
        "details": {
            "recovery": rec.as_dict(),
            "strain": strain.as_dict(),
            "sleep_debt": debt.as_dict(),
            "sleep_need": need.as_dict(),
            "sleep_performance": performance.as_dict(),
            "sleep_consistency": consistency.as_dict(),
        },
    }


def recompute_scores(session: Session, days: Iterable[date]) -> int:
    days = sorted(set(days))
    if not days:
        return 0
    hr_max = estimate_hr_max(session, days[-1])
    for day in days:
        values = compute_day(session, day, hr_max)
        stmt = insert_for(session, DailyScore).values(day=day, **values)
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["day"], set_=values | {"updated_at": func.now()}
            )
        )
    session.commit()
    return len(days)


def safe_recompute(session: Session, days: Iterable[date]) -> None:
    """Recompute after an ingest without ever failing the ingest itself."""
    try:
        recompute_scores(session, days)
    except Exception:  # noqa: BLE001
        session.rollback()
        log.exception("Recomputing scores failed")


def days_affected_by(changed: Iterable[date], today: date | None = None) -> list[date]:
    """Every day whose scores can depend on a change to ``changed`` (baselines look back)."""
    today = today or date.today()
    out: set[date] = set()
    for d in set(changed):
        last = min(d + timedelta(days=BASELINE_DAYS), today)
        out.update(d + timedelta(days=i) for i in range((last - d).days + 1))
    return sorted(out)


def recompute_all(session_factory, days_back: int = 400) -> int:  # noqa: ANN001
    """Rebuild every score from scratch (startup, after imports). One run at a time."""
    if not _recompute_lock.acquire(blocking=False):
        return -1
    try:
        with session_factory() as session:
            first = session.scalar(select(func.min(DailyMetric.day)))
            if first is None:
                return 0
            start = max(first, date.today() - timedelta(days=days_back))
            days = [start + timedelta(days=i) for i in range((date.today() - start).days + 1)]
            n = recompute_scores(session, days)
            log.info("Recomputed scores for %d days", n)
            return n
    except Exception:  # noqa: BLE001  (never take the app down over a score)
        log.exception("Recomputing scores failed")
        return -1
    finally:
        _recompute_lock.release()
