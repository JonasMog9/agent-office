"""Personal fitness model: how fast you run at a given heart rate, learned from your own runs.

1. Every run with heart-rate and speed streams is cut into steady 2-minute segments. The first
   5 minutes are skipped (heart rate lags behind pace while warming up), and so are segments
   with stops, walking, or big swings in speed (interval transitions).
2. A robust linear regression (scikit-learn's HuberRegressor, so GPS glitches don't drag it)
   fits  speed ~ heart-rate-reserve fraction + grade  over the last 60 days of segments.
3. Two numbers come out of it, both on flat ground:
     pace at HR 150     your aerobic fitness trend: it drops as you get fitter
     VDOT from HR       Swain's finding that %VO2 reserve ≈ %HR reserve gives
                        VO2max ≈ 3.5 + (VO2 cost of the pace − 3.5) / HRR fraction,
                        evaluated at your typical training HR, so nothing is extrapolated.
4. It's evaluated, not assumed: cross-validation that holds out whole runs compares its error
   (s/km) with the baseline of predicting your average pace. If it doesn't beat that baseline,
   the result says so and gives no estimate.
"""

import statistics
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, timedelta

import numpy as np
from sklearn.linear_model import HuberRegressor
from sklearn.model_selection import GroupKFold

from app.coach.vdot import vo2_cost
from app.metrics.common import Component, ScoreResult

SEGMENT_S = 120
WARMUP_S = 300
MIN_SPEED = 2.0  # m/s (8:20/km); slower is walking or stopped
MAX_SPEED_CV = 0.08
WINDOW_DAYS = 60
MIN_RUNS = 3
MIN_SEGMENTS = 20
REFERENCE_HR = 150
REST_VO2 = 3.5  # ml/kg/min


@dataclass(frozen=True)
class Segment:
    run_id: int
    day: date
    hr: float
    speed: float  # m/s
    grade: float  # %


def segments(run_id: int, day: date, streams: Mapping) -> list[Segment]:
    """Steady 2-minute segments of one run from its Strava streams."""
    t, hr, v = streams.get("time"), streams.get("heartrate"), streams.get("velocity_smooth")
    if not t or not hr or not v:
        return []
    grade = streams.get("grade_smooth") or [0.0] * len(t)
    moving = streams.get("moving") or [True] * len(t)
    n = min(len(t), len(hr), len(v), len(grade), len(moving))
    out, start = [], 0
    while start < n:
        end = start
        while end < n and t[end] - t[start] < SEGMENT_S:
            end += 1
        if end >= n:
            break
        idx = range(start, end)
        if t[start] >= WARMUP_S and all(moving[i] and hr[i] for i in idx):
            speeds = [v[i] for i in idx]
            mean_v = statistics.fmean(speeds)
            if mean_v >= MIN_SPEED and statistics.pstdev(speeds) / mean_v <= MAX_SPEED_CV:
                out.append(
                    Segment(
                        run_id,
                        day,
                        statistics.fmean(hr[i] for i in idx),
                        mean_v,
                        statistics.fmean(grade[i] or 0 for i in idx),
                    )
                )
        start = end
    return out


def _xy(segs: Sequence[Segment], hr_rest: float, hr_max: float) -> tuple[np.ndarray, np.ndarray]:
    x = np.array([[(s.hr - hr_rest) / (hr_max - hr_rest), s.grade] for s in segs])
    return x, np.array([s.speed for s in segs])


def _fit(x: np.ndarray, y: np.ndarray) -> HuberRegressor:
    return HuberRegressor(max_iter=500).fit(x, y)


def _pace_s_per_km(speed: float) -> float:
    return 1000 / speed


def cross_validate(segs: Sequence[Segment], hr_rest: float, hr_max: float) -> tuple[float, float]:
    """(model MAE, baseline MAE) in s/km, holding out whole runs."""
    x, y = _xy(segs, hr_rest, hr_max)
    groups = np.array([s.run_id for s in segs])
    k = min(5, len(set(groups)))
    model_err, base_err = [], []
    for train, test in GroupKFold(n_splits=k).split(x, y, groups):
        predicted = np.clip(_fit(x[train], y[train]).predict(x[test]), 0.5, None)
        baseline = np.full(len(test), y[train].mean())
        actual = 1000 / y[test]
        model_err.extend(np.abs(1000 / predicted - actual))
        base_err.extend(np.abs(1000 / baseline - actual))
    return float(np.mean(model_err)), float(np.mean(base_err))


def fitness(
    segs: Sequence[Segment], hr_rest: float | None, hr_max: float | None, as_of: date
) -> ScoreResult:
    """Fitness as of ``as_of`` from segments in the 60 days before it. Value = VDOT from HR."""
    if not hr_rest or not hr_max or hr_max <= hr_rest:
        return ScoreResult(None, notes=["Needs a resting and a max heart rate."])
    since = as_of - timedelta(days=WINDOW_DAYS)
    window = [s for s in segs if since < s.day <= as_of]
    runs = {s.run_id for s in window}
    if len(runs) < MIN_RUNS or len(window) < MIN_SEGMENTS:
        return ScoreResult(
            None,
            notes=[
                f"Needs {MIN_RUNS}+ runs and {MIN_SEGMENTS}+ steady segments with heart rate in "
                f"the last {WINDOW_DAYS} days; has {len(runs)} runs, {len(window)} segments."
            ],
        )
    x, y = _xy(window, hr_rest, hr_max)
    model = _fit(x, y)
    model_mae, base_mae = cross_validate(window, hr_rest, hr_max)

    typical_hrr = float(np.median(x[:, 0]))
    speed_typical = float(model.predict([[typical_hrr, 0.0]])[0])
    ref_hrr = (REFERENCE_HR - hr_rest) / (hr_max - hr_rest)
    speed_ref = float(model.predict([[ref_hrr, 0.0]])[0])
    vdot_hr = REST_VO2 + (vo2_cost(speed_typical * 60) - REST_VO2) / typical_hrr

    comps = [
        Component(
            f"pace at HR {REFERENCE_HR}",
            round(_pace_s_per_km(speed_ref)),
            note="seconds per km on flat ground; lower = fitter",
        ),
        Component(
            "typical training",
            round(_pace_s_per_km(speed_typical)),
            round(hr_rest + typical_hrr * (hr_max - hr_rest)),
            note="pace (s/km) and heart rate of your median segment, flat ground",
        ),
        Component(
            "slope", round(float(model.coef_[0]) * 0.1 * 60, 1), note="m/min faster per +10% HRR"
        ),
        Component("grade effect", round(float(model.coef_[1]) * 60, 1), note="m/min per +1% grade"),
        Component(
            "cross-validated error",
            round(model_mae, 1),
            round(base_mae, 1),
            note="s/km: model (value) vs. predicting your average pace (baseline)",
        ),
    ]
    notes = [f"{len(window)} segments from {len(runs)} runs in the last {WINDOW_DAYS} days."]
    if model_mae >= base_mae:
        notes.append(
            "The model doesn't beat simply predicting your average pace, so no estimate is given."
        )
        return ScoreResult(None, comps, notes)
    return ScoreResult(round(vdot_hr, 1), comps, notes)
