"""Recovery (0–100%): how ready the body is today, versus the owner's own recent normal.

Each input is turned into a robust z-score against the previous 60 days (median and MAD, so
outliers in the baseline don't distort it), signed so positive means "better than usual":

    component   transform                     direction   weight
    HRV         ln(SDNN)                      higher +    0.40
    resting HR  bpm                           lower +     0.25
    sleep       asleep / need (not baseline)  more +      0.20
    resp. rate  breaths/min                   lower +     0.10
    wrist temp  °C                            any shift − 0.05

Missing components are dropped and the remaining weights rescaled to sum to 1, so a Series 7
watch (no temperature sensor) or a night without the watch still gets a score from what
exists. The weighted z is mapped through the normal CDF: z = 0 (a normal day) is 50%,
+1 is 84%, −1 is 16%. Green is ≥ 67%, yellow ≥ 34%, red below.

HRV is only ever compared with the owner's own baseline: Apple Watch reports SDNN, which
isn't comparable with Whoop's RMSSD.
"""

import math
from collections.abc import Mapping, Sequence

from app.metrics.common import Component, ScoreResult, clip, normal_cdf, robust_center_spread

BASELINE_DAYS = 60
MIN_HISTORY = 14  # baseline days a component needs before it counts
Z_CAP = 3.0  # one extreme reading can't dominate the score

# name: (daily_metrics column, transform, sign, weight, spread floor in transformed units)
SIGNALS = {
    "hrv": ("hrv_sdnn_ms", math.log, +1, 0.40, 0.05),
    "resting_hr": ("resting_hr_bpm", float, -1, 0.25, 1.0),
    "respiratory_rate": ("respiratory_rate_bpm", float, -1, 0.10, 0.3),
    "wrist_temp": ("wrist_temp_c", float, -1, 0.05, 0.1),  # sign applied to |z|
}
SLEEP_WEIGHT = 0.20
SLEEP_SPREAD = 0.15  # 85% of sleep need ≈ −1 z


def label_for(score: float) -> str:
    return "green" if score >= 67 else "yellow" if score >= 34 else "red"


def recovery(
    today: Mapping[str, float | None],
    history: Sequence[Mapping[str, float | None]],
    sleep_need_min: float = 480,
) -> ScoreResult:
    """Score ``today`` (a daily_metrics row) against ``history`` (the up-to-60 previous rows).

    History rows may have gaps (days without the watch); only non-null values count.
    """
    notes: list[str] = []
    components: list[Component] = []
    weighted: list[tuple[float, float]] = []  # (weight, z)
    untracked: list[str] = []  # never recorded, e.g. wrist temperature on older watches
    untracked_weight = 0.0

    for name, (column, transform, sign, weight, floor) in SIGNALS.items():
        value = today.get(column)
        past = [transform(r[column]) for r in history[-BASELINE_DAYS:] if r.get(column)]
        if value is None and not past:
            untracked.append(name)
            untracked_weight += weight
            continue
        if value is None:
            components.append(Component(name, None, note="no reading today"))
            continue
        if len(past) < MIN_HISTORY:
            components.append(
                Component(name, value, note=f"needs {MIN_HISTORY} days of history, has {len(past)}")
            )
            continue
        center, spread = robust_center_spread(past, floor)
        raw_z = (transform(value) - center) / spread
        z = -abs(raw_z) if name == "wrist_temp" else sign * raw_z
        z = clip(z, -Z_CAP, Z_CAP)
        baseline = math.exp(center) if transform is math.log else center
        components.append(Component(name, value, round(baseline, 2), round(z, 2), weight))
        weighted.append((weight, z))

    asleep = today.get("sleep_asleep_min")
    if asleep:
        performance = asleep / sleep_need_min
        z = clip((min(performance, 1.1) - 1) / SLEEP_SPREAD, -Z_CAP, Z_CAP)
        components.append(
            Component(
                "sleep",
                asleep,
                sleep_need_min,
                round(z, 2),
                SLEEP_WEIGHT,
                note=f"{performance:.0%} of sleep need",
            )
        )
        weighted.append((SLEEP_WEIGHT, z))
    else:
        components.append(Component("sleep", None, note="no sleep recorded last night"))

    used = {c.name for c in components if c.z is not None}
    if not used & {"hrv", "resting_hr"}:
        notes.append("No usable HRV or resting HR today, so no recovery score.")
        return ScoreResult(None, components, notes)

    total_weight = sum(w for w, _ in weighted)
    combined = sum(w * z for w, z in weighted) / total_weight
    components = [
        Component(
            c.name,
            c.value,
            c.baseline,
            c.z,
            round(c.weight / total_weight, 3),
            round(c.weight / total_weight * c.z, 3),
            c.note,
        )
        if c.z is not None
        else c
        for c in components
    ]
    if untracked:
        notes.append(f"Not recorded at all in the baseline window: {', '.join(untracked)}.")
    if total_weight < 0.999 - untracked_weight:
        notes.append(f"Scored from {', '.join(sorted(used))}; missing inputs were reweighted.")
    score = round(100 * normal_cdf(combined))
    return ScoreResult(score, components, notes, label_for(score))
