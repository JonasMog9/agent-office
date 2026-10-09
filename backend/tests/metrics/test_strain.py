import math

import pytest

from app.metrics.strain import (
    daily_strain,
    strain_from_trimp,
    trimp_from_average,
    trimp_from_stream,
)

REST, MAX = 50.0, 190.0


def banister(minutes: float, hr: float, a: float = 0.64, b: float = 1.92) -> float:
    hrr = (hr - REST) / (MAX - REST)
    return minutes * hrr * a * math.exp(b * hrr)


def test_stream_trimp_matches_the_formula_for_a_steady_effort() -> None:
    times = list(range(0, 1801))  # 30 minutes, one sample per second
    assert trimp_from_stream(times, [155] * len(times), REST, MAX, "male") == pytest.approx(
        banister(30, 155)
    )


def test_pauses_in_the_stream_are_not_counted_as_effort() -> None:
    times = list(range(0, 601))  # 10 minutes at 1 Hz
    steady = trimp_from_stream(times, [150] * 601, REST, MAX, "male")
    paused = trimp_from_stream(
        times + [4200], [150] * 602, REST, MAX, "male"
    )  # then an hour's stop
    assert paused == pytest.approx(steady + banister(0.5, 150))  # the gap counts as at most 30 s


def test_average_hr_fallback() -> None:
    assert trimp_from_average(45, 140, REST, MAX, "male") == pytest.approx(banister(45, 140))


def test_women_use_their_own_coefficients() -> None:
    assert trimp_from_average(45, 140, REST, MAX, "female") == pytest.approx(
        banister(45, 140, 0.86, 1.67)
    )


def test_heart_rate_below_rest_or_above_max_is_clipped() -> None:
    assert trimp_from_average(30, 40, REST, MAX, "male") == 0
    assert trimp_from_average(30, 220, REST, MAX, "male") == pytest.approx(banister(30, MAX))


@pytest.mark.parametrize(
    ("trimp", "low", "high"), [(0, 0, 0), (50, 5.5, 7), (120, 11, 12.5), (300, 17.5, 19)]
)
def test_strain_scale(trimp: float, low: float, high: float) -> None:
    assert low <= strain_from_trimp(trimp) <= high


def test_strain_never_reaches_21_and_always_increases() -> None:
    values = [strain_from_trimp(t) for t in (100, 200, 400, 800, 5000)]
    assert values == sorted(values) and values[-1] <= 21


def test_daily_strain_sums_workouts_and_explains_each() -> None:
    run = {
        "sport_type": "Run",
        "name": "Tempo",
        "streams": {"time": list(range(3601)), "heartrate": [160] * 3601},
    }
    lift = {"sport_type": "WeightTraining", "name": "Gym", "avg_hr": 110, "moving_s": 2700}
    walk = {"sport_type": "Walk", "name": "No watch", "moving_s": 1200}
    r = daily_strain([run, lift, walk], REST, MAX)
    assert [c.note for c in r.components] == [
        "TRIMP from HR stream",
        "TRIMP from average HR",
        "no heart rate recorded",
    ]
    total = r.components[0].value + r.components[1].value
    assert r.value == strain_from_trimp(total)


def test_rest_day_is_zero_with_a_note() -> None:
    r = daily_strain([], REST, MAX)
    assert r.value == 0 and any("No workouts" in n for n in r.notes)


def test_missing_heart_rate_settings_means_no_strain() -> None:
    assert daily_strain([], None, MAX).value is None
    assert daily_strain([], 60, 55).value is None


def test_unknown_sex_is_rejected() -> None:
    with pytest.raises(ValueError):
        daily_strain([], REST, MAX, sex="other")
