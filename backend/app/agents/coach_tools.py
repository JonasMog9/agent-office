"""The Health Coach's tools: each reads computed numbers from the database and returns them.

Nothing here asks the model for a number. Every value comes from ``metrics`` / ``coach``
(stored in ``daily_scores``, ``predictions`` and ``training_plans``) with its breakdown, so the
coach can explain where it came from.
"""

from collections.abc import Callable
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.loop import Tool
from app.coach import plan_service
from app.coach.warnings import warnings_for
from app.coach.zones import format_pace, hr_zones, pace_zones
from app.config import get_settings
from app.db.models import DailyMetric, DailyScore, Prediction, Workout

DATE = {
    "type": "string",
    "description": "Day as YYYY-MM-DD, or 'today' (the owner's local date).",
}
RACES = ["5K", "10K", "half marathon", "marathon"]


def today() -> date:
    return datetime.now(ZoneInfo(get_settings().timezone)).date()


def _day(value: str) -> date:
    if not value or value.lower() == "today":
        return today()
    if value.lower() == "yesterday":
        return today() - timedelta(days=1)
    return date.fromisoformat(value)


def _score(session: Session, day: date) -> DailyScore:
    score = session.get(DailyScore, day)
    if score is None:
        raise LookupError(f"No scores stored for {day} yet (has today's health sync run?).")
    return score


def _brief(result: dict | None) -> dict | None:
    """A ScoreResult dict without empty fields, to keep tool output small."""
    if not result:
        return None
    comps = [
        {k: v for k, v in c.items() if v not in (None, "")} for c in result.get("components", [])
    ]
    return {
        "value": result.get("value"),
        "label": result.get("label"),
        "components": comps,
        "notes": result.get("notes", []),
    }


def get_recovery(session: Session, args: dict) -> dict:
    day = _day(args["date"])
    s = _score(session, day)
    return {
        "date": day,
        "recovery": s.recovery,
        "label": s.recovery_label,
        "breakdown": _brief(s.details.get("recovery")),
    }


def get_sleep(session: Session, args: dict) -> dict:
    day = _day(args["date"])
    s = _score(session, day)
    m = session.get(DailyMetric, day)
    return {
        "date": day,
        "asleep_last_night_min": m.sleep_asleep_min if m else None,
        "sleep_performance_pct": s.sleep_performance,
        "sleep_need_tonight_min": s.sleep_need_min,
        "sleep_debt_min": s.sleep_debt_min,
        "consistency": s.sleep_consistency,
        "need_breakdown": _brief(s.details.get("sleep_need")),
        "note": s.details.get("sleep_ignored"),
    }


def get_strain(session: Session, args: dict) -> dict:
    day = _day(args["date"])
    s = _score(session, day)
    workouts = session.execute(
        select(
            Workout.sport_type, Workout.name, Workout.moving_s, Workout.distance_m, Workout.avg_hr
        ).where(Workout.day == day)
    ).all()
    return {
        "date": day,
        "strain_0_21": s.strain,
        "trimp": s.trimp,
        "workouts": [
            {
                "type": t,
                "name": n,
                "minutes": round((mv or 0) / 60),
                "km": round((d or 0) / 1000, 1),
                "avg_hr": hr,
            }
            for t, n, mv, d, hr in workouts
        ],
        "breakdown": _brief(s.details.get("strain")),
    }


def get_training_load(session: Session, args: dict) -> dict:
    day = _day(args["date"])
    s = _score(session, day)
    return {
        "date": day,
        "fitness_ctl": s.ctl,
        "fatigue_atl": s.atl,
        "form": s.form,
        "acwr": s.acwr,
        "flags": (s.load_details or {}).get("notes", []),
        "weekly_km_last_4_weeks": round(plan_service.weekly_km(session, day), 1),
    }


def get_trend(session: Session, args: dict) -> dict:
    days = max(1, min(int(args["days"]), 60))
    end = today()
    rows = session.scalars(
        select(DailyScore)
        .where(DailyScore.day > end - timedelta(days=days))
        .order_by(DailyScore.day)
    ).all()
    return {
        "days": [
            {
                "date": r.day,
                "recovery": r.recovery,
                "label": r.recovery_label,
                "strain": r.strain,
                "sleep_debt_min": r.sleep_debt_min,
                "form": r.form,
                "acwr": r.acwr,
            }
            for r in rows
        ]
    }


def predict_race(session: Session, args: dict) -> dict:
    distance = args["distance"]
    p = session.scalar(
        select(Prediction).where(Prediction.distance == distance).order_by(Prediction.day.desc())
    )
    if p is None:
        raise LookupError("No predictions stored yet.")
    return {
        "as_of": p.day,
        "distance": distance,
        "predicted": format_time(p.predicted_s),
        "fastest": format_time(p.low_s),
        "slowest": format_time(p.high_s),
        "confidence": p.confidence,
        "methods": [
            {
                "method": c["name"],
                "time": format_time(c["value"]) if c["name"] != "range" else None,
                "note": c.get("note"),
            }
            for c in p.details.get("components", [])
            if c["name"] != "range"
        ],
        "notes": p.details.get("notes", []),
        "fitness_model": _brief(p.details.get("fitness")),
    }


