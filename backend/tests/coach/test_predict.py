from datetime import date, timedelta

import pytest

from app.coach.predict import efforts, predict_races, riegel, tanda_marathon_s, training_volume
from app.coach.vdot import DISTANCES_M, race_time_s, vdot

TODAY = date(2026, 10, 12)


def run(days_ago: int, km: float, minutes: float, best: list | None = None, race: bool = False):
    summary = {"name": "Run", "best_efforts": best or []}
    if race:
        summary["workout_type"] = 1
    return {
        "day": TODAY - timedelta(days=days_ago),
        "distance_m": km * 1000,
        "moving_s": minutes * 60,
        "elapsed_s": minutes * 60,
        "summary": summary,
    }


def be(name: str, metres: float, seconds: float) -> dict:
    return {"name": name, "distance": metres, "elapsed_time": seconds}


def test_riegel_formula() -> None:
    assert riegel(20 * 60, 5000, 10000) == pytest.approx(20 * 60 * 2**1.06)


def test_tanda_formula() -> None:
    # 100 km/week at 4:30/km → (17.1 + 140 e^-0.53 + 0.55 × 270) × 42.195 ≈ 2:54:25
    assert tanda_marathon_s(100, 270) == pytest.approx(10465, abs=5)
    assert tanda_marathon_s(30, 330) > tanda_marathon_s(80, 330)  # low mileage is slower


def test_efforts_skip_short_and_old_ones() -> None:
    runs = [
        run(5, 8, 40, [be("1k", 1000, 210), be("5k", 5000, 1260)]),
        run(80, 10, 45, [be("10k", 10000, 2700)]),  # outside 8 weeks
    ]
    found = efforts(runs, TODAY)
    assert [(e.name, e.is_race) for e in found] == [("5k", False)]


def test_a_race_gives_high_confidence_and_matches_vdot_tables() -> None:
    runs = [run(10, 5, 19 + 57 / 60, race=True)] + [run(i, 10, 50) for i in range(1, 56, 2)]
    p = predict_races(runs, vo2max=None, as_of=TODAY)
    assert p["5K"].label == "high"
    vdot_10k = next(c for c in p["10K"].components if c.name == "VDOT")
    assert vdot_10k.baseline == pytest.approx(50, abs=0.1)
    assert vdot_10k.value == pytest.approx(41 * 60 + 21, rel=0.005)  # Daniels: 41:21


def test_no_efforts_falls_back_to_vo2max_with_low_confidence() -> None:
    p = predict_races([run(3, 5, 30)], vo2max=48.0, as_of=TODAY)
    assert p["5K"].label == "low"
    assert p["5K"].value == round(race_time_s(48.0, DISTANCES_M["5K"]))
    low, high = (lambda c: (c.value, c.baseline))(p["5K"].components[-1])
    assert low < p["5K"].value < high  # ±5% with one method
    assert any("race or time trial" in n for n in p["5K"].notes)


def test_low_mileage_slows_the_marathon_and_is_flagged() -> None:
    best = [be("10k", 10000, 45 * 60)]
    # ~20 km/week: enough for Tanda to apply, well short of marathon volume
    low_volume = [run(3, 10, 45, best)] + [run(i, 8, 44) for i in range(5, 56, 3)]
    p = predict_races(low_volume, vo2max=None, as_of=TODAY)["marathon"]
    tanda = next(c for c in p.components if c.name == "Tanda")
    vdot_m = next(c for c in p.components if c.name == "VDOT")
    assert tanda.value > vdot_m.value
    assert any("km/week" in n for n in p.notes)


def test_nothing_to_go_on() -> None:
    assert predict_races([], None, TODAY)["10K"].value is None


def test_training_volume() -> None:
    weekly, pace = training_volume([run(1, 10, 50), run(8, 6, 33)], TODAY, weeks=2)
    assert weekly == pytest.approx(8) and pace == pytest.approx(83 * 60 / 16)


def test_best_effort_picks_the_fastest_equivalent() -> None:
    runs = [run(3, 6, 30, [be("5k", 5000, 24 * 60)]), run(9, 11, 50, [be("10k", 10000, 42 * 60)])]
    p = predict_races(runs, None, TODAY)["5K"]
    assert next(c for c in p.components if c.name == "VDOT").baseline == pytest.approx(
        round(vdot(10000, 42 * 60), 1)
    )


def test_one_run_cannot_vote_twice_and_the_hr_model_breaks_the_tie() -> None:
    # The owner's case: a careful post-injury run (VDOT ≈ 36), Apple VO2max 53, HR model 42.
    runs = [run(3, 6, 32, [be("5k", 5000, 27 * 60)])]
    p = predict_races(runs, vo2max=53.0, as_of=TODAY, hr_vdot=42.0)["5K"]
    assert p.value == round(race_time_s(42.0, DISTANCES_M["5K"]))  # ≈ 23:00, the median source
    assert p.label == "medium"
    assert any("Methods disagree" in n for n in p.notes)
    low, high = p.components[-1].value, p.components[-1].baseline
    assert high / low == pytest.approx(1.05 / 0.95, rel=1e-3)  # ±5% at medium confidence


def test_without_hr_model_two_sources_average() -> None:
    runs = [run(3, 6, 32, [be("5k", 5000, 27 * 60)])]
    p = predict_races(runs, vo2max=53.0, as_of=TODAY)["5K"]
    effort = [c.value for c in p.components if c.name in ("VDOT", "Riegel")]
    vo2 = next(c.value for c in p.components if c.name == "VO2max")
    assert p.value == round((sum(effort) / 2 + vo2) / 2)
