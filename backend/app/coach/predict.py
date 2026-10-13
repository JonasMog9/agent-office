"""Race-time predictions for the 5K, 10K, half and marathon, each from several methods.

Methods (each one a component of the result, so the coach can say where a number comes from):

    VDOT        your best recent effort → Daniels VDOT → the time with the same VDOT
    Riegel      T2 = T1 × (D2 / D1)^1.06 from that same effort
    VO2max      Apple's VO2max estimate used as the VDOT (a cross-check; Apple's number is
                a model of its own, so it's the least certain)
    Tanda       marathon only: Pm = 17.1 + 140 × e^(−0.0053 K) + 0.55 P   (s/km)
                K = mean weekly km and P = mean training pace (s/km) over the last 8 weeks
                (Tanda 2011). It's the mileage adjustment: low volume gives a slower marathon.

    HR model    marathon and the rest: the VDOT the personal fitness model infers from the
                pace you hold at a given heart rate (coach.fitness). Works from easy runs, so
                it's the one to lean on when there's no recent race.

Methods are grouped by source so one input can't vote twice: VDOT and Riegel both come from
the same effort and count as one "effort" source (their mean). The estimate is the median of
the sources. The range is the estimate ± 3% (high confidence), ± 5% (medium) or ± 8% (low),
and a note names the spread when the sources disagree by more than 15%.

Efforts are Strava's best efforts of 5K and longer inside runs, plus whole runs marked as a
race. Shorter best efforts (400 m, 1K, mile) would overstate endurance and are skipped.
Confidence: high with a race in the last 8 weeks; medium with training best efforts (rarely
all-out, so they understate fitness) or the HR model; low with neither.
"""

import math
import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from app.coach.vdot import DISTANCES_M, race_time_s, vdot
from app.coach.zones import format_pace
from app.metrics.common import Component, ScoreResult

RACES = ["5K", "10K", "half marathon", "marathon"]
WINDOW_DAYS = 56
MIN_EFFORT_M = 4900  # Strava's "5k" best effort is 5000 m; allow GPS rounding
RIEGEL_EXPONENT = 1.06
STRAVA_RACE = 1  # workout_type for a run marked as a race
RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}


@dataclass(frozen=True)
class Effort:
    day: date
    name: str
    distance_m: float
    time_s: float
    is_race: bool

    @property
    def vdot(self) -> float:
        return vdot(self.distance_m, self.time_s)


def efforts(runs: Sequence[Mapping], as_of: date, window_days: int = WINDOW_DAYS) -> list[Effort]:
    """Hard-enough efforts of 5K or more from runs within ``window_days`` before ``as_of``."""
    since = as_of - timedelta(days=window_days)
    out = []
    for run in runs:
        if not since < run["day"] <= as_of:
            continue
        summary = run.get("summary") or {}
        if summary.get("workout_type") == STRAVA_RACE and (run.get("distance_m") or 0) >= 1500:
            t = run.get("moving_s") or run.get("elapsed_s")
            if t:
                out.append(
                    Effort(run["day"], summary.get("name", "race"), run["distance_m"], t, True)
                )
        for be in summary.get("best_efforts") or []:
            if (be.get("distance") or 0) >= MIN_EFFORT_M and be.get("elapsed_time"):
                out.append(
                    Effort(
                        run["day"], be.get("name", ""), be["distance"], be["elapsed_time"], False
                    )
                )
    return out


def training_volume(
    runs: Sequence[Mapping], as_of: date, weeks: int = 8
) -> tuple[float, float | None]:
    """(mean weekly km, mean pace in s/km) over the ``weeks`` before ``as_of``."""
    since = as_of - timedelta(weeks=weeks)
    window = [
        r for r in runs if since < r["day"] <= as_of and r.get("distance_m") and r.get("moving_s")
    ]
    km = sum(r["distance_m"] for r in window) / 1000
    seconds = sum(r["moving_s"] for r in window)
    return km / weeks, (seconds / km if km else None)


