"""Training history: the totals, trends and records behind the health page, the kind of
numbers a Strava or Garmin subscription shows. Pure functions over plain run dicts, so
they're tested on hand-made data.

A run is a mapping with ``day``, ``name``, ``distance_m``, ``moving_s``, and optionally
``elevation_m``, ``avg_hr``, ``max_hr``, ``cadence_spm``, ``summary`` (the Strava activity,
for best efforts) and ``streams`` (``time`` and ``heartrate`` lists, for time in zones).

    weekly_totals     km, runs, time and climb per Monday-to-Sunday week, empty weeks too
    daily_km          km per day for the activity calendar
    totals            count, km, hours, climb and longest run over any set of runs
    personal_records  the fastest time for each Strava best-effort distance
    time_in_zones     minutes in each heart-rate zone, from the HR streams
    run_rows          the recent-runs table (pace, cadence)
"""

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta

MAX_SAMPLE_GAP_S = 30  # a longer gap between HR samples is a pause, not time in a zone

# Strava's best-effort names, shortest first, and their distances in metres.
EFFORTS = {
    "400m": 400,
    "1/2 mile": 805,
    "1k": 1000,
    "1 mile": 1609,
    "2 mile": 3219,
    "5k": 5000,
    "10k": 10000,
    "15k": 15000,
    "10 mile": 16093,
    "20k": 20000,
    "Half-Marathon": 21097,
    "30k": 30000,
    "Marathon": 42195,
}
# Strava's live API capitalises some names ("5K", "10K", "1K"); match them case-insensitively.
EFFORT_KEY = {name.lower(): name for name in EFFORTS}


def week_start(d: date) -> date:
    return d - timedelta(days=d.weekday())


def weekly_totals(runs: Iterable[Mapping], end: date, weeks: int = 26) -> list[dict]:
    """The last ``weeks`` weeks ending with the week of ``end``, oldest first."""
    last = week_start(end)
    starts = [last - timedelta(weeks=weeks - 1 - i) for i in range(weeks)]
    out = {
        s: {"week": s.isoformat(), "km": 0.0, "runs": 0, "minutes": 0.0, "climb_m": 0.0}
        for s in starts
    }
    for r in runs:
        w = out.get(week_start(r["day"]))
        if w is None:
            continue
        w["km"] += (r.get("distance_m") or 0) / 1000
        w["runs"] += 1
        w["minutes"] += (r.get("moving_s") or 0) / 60
        w["climb_m"] += r.get("elevation_m") or 0
    return [
        w
        | {"km": round(w["km"], 1), "minutes": round(w["minutes"]), "climb_m": round(w["climb_m"])}
        for w in out.values()
    ]


def daily_km(runs: Iterable[Mapping], end: date, days: int = 84) -> list[dict]:
    """Km per day for the ``days`` up to and including ``end``, oldest first."""
    start = end - timedelta(days=days - 1)
    km = {start + timedelta(days=i): 0.0 for i in range(days)}
    for r in runs:
        if r["day"] in km:
            km[r["day"]] += (r.get("distance_m") or 0) / 1000
    return [{"day": d.isoformat(), "km": round(v, 1)} for d, v in km.items()]


def totals(runs: Sequence[Mapping]) -> dict:
    longest = max(runs, key=lambda r: r.get("distance_m") or 0, default=None)
    return {
        "runs": len(runs),
        "km": round(sum((r.get("distance_m") or 0) for r in runs) / 1000, 1),
        "hours": round(sum((r.get("moving_s") or 0) for r in runs) / 3600, 1),
        "climb_m": round(sum((r.get("elevation_m") or 0) for r in runs)),
        "longest_km": round((longest.get("distance_m") or 0) / 1000, 1) if longest else None,
    }


def personal_records(runs: Iterable[Mapping]) -> list[dict]:
    """The fastest elapsed time for each best-effort distance, shortest distance first."""
    best: dict[str, dict] = {}
    for r in runs:
        for be in (r.get("summary") or {}).get("best_efforts") or []:
            name, t = EFFORT_KEY.get(str(be.get("name", "")).lower()), be.get("elapsed_time")
            if name is None or not t:
                continue
            if name not in best or t < best[name]["seconds"]:
                best[name] = {
                    "name": name,
                    "distance_m": EFFORTS[name],
                    "seconds": t,
                    "day": r["day"].isoformat(),
                    "run": r.get("name") or "",
                }
    return sorted(best.values(), key=lambda b: b["distance_m"])


def zone_of(hr: float, bounds: Sequence[tuple[int, float, float]]) -> int:
    """The zone a heart rate falls in. Below zone 1 counts as zone 1, above zone 5 as 5."""
    for zone, _low, high in bounds:
        if hr < high:
            return zone
    return bounds[-1][0]


def time_in_zones(
    streams: Iterable[Mapping], bounds: Sequence[tuple[int, float, float]]
) -> dict[int, float]:
    """Minutes per zone over every run's HR stream. ``bounds`` are (zone, low, high) bpm."""
    minutes = {zone: 0.0 for zone, _, _ in bounds}
    for s in streams:
        t, hr = s.get("time") or [], s.get("heartrate") or []
        for i in range(min(len(t), len(hr)) - 1):
            gap = t[i + 1] - t[i]
            if 0 < gap <= MAX_SAMPLE_GAP_S and hr[i]:
                minutes[zone_of(hr[i], bounds)] += gap / 60
    return {z: round(m, 1) for z, m in minutes.items()}


def pace_s_per_km(distance_m: float | None, moving_s: float | None) -> float | None:
    if not distance_m or not moving_s:
        return None
    return moving_s / (distance_m / 1000)


def run_rows(runs: Sequence[Mapping], limit: int = 15) -> list[dict]:
    """The most recent runs, newest first, for the recent-runs table."""
    newest = sorted(runs, key=lambda r: r["day"], reverse=True)[:limit]
    out = []
    for r in newest:
        pace = pace_s_per_km(r.get("distance_m"), r.get("moving_s"))
        climb, hr, cad = r.get("elevation_m"), r.get("avg_hr"), r.get("cadence_spm")
        out.append(
            {
                "day": r["day"].isoformat(),
                "name": r.get("name") or "Run",
                "km": round((r.get("distance_m") or 0) / 1000, 2),
                "moving_s": r.get("moving_s"),
                "pace_s_per_km": None if pace is None else round(pace),
                "avg_hr": None if hr is None else round(hr),
                "climb_m": None if climb is None else round(climb),
                "cadence_spm": None if cad is None else round(cad),
            }
        )
    return out
