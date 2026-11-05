"""GET /stats/health: everything the health page shows, the numbers a Strava or Garmin
subscription would, computed here from the owner's own Apple Health and Strava data.

VO2max, race predictions and their history, weekly mileage, an activity calendar, totals,
personal records, heart-rate and pace zones with time in zone, fitness and fatigue,
resting HR and HRV, sleep stages, running form, recent runs and this week's plan.
Private like the stats page: it needs OFFICE_VIEW_KEY in the ``X-Office-Key`` header.
"""

import hmac
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import coach_tools
from app.coach import history, plan_service
from app.coach.predict import RACES, RUN_TYPES
from app.coach.zones import hr_zones, pace_zones
from app.config import get_settings
from app.db.models import DailyMetric, DailyScore, Prediction, Workout
from app.db.session import get_session

router = APIRouter()
ZONE_WINDOW_DAYS = 28


def _r(x: float | None, nd: int = 0) -> float | None:
    return None if x is None else round(x, nd) if nd else round(x)


def runs(session: Session, since: date | None = None, summaries: bool = False) -> list[dict]:
    """Runs as plain dicts. Strava's run cadence is per foot, so it's doubled to steps/min."""
    cols = [
        Workout.day,
        Workout.name,
        Workout.distance_m,
        Workout.moving_s,
        Workout.elevation_gain_m,
        Workout.avg_hr,
        Workout.max_hr,
        Workout.avg_cadence,
    ]
    if summaries:
        cols.append(Workout.summary)
    q = select(*cols).where(Workout.sport_type.in_(RUN_TYPES))
    if since:
        q = q.where(Workout.day >= since)
    out = []
    for row in session.execute(q.order_by(Workout.day)):
        out.append(
            {
                "day": row.day,
                "name": row.name,
                "distance_m": row.distance_m,
                "moving_s": row.moving_s,
                "elevation_m": row.elevation_gain_m,
                "avg_hr": row.avg_hr,
                "max_hr": row.max_hr,
                "cadence_spm": None if row.avg_cadence is None else row.avg_cadence * 2,
                "summary": row.summary if summaries else None,
            }
        )
    return out


def vo2max(session: Session, end: date, days: int = 365) -> list[dict]:
    q = select(DailyMetric.day, DailyMetric.vo2max).where(
        DailyMetric.day.between(end - timedelta(days=days - 1), end),
        DailyMetric.vo2max.is_not(None),
    )
    return [
        {"day": d.isoformat(), "value": _r(v, 1)}
        for d, v in session.execute(q.order_by(DailyMetric.day))
    ]


def daily(session: Session, end: date, days: int) -> list[tuple]:
    """(day, metrics row or None, score row or None) for each of the last ``days`` days."""
    start = end - timedelta(days=days - 1)
    metrics = {
        m.day: m for m in session.scalars(select(DailyMetric).where(DailyMetric.day >= start))
    }
    scores = {s.day: s for s in session.scalars(select(DailyScore).where(DailyScore.day >= start))}
    return [
        (d, metrics.get(d), scores.get(d)) for d in (start + timedelta(days=i) for i in range(days))
    ]


def vitals(rows: list[tuple]) -> list[dict]:
    return [
        {
            "day": d.isoformat(),
            "resting_hr": _r(m.resting_hr_bpm) if m else None,
            "hrv": _r(m.hrv_sdnn_ms) if m else None,
            "respiratory_rate": _r(m.respiratory_rate_bpm, 1) if m else None,
            "recovery": _r(s.recovery) if s else None,
            "label": s.recovery_label if s else None,
        }
        for d, m, s in rows
    ]


def sleep(rows: list[tuple]) -> list[dict]:
    return [
        {
            "day": d.isoformat(),
            "asleep_min": _r(m.sleep_asleep_min) if m else None,
            "deep_min": _r(m.sleep_deep_min) if m else None,
            "core_min": _r(m.sleep_core_min) if m else None,
            "rem_min": _r(m.sleep_rem_min) if m else None,
            "awake_min": _r(m.sleep_awake_min) if m else None,
            "performance_pct": _r(s.sleep_performance) if s else None,
            "debt_min": _r(s.sleep_debt_min) if s else None,
        }
        for d, m, s in rows
    ]


