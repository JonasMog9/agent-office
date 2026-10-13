import math
import random
from datetime import date, timedelta

import numpy as np
import pytest

from app.coach.ml.features import FEATURES, Day, find_races, window_features
from app.coach.ml.train import baselines, cross_validate

RACE = date(2019, 9, 29)  # Berlin


def training(weeks: int = 8, km: float = 10, pace_min: float = 5.5, end: date = RACE) -> list[Day]:
    """One run every other day before ``end``."""
    return [Day(end - timedelta(days=i), km, km * pace_min) for i in range(2, weeks * 7 + 1, 2)]


def test_window_features_from_hand_made_days() -> None:
    days = training() + [Day(RACE - timedelta(days=10), 32, 32 * 6.0)]
    f = window_features(days, RACE, male=True)
    total_km = 28 * 10 + 32
    assert f["weekly_km"] == pytest.approx(total_km / 8)
    assert f["long_run_km"] == 32 and f["runs_30k"] == 1
    assert f["run_days_per_week"] == pytest.approx(29 / 8)
    assert f["best_pace_10k"] == pytest.approx(330)  # 5:30/km beats the long run's 6:00
    assert f["male"] == 1.0 and set(FEATURES) <= set(f)


def test_race_day_and_later_days_are_not_features() -> None:
    days = training() + [Day(RACE, 42.4, 200), Day(RACE + timedelta(days=1), 50, 300)]
    assert window_features(days, RACE, True)["long_run_km"] == 10


def test_too_little_training_is_skipped() -> None:
    assert window_features(training(km=3), RACE, True) is None  # 10.5 km/week
    assert window_features(training()[:5], RACE, True) is None  # 5 run days
    assert window_features([], RACE, True) is None


def test_missing_long_days_give_nan_best_pace() -> None:
    f = window_features(training(km=8), RACE, False)
    assert math.isnan(f["best_pace_10k"]) and f["best_day_km"] is None


def test_finds_majors_and_fast_42k_days_but_not_long_training_runs() -> None:
    other = date(2019, 6, 2)
    days = (
        training()
        + [Day(RACE, 42.6, 215)]  # Berlin date
        + training(end=other)
        + [Day(other, 42.3, 200)]  # not a major, but 4:44/km vs 5:30 training
        + training(end=date(2019, 12, 1))
        + [Day(date(2019, 12, 1), 42.5, 270)]  # slow 42 km on a random date: a long run
    )
    days.sort(key=lambda d: d.day)
    found = [r.day for r, _ in find_races(days, True)]
    assert found == [other, RACE]


def test_rejects_implausible_times() -> None:
    days = training() + [Day(RACE, 42.4, 100)]  # 1:40, GPS or a bike ride
    assert find_races(days, True) == []


def synthetic(n_runners: int = 60, seed: int = 0) -> tuple:
    """A made-up population where volume and pace drive marathon time (pipeline test only)."""
    rng = random.Random(seed)
    rows, y, groups = [], [], []
    for a in range(n_runners):
        for _ in range(2):
            weekly = rng.uniform(25, 110)
            pace = rng.uniform(270, 400)
            rows.append(
                {
                    "weekly_km": weekly,
                    "pace_s_per_km": pace,
                    "long_run_km": rng.uniform(18, 35),
                    "runs_30k": rng.randint(0, 5),
                    "run_days_per_week": rng.uniform(3, 6),
                    "recent_share": rng.uniform(0.4, 0.6),
                    "best_pace_10k": pace * 0.93,
                    "male": float(rng.random() < 0.7),
                    "best_day_km": 12.0,
                }
            )
            y.append(1.1 * pace * 42.195 / 60 - 0.4 * weekly + rng.gauss(0, 5))
            groups.append(a)
    x = np.array([[r[f] for f in FEATURES] for r in rows])
    return x, np.array(y), np.array(groups), rows


def test_baselines_are_in_minutes_and_skip_missing_inputs() -> None:
    _, _, _, rows = synthetic(3)
    rows[0] = rows[0] | {"best_day_km": None, "best_pace_10k": float("nan")}
    b = baselines(rows)
    assert np.isnan(b["Riegel"][0]) and not np.isnan(b["Tanda"][0])
    assert 120 < np.nanmedian(b["Tanda"]) < 400


def test_cross_validation_reports_every_method_on_the_same_folds() -> None:
    x, y, groups, rows = synthetic()
    cv = cross_validate(x, y, groups, rows)
    assert {"Ridge", "GBM", "Tanda", "Riegel", "VDOT", "range_80"} <= set(cv)
    assert cv["Ridge"]["mae_min"] < cv["Tanda"]["mae_min"]  # it's a linear world
    assert 0.5 < cv["range_80"]["coverage"] <= 1.0


def test_load_races_reads_bmclab_style_parquet(tmp_path) -> None:  # noqa: ANN001
    pd = pytest.importorskip("pandas")
    pytest.importorskip("pyarrow")
    from app.coach.ml.train import load_races

    days = training() + [Day(RACE, 42.5, 215)]
    df = pd.DataFrame(
        {
            "datetime": pd.to_datetime([d.day for d in days]),
            "athlete": 7,
            "distance": [d.km for d in days],
            "duration": [d.minutes for d in days],
            "gender": "M",
            "age_group": "35 - 54",
            "country": "Brazil",
            "major": "BERLIN 2019",
        }
    )
    path = tmp_path / "run_ww_2019_d.parquet"
    df.to_parquet(path)
    x, y, groups, rows = load_races([str(path)])
    assert x.shape == (1, len(FEATURES)) and y.tolist() == [215] and groups.tolist() == [7]
