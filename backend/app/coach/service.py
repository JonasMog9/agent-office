"""Store coach outputs that are worth keeping over time (race predictions, fitness)."""

from collections.abc import Iterable
from datetime import date, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.coach.fitness import WINDOW_DAYS, Segment, fitness, segments
from app.coach.ml.model import predict_marathon
from app.coach.predict import RUN_TYPES, predict_races
from app.config import get_settings
from app.db.models import DailyMetric, DailyScore, Prediction, Workout
from app.db.upsert import insert_for

VO2MAX_MAX_AGE_DAYS = 30
# Steady segments per run, keyed by (workout id, updated_at). Cutting segments means reading
# the full streams, so it's done once per run version instead of on every recompute.
_segment_cache: dict[tuple, list[Segment]] = {}


def run_segments(session: Session, since: date, until: date) -> list[Segment]:
    keys = session.execute(
        select(Workout.id, Workout.updated_at).where(
            Workout.sport_type.in_(RUN_TYPES), Workout.day.between(since, until)
        )
    ).all()
    missing = [wid for wid, updated in keys if (wid, updated) not in _segment_cache]
    for wid, day, streams, updated in session.execute(
        select(Workout.id, Workout.day, Workout.streams, Workout.updated_at)
        .where(Workout.id.in_(missing))
        .execution_options(yield_per=20)
    ):
        _segment_cache[(wid, updated)] = segments(wid, day, streams or {})
    return [seg for key in keys for seg in _segment_cache.get(tuple(key), [])]


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
    segs = run_segments(session, days[0] - timedelta(days=WINDOW_DAYS), days[-1])
    hr = {
        d: (rest, mx)
        for d, rest, mx in session.execute(
            select(DailyScore.day, DailyScore.hr_rest_used, DailyScore.hr_max_used).where(
                DailyScore.day.between(days[0], days[-1])
            )
        )
    }
    male = get_settings().athlete_sex == "male"
    for day in days:
        recent = [v for d, v in vo2 if day - timedelta(days=VO2MAX_MAX_AGE_DAYS) < d <= day]
        fit = fitness(segs, *hr.get(day, (None, None)), day)
        ml = predict_marathon(runs, day, male)
        predictions = predict_races(runs, recent[-1] if recent else None, day, fit.value, ml)
        for distance, result in predictions.items():
            rng = next((c for c in result.components if c.name == "range"), None)
            values = {
                "predicted_s": result.value,
                "low_s": rng.value if rng else None,
                "high_s": rng.baseline if rng else None,
                "confidence": result.label,
                "details": result.as_dict() | {"fitness": fit.as_dict()},
            }
            stmt = insert_for(session, Prediction).values(day=day, distance=distance, **values)
            session.execute(
                stmt.on_conflict_do_update(
                    index_elements=["day", "distance"], set_=values | {"updated_at": func.now()}
                )
            )
    return len(days)
