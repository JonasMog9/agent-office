"""Strain (0–21): how hard the day was, from heart-rate training load.

Training load is Banister's TRIMP: minutes spent at each heart-rate-reserve fraction,
weighted exponentially so hard minutes count much more than easy ones,

    HRr   = (HR − HRrest) / (HRmax − HRrest)          clipped to [0, 1]
    TRIMP = Σ minutes × HRr × a × e^(b × HRr)         a, b = 0.64, 1.92 (men) / 0.86, 1.67 (women)

computed second by second from a workout's Strava heart-rate stream when there is one, else
from its average heart rate. The day's TRIMP is put on Whoop's 0–21 scale with a saturating
curve, so each extra unit of load adds less strain than the last:

    strain = 21 × (1 − e^(−TRIMP / 150))

Whoop's own formula isn't public. With this mapping an easy 45-minute run (TRIMP ≈ 50) is
about 6, an hour at tempo (≈ 120) about 12, and a two-hour hard effort (≈ 300) about 18.
All-day heart rate outside workouts isn't counted yet, so rest days read close to 0.
"""

import math
from collections.abc import Mapping, Sequence

from app.metrics.common import Component, ScoreResult, clip

SCALE = 150.0
MAX_GAP_S = 30  # a longer gap between samples is a pause: count at most this much of it
COEFFICIENTS = {"male": (0.64, 1.92), "female": (0.86, 1.67)}


def _weight(hr: float, hr_rest: float, hr_max: float, sex: str) -> float:
    a, b = COEFFICIENTS[sex]
    hrr = clip((hr - hr_rest) / (hr_max - hr_rest), 0.0, 1.0)
    return hrr * a * math.exp(b * hrr)


def trimp_from_stream(
    time_s: Sequence[float], heartrate: Sequence[float], hr_rest: float, hr_max: float, sex: str
) -> float:
    total = 0.0
    for i in range(1, min(len(time_s), len(heartrate))):
        dt = min(time_s[i] - time_s[i - 1], MAX_GAP_S)
        if dt > 0 and heartrate[i]:
            total += dt / 60 * _weight(heartrate[i], hr_rest, hr_max, sex)
    return total


def trimp_from_average(
    minutes: float, avg_hr: float, hr_rest: float, hr_max: float, sex: str
) -> float:
    return minutes * _weight(avg_hr, hr_rest, hr_max, sex)


def strain_from_trimp(trimp: float) -> float:
    return round(21 * (1 - math.exp(-max(trimp, 0) / SCALE)), 1)


def workout_trimp(
    workout: Mapping, hr_rest: float, hr_max: float, sex: str
) -> tuple[float | None, str]:
    """(TRIMP, how it was computed) for one ``workouts`` row, or (None, why not)."""
    streams = workout.get("streams") or {}
    if streams.get("heartrate") and streams.get("time"):
        return trimp_from_stream(
            streams["time"], streams["heartrate"], hr_rest, hr_max, sex
        ), "HR stream"
    if workout.get("avg_hr") and workout.get("moving_s"):
        minutes = workout["moving_s"] / 60
        return trimp_from_average(minutes, workout["avg_hr"], hr_rest, hr_max, sex), "average HR"
    return None, "no heart rate recorded"


def daily_strain(
    workouts: Sequence[Mapping], hr_rest: float | None, hr_max: float | None, sex: str = "male"
) -> ScoreResult:
    """Strain for one day from that day's workouts."""
    if sex not in COEFFICIENTS:
        raise ValueError(f"sex must be one of {sorted(COEFFICIENTS)}")
    if not hr_rest or not hr_max or hr_max <= hr_rest:
        return ScoreResult(None, notes=["Needs a resting and a max heart rate to compute strain."])
    components, total = [], 0.0
    for w in workouts:
        trimp, how = workout_trimp(w, hr_rest, hr_max, sex)
        name = f"{w.get('sport_type', 'Workout')}: {w.get('name', '')}".strip(": ")
        if trimp is None:
            components.append(Component(name, None, note=how))
            continue
        total += trimp
        components.append(
            Component(name, round(trimp, 1), contribution=round(trimp, 1), note=f"TRIMP from {how}")
        )
    notes = [f"Resting HR {hr_rest:.0f}, max HR {hr_max:.0f}, total TRIMP {total:.0f}."]
    if not workouts:
        notes.append("No workouts recorded; all-day activity isn't counted yet.")
    return ScoreResult(strain_from_trimp(total), components, notes)
