"""Store coach outputs that are worth keeping over time (race predictions)."""

from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.coach.predict import RUN_TYPES, predict_races
from app.db.models import DailyMetric, Prediction, Workout
from app.db.upsert import insert_for

VO2MAX_MAX_AGE_DAYS = 30


def update_predictions(session: Session, days: Iterable[date]) -> int:
    """Predict every race as of each of ``days`` (using only data up to that day) and upsert."""
    days = sorted(set(days))
    if not days:
        return 0
    runs = [
        {"day": d, "distance_m": dist, "moving_s": mv, "elapsed_s": el, "summary": summary}
        for d, dist, mv, el, summary in session.execute(
            select(
                Workout.day,
                Workout.distance_m,
                Workout.moving_s,
                Workout.elapsed_s,
                Workout.summary,
            ).where(Workout.sport_type.in_(RUN_TYPES), Workout.day <= days[-1])
        )
    ]
    vo2 = sorted(
        session.execute(
            select(DailyMetric.day, DailyMetric.vo2max).where(DailyMetric.vo2max.is_not(None))
        ).all()
    )
    for day in days:
        recent = [v for d, v in vo2 if day - timedelta(days=VO2MAX_MAX_AGE_DAYS) < d <= day]
        for distance, result in predict_races(runs, recent[-1] if recent else None, day).items():
            rng = next((c for c in result.components if c.name == "range"), None)
            values = {
                "predicted_s": result.value,
                "low_s": rng.value if rng else None,
                "high_s": rng.baseline if rng else None,
                "confidence": result.label,
                "details": result.as_dict(),
            }
            stmt = insert_for(session, Prediction).values(day=day, distance=distance, **values)
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["day", "distance"], set_=values | {"updated_at": func.now()}
                )
            )
    return len(days)
