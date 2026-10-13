"""Running form trends and early warnings (possible illness, injury risk). Rules, not guesses.

Running form compares the last 14 days with your own baseline (the 76 days before that),
using medians so one odd run doesn't trip it:

    cadence          steps/min from Strava (its run cadence is per foot, so ×2), compared only
                     with baseline runs at a similar pace (±20 s/km), since cadence rises with speed
    ground contact   ms, Apple Watch daily average         flag if up 5%+
    vertical osc.    cm, Apple Watch daily average         flag if up 8%+
    stride length    m, Apple Watch daily average          flag if down 4%+
    cadence                                                flag if down 3%+

Fatigue and niggles tend to show as shorter, slower-turnover strides with more time on the
ground. Each needs 3+ recent and 5+ baseline values; otherwise it says what's missing.

Early warnings, against your own 30-day baselines (medians):

    possible illness   resting HR ≥ 5 bpm above and HRV ≥ 20% below baseline, both on each of
                       the last 2 days; a raised respiratory rate (≥ 1 breath/min) is added as
                       supporting evidence, or flags it on its own with the RHR rise
    injury risk        ACWR above 1.5, or form below −30, or 2+ running-form flags at once
"""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, timedelta

from app.metrics.common import Component, ScoreResult

RECENT_DAYS = 14
BASELINE_DAYS = 90
MIN_RECENT, MIN_BASELINE = 3, 5
PACE_BAND_S = 20
# metric: (daily_metrics column, flag threshold as a fraction, direction that's bad)
FORM_METRICS = {
    "ground contact": ("ground_contact_ms", 0.05, +1),
    "vertical oscillation": ("vertical_oscillation_cm", 0.08, +1),
    "stride length": ("stride_length_m", 0.04, -1),
}
CADENCE_DROP = 0.03

ILLNESS_BASELINE_DAYS = 30
RHR_RISE_BPM = 5
HRV_DROP = 0.20
RESP_RISE = 1.0
ACWR_HIGH = 1.5
FORM_LOW = -30


@dataclass(frozen=True)
class EarlyWarning:
    kind: str  # "possible illness" | "injury risk"
    message: str
    evidence: list[str] = field(default_factory=list)


def _change(recent: Sequence[float], base: Sequence[float]) -> tuple[float, float, float] | None:
    if len(recent) < MIN_RECENT or len(base) < MIN_BASELINE:
        return None
    r, b = statistics.median(recent), statistics.median(base)
    return r, b, (r - b) / b if b else 0.0


def running_form(
    runs: Sequence[Mapping], daily: Mapping[date, Mapping], as_of: date
) -> ScoreResult:
    """Form trend components and flags. Value = number of flags."""
    recent_start = as_of - timedelta(days=RECENT_DAYS)
    base_start = as_of - timedelta(days=BASELINE_DAYS)
    comps, flags = [], []

    for name, (column, threshold, bad) in FORM_METRICS.items():
        recent = [
            m[column] for d, m in daily.items() if recent_start < d <= as_of and m.get(column)
        ]
        base = [
            m[column] for d, m in daily.items() if base_start < d <= recent_start and m.get(column)
        ]
        ch = _change(recent, base)
        if ch is None:
            comps.append(
                Component(
                    name, None, note=f"needs {MIN_RECENT}+ recent and {MIN_BASELINE}+ baseline days"
                )
            )
            continue
        r, b, pct = ch
        comps.append(Component(name, round(r, 2), round(b, 2), note=f"{pct:+.1%} vs baseline"))
        if pct * bad >= threshold:
            flags.append(f"{name} {pct:+.0%} vs your baseline")

    def cadence_and_pace(r: Mapping) -> tuple[float, float] | None:
        if r.get("avg_cadence") and r.get("avg_speed_mps"):
            return r["avg_cadence"] * 2, 1000 / r["avg_speed_mps"]
        return None

    recent_runs = [
        cp for r in runs if recent_start < r["day"] <= as_of and (cp := cadence_and_pace(r))
    ]
    base_runs = [
        cp for r in runs if base_start < r["day"] <= recent_start and (cp := cadence_and_pace(r))
    ]
    diffs = []
    for cadence, pace in recent_runs:
        similar = [c for c, p in base_runs if abs(p - pace) <= PACE_BAND_S]
        if len(similar) >= MIN_BASELINE // 2:
            diffs.append((cadence, statistics.median(similar)))
    if len(diffs) >= MIN_RECENT:
        r = statistics.median(c for c, _ in diffs)
        b = statistics.median(b for _, b in diffs)
        pct = (r - b) / b
        comps.append(
            Component("cadence", round(r), round(b), note=f"{pct:+.1%} vs runs at a similar pace")
        )
        if pct <= -CADENCE_DROP:
            flags.append(f"cadence {pct:+.0%} at the same pace")
    else:
        comps.append(
            Component("cadence", None, note="not enough runs with cadence at a similar pace")
        )
    return ScoreResult(len(flags), comps, flags)


