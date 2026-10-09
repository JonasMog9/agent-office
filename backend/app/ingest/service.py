"""Store Shortcut payloads and recompute the days they touch."""

from collections.abc import Iterable
from datetime import UTC, date
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import DailyMetric, HealthSample, RawPayload
from app.db.upsert import insert_for as _insert
from app.ingest.daily import summarize_day
from app.ingest.shortcut import NIGHT_METRICS, ParseResult, Sample, parse_payload, sample_day
from app.metrics.daily import days_affected_by, safe_recompute


def store_samples(session: Session, samples: Iterable[Sample], batch_size: int = 1000) -> None:
    """Upsert samples in multi-row batches (the Apple Health export can hold ~10^5 of them)."""
    batch: dict[tuple, dict] = {}

    def flush() -> None:
        if not batch:
            return
        stmt = _insert(session, HealthSample).values(list(batch.values()))
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["metric", "start_at", "end_at", "category"],
                set_={"value": stmt.excluded.value, "day": stmt.excluded.day},
            )
        )
        batch.clear()

    for s in samples:
        # A key may appear only once per statement (Postgres rejects updating a row twice),
        # so duplicates inside one batch collapse to the last one, as sequential upserts would.
        key = (s.metric, s.start, s.end, s.category)
        batch[key] = {
            "metric": s.metric,
            "start_at": s.start,
            "end_at": s.end,
            "value": s.value,
            "category": s.category,
            "day": s.day,
        }
        if len(batch) >= batch_size:
            flush()
    flush()


def recompute_days(session: Session, days: Iterable[date]) -> None:
    for day in sorted(set(days)):
        rows = session.scalars(select(HealthSample).where(HealthSample.day == day)).all()
        summary = summarize_day(
            Sample(r.metric, r.start_at, r.end_at, r.value, r.category, r.day) for r in rows
        )
        stmt = _insert(session, DailyMetric).values(day=day, **summary)
        # ORM onupdate defaults don't fire for ON CONFLICT DO UPDATE, so set updated_at here.
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["day"], set_={**summary, "updated_at": func.now()}
            )
        )


def ingest_shortcut_payload(session: Session, body: dict) -> ParseResult:
    session.add(RawPayload(source="shortcut", body=body))
    result = parse_payload(body)
    store_samples(session, result.samples)
    days = {s.day for s in result.samples}
    recompute_days(session, days)
    session.commit()
    safe_recompute(session, days_affected_by(days))
    return result


def reassign_night_samples(session: Session, timezone: str) -> set[date]:
    """Move stored night samples to the day the current rule gives them; recompute those days.

    Postgres keeps timestamps in UTC and drops the offset they arrived with, so the home
    ``timezone`` stands in for it. Idempotent: once every sample is on its day, nothing moves.
    """
    tz = ZoneInfo(timezone)
    changed: set[date] = set()
    rows = session.scalars(select(HealthSample).where(HealthSample.metric.in_(NIGHT_METRICS)))
    for r in rows:
        start = r.start_at if r.start_at.tzinfo else r.start_at.replace(tzinfo=UTC)
        end = r.end_at if r.end_at.tzinfo else r.end_at.replace(tzinfo=UTC)
        day = sample_day(r.metric, start.astimezone(tz), end.astimezone(tz))
        if day != r.day:
            changed |= {r.day, day}
            r.day = day
    if changed:
        session.flush()
        recompute_days(session, changed)
    session.commit()
    return changed
