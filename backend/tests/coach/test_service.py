from datetime import date, datetime

import pytest
from sqlalchemy import select

from app.coach.service import update_predictions
from app.db.models import DailyMetric, Prediction, Workout
from app.db.session import SessionLocal

DAY = date(2026, 10, 12)


@pytest.mark.usefixtures("db")
def test_predictions_are_stored_per_day_and_use_only_earlier_data() -> None:
    with SessionLocal() as s:
        s.add(DailyMetric(day=date(2026, 10, 1), vo2max=50.0))
        s.add(
            Workout(
                id=1,
                sport_type="Run",
                name="Parkrun",
                start_at=datetime(2026, 10, 10, 9),
                day=date(2026, 10, 10),
                distance_m=5000,
                moving_s=19 * 60 + 57,
                summary={"workout_type": 1, "name": "Parkrun"},
            )
        )
        s.commit()
        update_predictions(s, [date(2026, 10, 9), DAY])
        update_predictions(s, [DAY])  # upsert, no duplicates
        s.commit()
        rows = {(p.day, p.distance): p for p in s.scalars(select(Prediction))}
    assert len(rows) == 8
    before, after = rows[(date(2026, 10, 9), "5K")], rows[(DAY, "5K")]
    assert before.confidence == "low" and after.confidence == "high"  # the race is on Oct 10
    assert after.low_s <= after.predicted_s <= after.high_s
    assert {c["name"] for c in after.details["components"]} >= {"VDOT", "Riegel", "VO2max"}
