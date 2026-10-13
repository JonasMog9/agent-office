"""Make a plan from your own data, store it, and hand out today's workout adjusted to today."""

from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.coach.plan import Workout, adjust, build_plan, plan_as_dict
from app.coach.predict import RUN_TYPES
from app.coach.vdot import vdot
from app.db.models import DailyScore, Prediction, TrainingPlan
from app.db.models import Workout as WorkoutRow

USUAL_LOOKBACK_WEEKS = 26
DEFAULT_VDOT = 40.0


def weekly_km(session: Session, end: date, weeks: int = 4) -> float:
    """Mean weekly running km over the ``weeks`` up to and including ``end``."""
    since = end - timedelta(weeks=weeks)
    total = session.scalars(
        select(WorkoutRow.distance_m).where(
            WorkoutRow.sport_type.in_(RUN_TYPES), WorkoutRow.day > since, WorkoutRow.day <= end
        )
    ).all()
    return sum(d or 0 for d in total) / 1000 / weeks


def usual_weekly_km(session: Session, today: date) -> float:
    """Your best 4-week average in the last 6 months: the volume to return to after a break."""
    return max(
        weekly_km(session, today - timedelta(weeks=w)) for w in range(USUAL_LOOKBACK_WEEKS - 3)
    )


def current_vdot(session: Session, today: date) -> tuple[float, str]:
    p = session.scalar(
        select(Prediction)
        .where(
            Prediction.distance == "5K",
            Prediction.day <= today,
            Prediction.predicted_s.is_not(None),
        )
        .order_by(Prediction.day.desc())
    )
    if p is None:
        return DEFAULT_VDOT, f"no prediction yet, paces assume VDOT {DEFAULT_VDOT:.0f}"
    return vdot(5000, p.predicted_s), f"from the {p.day} 5K prediction ({p.confidence} confidence)"


def create_plan(
    session: Session,
    today: date,
    *,
    race_distance: str | None = None,
    race_date: date | None = None,
    returning_from_injury: bool = False,
    runs_per_week: int = 4,
    weeks: int = 12,
) -> TrainingPlan:
    current = weekly_km(session, today)
    usual = usual_weekly_km(session, today)
    vdot_value, vdot_source = current_vdot(session, today)
    plan = build_plan(
        today,
        current,
        vdot_value,
        race_distance=race_distance,
        race_date=race_date,
        weeks=weeks,
        runs_per_week=runs_per_week,
        returning_from_injury=returning_from_injury,
        usual_weekly_km=usual,
    )
    params = {
        "current_weekly_km": round(current, 1),
        "usual_weekly_km": round(usual, 1),
        "vdot": round(vdot_value, 1),
        "vdot_source": vdot_source,
        "runs_per_week": runs_per_week,
        "returning_from_injury": returning_from_injury,
    }
    session.execute(update(TrainingPlan).where(TrainingPlan.active).values(active=False))
    row = TrainingPlan(
        race_distance=race_distance,
        race_date=race_date,
        params=params,
        plan=plan_as_dict(plan),
        active=True,
    )
    session.add(row)
    session.commit()
    return row


def active_plan(session: Session) -> TrainingPlan | None:
    return session.scalar(select(TrainingPlan).where(TrainingPlan.active))


def todays_workout(session: Session, today: date, pain: bool = False) -> dict | None:
    """Today's workout from the active plan, adjusted to today's recovery and load."""
    row = active_plan(session)
    if row is None:
        return None
    planned = next(
        (
            w
            for week in row.plan["weeks"]
            for w in week["workouts"]
            if w["day"] == today.isoformat()
        ),
        None,
    )
    if planned is None:
        return {"planned": None, "today": None, "notes": ["The plan doesn't cover today."]}
    score = session.get(DailyScore, today)
    workout = Workout(today, planned["kind"], planned["km"], planned["description"])
    adjusted = adjust(
        workout,
        score.recovery_label if score else None,
        score.acwr if score else None,
        pain=pain,
    )
    return {
        "planned": planned,
        "today": {"kind": adjusted.kind, "km": adjusted.km, "description": adjusted.description},
        "notes": adjusted.notes,
        "recovery": score.recovery_label if score else None,
        "acwr": score.acwr if score else None,
    }
