"""Apply the trained marathon model (``model.joblib``, see train.py and REPORT.md) to you.

Your runs are summed into daily totals, the same shape as the training data, and turned into
the same 8-week features. The model only predicts when your training looks like what it learned
from (20+ km a week, 8+ run days); otherwise it says why and the formulas carry on alone.
"""

import json
from collections import defaultdict
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from functools import cache
from pathlib import Path

from app.coach.ml.features import FEATURES, MIN_WEEKLY_KM, Day, window_features

HERE = Path(__file__).parent


@cache
def _load() -> dict | None:
    path = HERE / "model.joblib"
    if not path.exists():
        return None
    import joblib

    return joblib.load(path)


@cache
def metrics() -> dict | None:
    path = HERE / "metrics.json"
    return json.loads(path.read_text()) if path.exists() else None


def daily_totals(runs: Sequence[Mapping]) -> list[Day]:
    km, minutes = defaultdict(float), defaultdict(float)
    for r in runs:
        if r.get("distance_m") and r.get("moving_s"):
            km[r["day"]] += r["distance_m"] / 1000
            minutes[r["day"]] += r["moving_s"] / 60
    return [Day(d, km[d], minutes[d]) for d in sorted(km)]


def predict_marathon(
    runs: Sequence[Mapping], as_of: date, male: bool
) -> tuple[float, float, float] | str:
    """(minutes, 10th percentile, 90th percentile), or the reason there's no prediction."""
    bundle = _load()
    if bundle is None:
        return "No trained model (run app/coach/ml/train.py)."
    feats = window_features(daily_totals(runs), as_of + timedelta(days=1), male)  # incl. today
    if feats is None:
        return (
            f"Training too light for the model: it learned from runners doing "
            f"{MIN_WEEKLY_KM}+ km a week over 8 weeks, with at least one 10 km+ run."
        )
    x = [[feats[f] for f in FEATURES]]
    point = float(bundle["model"].predict(x)[0])
    low, high = float(bundle["q10"].predict(x)[0]), float(bundle["q90"].predict(x)[0])
    return point, min(low, point), max(high, point)
