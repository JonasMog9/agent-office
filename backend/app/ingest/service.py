"""Store Shortcut payloads and recompute the days they touch."""

from collections.abc import Iterable
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.db.models import DailyMetric, HealthSample, RawPayload
from app.ingest.daily import summarize_day
from app.ingest.shortcut import ParseResult, Sample, parse_payload


def _insert(session: Session, table):  # noqa: ANN001, ANN202
    """INSERT that supports ON CONFLICT on both Postgres (production) and SQLite (tests)."""
    return (pg_insert if session.get_bind().dialect.name == "postgresql" else sqlite_insert)(table)


def store_samples(session: Session, samples: Iterable[Sample]) -> None:
    for s in samples:
        stmt = _insert(session, HealthSample).values(
            metric=s.metric,
            start_at=s.start,
            end_at=s.end,
            value=s.value,
            category=s.category,
            day=s.day,
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=["metric", "start_at", "end_at", "category"],
                set_={"value": stmt.excluded.value, "day": stmt.excluded.day},
            )
        )


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
    recompute_days(session, (s.day for s in result.samples))
    session.commit()
    return result
