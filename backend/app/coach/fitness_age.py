"""Fitness age: the age at which a typical person has your VO2max.

It's the idea behind NTNU's fitness-age calculator and Garmin's Fitness Age: VO2max falls
with age, so a VO2max can be read as an age. We use the median (50th percentile) treadmill
VO2max for each decade from the FRIEND registry, Kaminsky et al., Mayo Clinic Proceedings
2015 (ml/kg/min), and interpolate linearly between decade midpoints:

    age band     20–29  30–39  40–49  50–59  60–69  70–79
    men          48.0   42.4   37.8   32.6   28.2   24.4
    women        37.6   30.9   27.0   23.4   20.6   18.3

The 20–29 and 70–79 values are the ones the paper's abstract quotes; the rest are as
reproduced in published summaries and worth checking against the paper's table. Above the
20–29 median, fitness age is "20 or younger": the table doesn't go lower. Below the 70–79
median, "80 or older". Apple Watch's VO2max is itself an estimate, so this is too.
"""

from datetime import date

from app.metrics.common import Component, ScoreResult

MIDPOINTS = [25, 35, 45, 55, 65, 75]
MEDIANS = {
    "male": [48.0, 42.4, 37.8, 32.6, 28.2, 24.4],
    "female": [37.6, 30.9, 27.0, 23.4, 20.6, 18.3],
}
YOUNGEST, OLDEST = 20, 80
SOURCE = "FRIEND registry treadmill medians (Kaminsky et al. 2015)"


def age_on(birth_month: str, day: date) -> float | None:
    """Age in years (with months as a fraction) from a "YYYY-MM" birth month."""
    try:
        y, m = (int(p) for p in birth_month.split("-")[:2])
    except (ValueError, AttributeError):
        return None
    if not 1 <= m <= 12:
        return None
    months = (day.year - y) * 12 + (day.month - m)
    return months / 12 if months >= 0 else None


def median_at(age: float, sex: str) -> float:
    """The median VO2max at an age, interpolated between decade midpoints."""
    med = MEDIANS.get(sex, MEDIANS["male"])
    if age <= MIDPOINTS[0]:
        return med[0]
    if age >= MIDPOINTS[-1]:
        return med[-1]
    pts = list(zip(MIDPOINTS, med, strict=True))
    for (a0, v0), (a1, v1) in zip(pts, pts[1:], strict=False):
        if a0 <= age <= a1:
            return v0 + (v1 - v0) * (age - a0) / (a1 - a0)
    return med[-1]


def fitness_age(vo2max: float | None, sex: str, age: float | None = None) -> ScoreResult:
    """Value = fitness age in years (rounded), label "younger" / "same" / "older" vs ``age``."""
    if not vo2max:
        return ScoreResult(None, notes=["No VO2max yet: the Apple Watch needs outdoor runs."])
    med = MEDIANS.get(sex, MEDIANS["male"])
    # Extend each end by one more decade of the same slope, then clamp to 20–80.
    pts = [
        (MIDPOINTS[0] - 10, 2 * med[0] - med[1]),
        *zip(MIDPOINTS, med, strict=True),
        (MIDPOINTS[-1] + 10, 2 * med[-1] - med[-2]),
    ]
    if vo2max >= pts[0][1]:
        fa = float(YOUNGEST)
    elif vo2max <= pts[-1][1]:
        fa = float(OLDEST)
    else:
        fa = float(OLDEST)
        for (a0, v0), (a1, v1) in zip(pts, pts[1:], strict=False):
            if v1 <= vo2max <= v0:
                fa = a0 + (a1 - a0) * (v0 - vo2max) / (v0 - v1)
                break
        fa = min(max(fa, YOUNGEST), OLDEST)
    comps = [Component("VO2max", round(vo2max, 1), note="Apple Watch estimate")]
    label = None
    notes = [f"The age at which the median VO2max equals yours ({SOURCE})."]
    if age is not None:
        typical = median_at(age, sex)
        comps.append(Component("median at your age", round(typical, 1), note=f"age {age:.0f}"))
        diff = round(fa) - round(age)
        label = "younger" if diff < 0 else "older" if diff > 0 else "same"
    if fa == YOUNGEST:
        notes.append("Fitter than the median 20-year-old: the table doesn't go younger than 20.")
    if fa == OLDEST:
        notes.append("Below the median for 70–79: the table doesn't go older than 80.")
    return ScoreResult(round(fa), comps, notes, label)