def riegel(time_s: float, distance_m: float, target_m: float) -> float:
    return time_s * (target_m / distance_m) ** RIEGEL_EXPONENT


def tanda_marathon_s(weekly_km: float, pace_s_per_km: float) -> float:
    return (17.1 + 140.0 * math.exp(-0.0053 * weekly_km) + 0.55 * pace_s_per_km) * 42.195


MARGINS = {"high": 0.03, "medium": 0.05, "low": 0.08}
DISAGREEMENT = 0.15


def predict_races(
    runs: Sequence[Mapping], vo2max: float | None, as_of: date, hr_vdot: float | None = None
) -> dict[str, ScoreResult]:
    """One result per race distance. Value = estimate in seconds, label = confidence."""
    found = efforts(runs, as_of)
    best = max(found, key=lambda e: e.vdot, default=None)
    weekly_km, pace = training_volume(runs, as_of)
    if any(e.is_race for e in found):
        confidence = "high"
    elif best or hr_vdot:
        confidence = "medium"
    else:
        confidence = "low"

    results = {}
    for race in RACES:
        target = DISTANCES_M[race]
        comps: list[Component] = []
        if best:
            km, minutes = best.distance_m / 1000, best.time_s / 60
            src = f"{best.name} {km:.1f} km in {minutes:.1f} min on {best.day}"
            comps.append(
                Component(
                    "VDOT", round(race_time_s(best.vdot, target)), round(best.vdot, 1), note=src
                )
            )
            comps.append(
                Component("Riegel", round(riegel(best.time_s, best.distance_m, target)), note=src)
            )
        if vo2max:
            comps.append(
                Component(
                    "VO2max",
                    round(race_time_s(vo2max, target)),
                    vo2max,
                    note="Apple estimate as VDOT",
                )
            )
        if hr_vdot:
            comps.append(
                Component(
                    "HR model",
                    round(race_time_s(hr_vdot, target)),
                    hr_vdot,
                    note="VDOT from your pace at heart rate (personal fitness model)",
                )
            )
        if race == "marathon" and pace and weekly_km >= 10:
            comps.append(
                Component(
                    "Tanda",
                    round(tanda_marathon_s(weekly_km, pace)),
                    note=f"{weekly_km:.0f} km/week at {format_pace(pace)}/km, last 8 weeks",
                )
            )
        if not comps:
            results[race] = ScoreResult(
                None, notes=["No efforts, VO2max or mileage to predict from."]
            )
            continue
        sources: dict[str, list[float]] = {}
        for c in comps:
            sources.setdefault("effort" if c.name in ("VDOT", "Riegel") else c.name, []).append(
                c.value
            )
        by_source = {name: statistics.fmean(v) for name, v in sources.items()}
        estimate = statistics.median(by_source.values())
        margin = MARGINS[confidence]
        comps.append(
            Component(
                "range",
                round(estimate * (1 - margin)),
                round(estimate * (1 + margin)),
                note=f"estimate ± {margin:.0%} ({confidence} confidence)",
            )
        )
        notes = []
        fastest = min(by_source, key=by_source.get)
        slowest = max(by_source, key=by_source.get)
        if by_source[slowest] > by_source[fastest] * (1 + DISAGREEMENT):
            notes.append(
                f"Methods disagree: {fmt_time(by_source[fastest])} ({fastest}) to "
                f"{fmt_time(by_source[slowest])} ({slowest})."
            )
        if confidence == "low":
            notes.append(
                "No hard effort in the last 8 weeks: a race or time trial would sharpen this."
            )
        elif confidence == "medium" and not hr_vdot:
            notes.append(
                "Based on training best efforts, which are rarely all-out; likely conservative."
            )
        if weekly_km < 30 and race in ("half marathon", "marathon"):
            notes.append(
                f"Only {weekly_km:.0f} km/week lately; long races need more volume than that."
            )
        results[race] = ScoreResult(round(estimate), comps, notes, confidence)
    return results


def fmt_time(seconds: float) -> str:
    s = round(seconds)
    return (
        f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"
    )