def early_warnings(
    daily: Mapping[date, Mapping],
    as_of: date,
    acwr: float | None = None,
    form: float | None = None,
    form_flags: Sequence[str] = (),
) -> list[EarlyWarning]:
    out = []
    since = as_of - timedelta(days=ILLNESS_BASELINE_DAYS + 2)

    def baseline(column: str) -> float | None:
        vals = [
            m[column]
            for d, m in daily.items()
            if since <= d < as_of - timedelta(days=1) and m.get(column)
        ]
        return statistics.median(vals) if len(vals) >= 7 else None

    rhr_b, hrv_b, resp_b = (
        baseline("resting_hr_bpm"),
        baseline("hrv_sdnn_ms"),
        baseline("respiratory_rate_bpm"),
    )
    last2 = [daily.get(as_of - timedelta(days=i), {}) for i in (1, 0)]
    if rhr_b and all(m.get("resting_hr_bpm") for m in last2):
        rhr_up = all(m["resting_hr_bpm"] - rhr_b >= RHR_RISE_BPM for m in last2)
        hrv_down = bool(hrv_b) and all(
            m.get("hrv_sdnn_ms") and m["hrv_sdnn_ms"] <= hrv_b * (1 - HRV_DROP) for m in last2
        )
        resp_up = bool(resp_b) and all(
            m.get("respiratory_rate_bpm") and m["respiratory_rate_bpm"] - resp_b >= RESP_RISE
            for m in last2
        )
        if rhr_up and (hrv_down or resp_up):
            evidence = [
                f"resting HR {last2[-1]['resting_hr_bpm']:.0f} vs your usual {rhr_b:.0f} "
                f"two days running"
            ]
            if hrv_down:
                evidence.append(f"HRV {last2[-1]['hrv_sdnn_ms']:.0f} ms vs your usual {hrv_b:.0f}")
            if resp_up:
                evidence.append(
                    f"breathing rate {last2[-1]['respiratory_rate_bpm']:.1f} "
                    f"vs your usual {resp_b:.1f}"
                )
            out.append(
                EarlyWarning(
                    "possible illness",
                    "You might be getting sick: take it easy today and see how you feel tomorrow.",
                    evidence,
                )
            )

    reasons = []
    if acwr is not None and acwr > ACWR_HIGH:
        reasons.append(f"this week's load is {acwr:.1f}× your 4-week average")
    if form is not None and form < FORM_LOW:
        reasons.append(f"form is {form:.0f} (deep fatigue)")
    if len(form_flags) >= 2:
        reasons.append("running form changed: " + ", ".join(form_flags))
    if reasons:
        out.append(
            EarlyWarning(
                "injury risk",
                "Injury risk is up: keep the next few days easy and shorter.",
                reasons,
            )
        )
    return out


def warnings_for(session, day: date) -> dict:  # noqa: ANN001
    """Running form and early warnings for ``day`` from stored data, for the agents."""
    from sqlalchemy import select

    from app.coach.predict import RUN_TYPES
    from app.db.models import DailyMetric, DailyScore, Workout

    since = day - timedelta(days=BASELINE_DAYS)
    columns = [
        "resting_hr_bpm",
        "hrv_sdnn_ms",
        "respiratory_rate_bpm",
        *(col for col, _, _ in FORM_METRICS.values()),
    ]
    daily = {
        m.day: {c: getattr(m, c) for c in columns}
        for m in session.scalars(select(DailyMetric).where(DailyMetric.day.between(since, day)))
    }
    runs = [
        {"day": d, "avg_cadence": cad, "avg_speed_mps": speed}
        for d, cad, speed in session.execute(
            select(Workout.day, Workout.avg_cadence, Workout.avg_speed_mps).where(
                Workout.sport_type.in_(RUN_TYPES), Workout.day.between(since, day)
            )
        )
    ]
    score = session.get(DailyScore, day)
    form = running_form(runs, daily, day)
    warnings = early_warnings(
        daily, day, score.acwr if score else None, score.form if score else None, form.notes
    )
    return {
        "running_form": form.as_dict(),
        "warnings": [
            {"kind": w.kind, "message": w.message, "evidence": w.evidence} for w in warnings
        ],
    }
