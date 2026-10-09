from datetime import UTC, date, datetime

import pytest
from sqlalchemy import select

from app.db.models import DailyMetric, HealthSample
from app.db.session import SessionLocal
from app.ingest.service import reassign_night_samples


def sample(start: str, end: str, day: date, metric: str = "sleep") -> HealthSample:
    return HealthSample(
        metric=metric,
        start_at=datetime.fromisoformat(start).astimezone(UTC),
        end_at=datetime.fromisoformat(end).astimezone(UTC),
        value=None if metric == "sleep" else 52.0,
        category="core" if metric == "sleep" else "",
        day=day,
    )


@pytest.mark.usefixtures("db")
def test_split_night_is_put_back_together() -> None:
    with SessionLocal() as s:
        s.add_all(
            [
                # Stored under the old "day it ends" rule: the 15 minutes before midnight
                # landed on Oct 4, the rest of the night on Oct 5.
                sample("2026-10-04T23:40:00-04:00", "2026-10-04T23:55:00-04:00", date(2026, 10, 4)),
                sample("2026-10-04T23:56:00-04:00", "2026-10-05T06:47:00-04:00", date(2026, 10, 5)),
                sample(
                    "2026-10-04T23:00:00-04:00",
                    "2026-10-04T23:01:00-04:00",
                    date(2026, 10, 4),
                    "hrv",
                ),
            ]
        )
        s.commit()
        assert reassign_night_samples(s, "America/New_York") == {
            date(2026, 10, 4),
            date(2026, 10, 5),
        }
        assert reassign_night_samples(s, "America/New_York") == set()  # idempotent

        days = {r.metric: r.day for r in s.scalars(select(HealthSample))}
        assert days["hrv"] == date(2026, 10, 4)  # day metrics are left alone
        oct5 = s.get(DailyMetric, date(2026, 10, 5))
        assert oct5.sleep_asleep_min == pytest.approx(15 + 411)
        assert s.get(DailyMetric, date(2026, 10, 4)).sleep_asleep_min is None
