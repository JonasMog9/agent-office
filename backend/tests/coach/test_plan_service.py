from datetime import date, datetime, timedelta

import pytest
from sqlalchemy import select

from app.coach.plan_service import create_plan, todays_workout, usual_weekly_km, weekly_km
from app.db.models import DailyScore, Prediction, TrainingPlan, Workout
from app.db.session import SessionLocal

TODAY = date(2026, 10, 13)  # a Tuesday: the plan's first quality day


def add_runs(s, weeks_ago_start: int, weeks_ago_end: int, km: float) -> None:  # noqa: ANN001
    """Four runs a week of ``km``/4 each, between the two week offsets."""
    wid = 1000 * weeks_ago_start
    for w in range(weeks_ago_end, weeks_ago_start):
        for d in (1, 3, 5, 6):
            day = TODAY - timedelta(weeks=w, days=d)
            wid += 1
            s.add(
                Workout(
                    id=wid,
                    sport_type="Run",
                    name="run",
                    start_at=datetime(day.year, day.month, day.day, 7),
                    day=day,
                    distance_m=km / 4 * 1000,
                    moving_s=km / 4 * 360,
                    summary={},
                )
            )


@pytest.mark.usefixtures("db")
def test_injury_return_plan_from_my_own_data_adapts_to_a_red_day() -> None:
    with SessionLocal() as s:
        add_runs(s, 20, 6, 35)  # normal training until 6 weeks ago
        add_runs(s, 3, 0, 12)  # careful running for the last 3 weeks
        s.add(
            Prediction(
                day=TODAY, distance="5K", predicted_s=23 * 60, confidence="medium", details={}
            )
        )
        s.commit()
        assert weekly_km(s, TODAY) == pytest.approx(9, abs=0.1)  # 3 weeks of 12 over 4 weeks
        assert usual_weekly_km(s, TODAY) == pytest.approx(35, abs=0.1)

        plan = create_plan(s, TODAY, returning_from_injury=True)
        assert plan.params["vdot"] == pytest.approx(42.2, abs=0.3)  # a 23:00 5K
        first = plan.plan["weeks"][0]
        assert first["phase"] == "return" and first["km"] == 10  # 70% of 9 → the 10 km floor

        # The plan's first week is all easy, so make today a hard day to see it adapt.
        hard = {
            "day": TODAY.isoformat(),
            "kind": "threshold",
            "km": 6.0,
            "description": "6 km threshold",
        }
        plan.plan = {"weeks": [{**first, "workouts": [hard]}], "notes": []}
        s.commit()
        s.add(DailyScore(day=TODAY, recovery=20, recovery_label="red", acwr=1.0, details={}))
        s.commit()

        today = todays_workout(s, TODAY)
        assert today["planned"]["kind"] == "threshold"
        assert today["today"]["kind"] == "easy" and "red" in today["notes"][0]
        assert todays_workout(s, TODAY, pain=True)["today"]["kind"] == "rest"


@pytest.mark.usefixtures("db")
def test_new_plan_retires_the_old_one_and_works_without_predictions() -> None:
    with SessionLocal() as s:
        create_plan(s, TODAY)
        second = create_plan(s, TODAY, race_distance="10K", race_date=TODAY + timedelta(weeks=10))
        active = s.scalars(select(TrainingPlan).where(TrainingPlan.active)).all()
        assert [p.id for p in active] == [second.id]
        assert "no prediction yet" in second.params["vdot_source"]
        assert todays_workout(s, TODAY + timedelta(weeks=20))["today"] is None