def format_time(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    s = round(seconds)
    return (
        f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    )


def get_zones(session: Session, args: dict) -> dict:
    day = today()
    s = session.scalar(
        select(DailyScore)
        .where(DailyScore.hr_max_used.is_not(None))
        .order_by(DailyScore.day.desc())
    )
    vdot_value, source = plan_service.current_vdot(session, day)
    zones = hr_zones(s.hr_rest_used, s.hr_max_used).as_dict() if s else None
    return {
        "heart_rate_zones": [
            {"zone": c["name"], "from_bpm": c["value"], "to_bpm": c["baseline"]}
            for c in (zones or {}).get("components", [])
        ],
        "vdot": round(vdot_value, 1),
        "vdot_source": source,
        "pace_zones_per_km": [
            {
                "zone": z.name,
                "fast": format_pace(z.fast_s_per_km),
                "slow": format_pace(z.slow_s_per_km),
            }
            for z in pace_zones(vdot_value)
        ],
    }


def get_plan(session: Session, args: dict) -> dict:
    day = today()
    workout = plan_service.todays_workout(session, day, pain=bool(args["pain"]))
    if workout is None:
        return {"plan": None, "note": "No training plan yet. Offer to make one with adjust_plan."}
    row = plan_service.active_plan(session)
    this_week = next(
        (w for w in row.plan["weeks"] if w["start"] <= day.isoformat() < _week_end(w["start"])),
        None,
    )
    return {
        "today": workout,
        "this_week": this_week,
        "plan_notes": row.plan.get("notes", []),
        "goal": {"race": row.race_distance, "date": row.race_date},
        "built_from": row.params,
    }


def _week_end(start: str) -> str:
    return (date.fromisoformat(start) + timedelta(days=7)).isoformat()


def adjust_plan(session: Session, args: dict) -> dict:
    distance = None if args["race_distance"] == "none" else args["race_distance"]
    race_date = date.fromisoformat(args["race_date"]) if args["race_date"] else None
    row = plan_service.create_plan(
        session,
        today(),
        race_distance=distance,
        race_date=race_date,
        returning_from_injury=bool(args["returning_from_injury"]),
        runs_per_week=int(args["runs_per_week"]),
    )
    weeks = row.plan["weeks"]
    return {
        "created": True,
        "weeks": len(weeks),
        "notes": row.plan.get("notes", []),
        "built_from": row.params,
        "weekly_km": [w["km"] for w in weeks],
        "phases": [w["phase"] for w in weeks],
        "first_week": weeks[0],
    }


def get_warnings(session: Session, args: dict) -> dict:
    return warnings_for(session, _day(args["date"])) | {"date": _day(args["date"])}


def tidy(value):  # noqa: ANN001, ANN201
    """Round numbers the way they're read: 26.29 → 26, 0.664 → 0.66. The coach may not round
    numbers itself, so its tools hand them over already rounded."""
    if isinstance(value, float):
        return round(value) if abs(value) >= 10 else round(value, 2)
    if isinstance(value, dict):
        return {k: tidy(v) for k, v in value.items()}
    if isinstance(value, list | tuple):
        return [tidy(v) for v in value]
    return value


def coach_tools(session_factory: Callable[[], Session]) -> list[Tool]:
    def bind(fn: Callable[[Session, dict], dict]) -> Callable[[dict], dict]:
        def run(args: dict) -> dict:
            with session_factory() as session:
                return tidy(fn(session, args))

        return run

    date_only = {"date": DATE}
    return [
        Tool(
            "get_recovery",
            "Recovery score (0-100, green/yellow/red) for a day, with the inputs that "
            "drove it (HRV, resting HR, breathing rate, sleep) vs. the owner's baseline.",
            date_only,
            ["date"],
            bind(get_recovery),
            "Checking recovery",
        ),
        Tool(
            "get_sleep",
            "Last night's sleep, sleep performance, sleep debt and tonight's sleep need.",
            date_only,
            ["date"],
            bind(get_sleep),
            "Checking sleep",
        ),
        Tool(
            "get_strain",
            "Strain (0-21) and the workouts behind it for a day.",
            date_only,
            ["date"],
            bind(get_strain),
            "Checking strain",
        ),
        Tool(
            "get_training_load",
            "Fitness (CTL), fatigue (ATL), form, ACWR and load flags.",
            date_only,
            ["date"],
            bind(get_training_load),
            "Checking training load",
        ),
        Tool(
            "get_trend",
            "Recovery, strain, sleep debt, form and ACWR for each of the last N days.",
            {"days": {"type": "integer", "description": "How many days, 1-60."}},
            ["days"],
            bind(get_trend),
            "Looking at the trend",
        ),
        Tool(
            "predict_race",
            "Latest race-time prediction with its range, confidence and the "
            "methods behind it (VDOT, Riegel, VO2max, HR model, Tanda, ML).",
            {"distance": {"type": "string", "enum": RACES}},
            ["distance"],
            bind(predict_race),
            "Predicting race time",
        ),
        Tool(
            "get_zones",
            "Heart-rate zones and pace zones (from current VDOT).",
            {},
            [],
            bind(get_zones),
            "Working out zones",
        ),
        Tool(
            "get_plan",
            "Today's workout from the active training plan, adjusted to today's "
            "recovery and load, plus this week. Set pain to true if the owner reports pain.",
            {"pain": {"type": "boolean"}},
            ["pain"],
            bind(get_plan),
            "Checking the plan",
        ),
        Tool(
            "adjust_plan",
            "Build a new training plan (replaces the current one). Only call when "
            "the owner asks for a plan or a change of goal.",
            {
                "race_distance": {"type": "string", "enum": [*RACES, "none"]},
                "race_date": {"type": "string", "description": "YYYY-MM-DD, or '' for no race."},
                "returning_from_injury": {"type": "boolean"},
                "runs_per_week": {"type": "integer", "enum": [3, 4, 5, 6]},
            },
            ["race_distance", "race_date", "returning_from_injury", "runs_per_week"],
            bind(adjust_plan),
            "Building a plan",
        ),
        Tool(
            "get_warnings",
            "Early warnings (possible illness, injury risk) and running-form trends for a day.",
            date_only,
            ["date"],
            bind(get_warnings),
            "Checking warnings",
        ),
    ]