def load(rows: list[tuple]) -> list[dict]:
    return [
        {
            "day": d.isoformat(),
            "fitness": _r(s.ctl, 1) if s else None,
            "fatigue": _r(s.atl, 1) if s else None,
            "form": _r(s.form, 1) if s else None,
            "strain": _r(s.strain, 1) if s else None,
        }
        for d, _m, s in rows
    ]


def running_form(rows: list[tuple], recent_runs: list[dict]) -> list[dict]:
    cadence: dict[date, list[float]] = {}
    for r in recent_runs:
        if r["cadence_spm"]:
            cadence.setdefault(r["day"], []).append(r["cadence_spm"])
    out = []
    for d, m, _s in rows:
        c = cadence.get(d)
        out.append(
            {
                "day": d.isoformat(),
                "cadence_spm": _r(sum(c) / len(c)) if c else None,
                "ground_contact_ms": _r(m.ground_contact_ms) if m else None,
                "vertical_oscillation_cm": _r(m.vertical_oscillation_cm, 1) if m else None,
                "stride_length_m": _r(m.stride_length_m, 2) if m else None,
            }
        )
    return out


def predictions(session: Session, end: date, days: int = 180) -> dict:
    rows = session.scalars(
        select(Prediction)
        .where(Prediction.day.between(end - timedelta(days=days - 1), end))
        .order_by(Prediction.day)
    ).all()
    history_by: dict[str, list[dict]] = {r: [] for r in RACES}
    latest: dict[str, Prediction] = {}
    for p in rows:
        if p.distance not in history_by or p.predicted_s is None:
            continue
        history_by[p.distance].append(
            {
                "day": p.day.isoformat(),
                "seconds": _r(p.predicted_s),
                "low": _r(p.low_s),
                "high": _r(p.high_s),
            }
        )
        latest[p.distance] = p
    current = []
    for race in RACES:
        p = latest.get(race)
        if p is None:
            current.append({"distance": race, "seconds": None})
            continue
        comps = (p.details or {}).get("components", [])
        current.append(
            {
                "distance": race,
                "as_of": p.day.isoformat(),
                "seconds": _r(p.predicted_s),
                "low": _r(p.low_s),
                "high": _r(p.high_s),
                "confidence": p.confidence,
                "methods": [
                    {"method": c["name"], "seconds": c["value"], "note": c.get("note", "")}
                    for c in comps
                    if c.get("name") != "range" and c.get("value")
                ],
            }
        )
    return {"current": current, "history": history_by}


def zones(session: Session, end: date) -> dict:
    score = session.scalar(
        select(DailyScore)
        .where(
            DailyScore.day <= end,
            DailyScore.hr_rest_used.is_not(None),
            DailyScore.hr_max_used.is_not(None),
        )
        .order_by(DailyScore.day.desc())
    )
    hr = []
    if score:
        z = hr_zones(score.hr_rest_used, score.hr_max_used)
        bounds = [(i + 1, c.value, c.baseline) for i, c in enumerate(z.components)]
        streams = session.scalars(
            select(Workout.streams).where(
                Workout.sport_type.in_(RUN_TYPES),
                Workout.day > end - timedelta(days=ZONE_WINDOW_DAYS),
                Workout.day <= end,
            )
        ).all()
        minutes = history.time_in_zones([s for s in streams if s], bounds) if bounds else {}
        hr = [
            {
                "zone": zone,
                "name": c.name.split(" ", 1)[1],
                "low": lo,
                "high": hi,
                "minutes": minutes.get(zone, 0),
            }
            for (zone, lo, hi), c in zip(bounds, z.components, strict=True)
        ]
    v, source = plan_service.current_vdot(session, end)
    pace = [
        {"name": p.name, "fast_s_per_km": _r(p.fast_s_per_km), "slow_s_per_km": _r(p.slow_s_per_km)}
        for p in pace_zones(v)
    ]
    return {
        "hr": hr,
        "hr_rest": _r(score.hr_rest_used) if score else None,
        "hr_max": _r(score.hr_max_used) if score else None,
        "window_days": ZONE_WINDOW_DAYS,
        "pace": pace,
        "vdot": _r(v, 1),
        "vdot_source": source,
    }


