from datetime import date, timedelta

import pytest

from app.coach.ml.model import daily_totals, metrics, predict_marathon
from app.coach.predict import predict_races

TODAY = date(2026, 10, 13)


def runs(weekly_km: float, pace_s_per_km: float) -> list[dict]:
    """8 realistic weeks: a long run (30% of the week, 8% slower) plus four equal runs."""
    out = []
    for week in range(8):
        sunday = TODAY - timedelta(days=7 * week)
        long_km, other_km = 0.3 * weekly_km, 0.7 * weekly_km / 4
        out.append(run(sunday, long_km, pace_s_per_km * 1.08))
        out += [run(sunday - timedelta(days=d), other_km, pace_s_per_km) for d in (2, 3, 4, 6)]
    return out


def run(day: date, km: float, pace: float) -> dict:
    return {"day": day, "distance_m": km * 1000, "moving_s": km * pace}


def test_daily_totals_sum_runs_on_the_same_day() -> None:
    two = [{"day": TODAY, "distance_m": 5000, "moving_s": 1500}] * 2
    [day] = daily_totals(two)
    assert (day.km, day.minutes) == (10, 50)


def test_model_ships_with_metrics_that_beat_the_formulas() -> None:
    m = metrics()
    assert m is not None and not m["keep_baseline"]
    assert m["cv"][m["chosen"]]["mae_min"] < m["cv"][m["best_baseline"]]["mae_min"]


def test_predicts_a_sane_marathon_with_a_range() -> None:
    minutes, p10, p90 = predict_marathon(runs(60, 330), TODAY, male=True)
    assert 180 < minutes < 270 and p10 <= minutes <= p90


def test_more_volume_and_faster_training_predict_a_faster_marathon() -> None:
    slow = predict_marathon(runs(35, 360), TODAY, male=True)[0]
    fast = predict_marathon(runs(90, 300), TODAY, male=True)[0]
    assert fast < slow - 20


def test_too_little_training_explains_itself() -> None:
    reason = predict_marathon(runs(10, 360), TODAY, male=True)
    assert isinstance(reason, str) and "20+ km" in reason


def test_ml_shows_up_beside_the_formulas() -> None:
    r = runs(60, 330)
    p = predict_races(r, None, TODAY, ml_marathon=predict_marathon(r, TODAY, True))["marathon"]
    ml = next(c for c in p.components if c.name == "ML")
    assert "80% range" in ml.note and ml.value == pytest.approx(p.value, rel=0.25)
    light = predict_races(r, None, TODAY, ml_marathon="Training too light")["marathon"]
    assert "Training too light" in light.notes