def summary(
    end: date, vo2: list[dict], weekly: list[dict], vit: list[dict], ld: list[dict]
) -> dict:
    def last(rows: list[dict], key: str) -> float | None:
        return next((r[key] for r in reversed(rows) if r.get(key) is not None), None)

    def mean(rows: list[dict], key: str) -> float | None:
        vals = [r[key] for r in rows if r.get(key) is not None]
        return round(sum(vals) / len(vals), 1) if vals else None

    since = (end - timedelta(days=90)).isoformat()
    vo2_then = next((r["value"] for r in vo2 if r["day"] >= since), None)
    vo2_now = vo2[-1]["value"] if vo2 else None
    return {
        "vo2max": vo2_now,
        "vo2max_change_90d": None
        if vo2_now is None or vo2_then is None
        else round(vo2_now - vo2_then, 1),
        "this_week_km": weekly[-1]["km"] if weekly else 0,
        "avg_week_km_4w": round(sum(w["km"] for w in weekly[-5:-1]) / 4, 1)
        if len(weekly) >= 5
        else None,
        "resting_hr": last(vit, "resting_hr"),
        "resting_hr_30d": mean(vit[-30:], "resting_hr"),
        "hrv": last(vit, "hrv"),
        "hrv_30d": mean(vit[-30:], "hrv"),
        "recovery": last(vit[-1:], "recovery"),
        "label": vit[-1]["label"] if vit else None,
        "fitness": last(ld, "fitness"),
        "fatigue": last(ld, "fatigue"),
        "form": last(ld, "form"),
    }


def health_page(session: Session, end: date) -> dict:
    all_runs = runs(session, summaries=True)
    rows90, rows120 = daily(session, end, 90), daily(session, end, 120)
    weekly = history.weekly_totals(all_runs, end, weeks=52)
    vo2 = vo2max(session, end)
    vit, ld = vitals(rows90), load(rows120)
    ytd = [r for r in all_runs if r["day"] >= date(end.year, 1, 1)]
    last4 = [r for r in all_runs if r["day"] > end - timedelta(weeks=4)]
    plan = coach_tools.get_plan(session, {"pain": False})
    return {
        "today": end.isoformat(),
        "summary": summary(end, vo2, weekly, vit, ld),
        "totals": {
            "last_4_weeks": history.totals(last4),
            "year_to_date": history.totals(ytd),
            "all_time": history.totals(all_runs),
        },
        "vo2max": vo2,
        "weekly": weekly,
        "calendar": history.daily_km(all_runs, end, days=84),
        "predictions": predictions(session, end),
        "load": ld,
        "vitals": vit,
        "sleep": sleep(rows90[-30:]),
        "zones": zones(session, end),
        "records": history.personal_records(all_runs),
        "runs": history.run_rows(all_runs),
        "form": running_form(rows90, all_runs),
        "plan": {
            "this_week": plan.get("this_week"),
            "goal": plan.get("goal"),
            "today": (plan.get("today") or {}).get("today"),
        }
        if plan.get("this_week")
        else None,
    }


@router.get("/stats/health")
def stats_health(
    session: Annotated[Session, Depends(get_session)],
    key: Annotated[str | None, Header(alias="X-Office-Key")] = None,
) -> JSONResponse:
    expected = get_settings().office_view_key
    if not expected or not key or not hmac.compare_digest(key.encode(), expected.encode()):
        return JSONResponse({"error": "bad key"}, status_code=401)
    body = health_page(session, coach_tools.today()) | {
        "generated_at": datetime.now(UTC).isoformat()
    }
    return JSONResponse(jsonable_encoder(body))
