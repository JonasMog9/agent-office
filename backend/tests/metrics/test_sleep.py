from datetime import datetime

import pytest

from app.metrics.sleep import sleep_consistency, sleep_debt, sleep_need, sleep_performance


def test_debt_sums_shortfalls_and_ignores_missing_nights() -> None:
    r = sleep_debt([480, 420, None, 500, 360], base_need_min=480)
    assert r.value == 60 + 120  # surplus nights don't cancel debt, missing nights aren't zero
    assert r.notes[0] == "Based on 4 of the last 7 nights."


def test_debt_only_looks_at_the_last_seven_nights() -> None:
    assert sleep_debt([0] * 3 + [480] * 7, 480).value == 0


def test_no_recent_sleep() -> None:
    r = sleep_debt([None] * 7, 480)
    assert r.value == 0 and "No sleep recorded recently." in r.notes


def test_need_adds_strain_and_part_of_the_debt() -> None:
    r = sleep_need(480, strain_today=21, debt_min=120)
    assert r.value == 480 + 45 + 30
    assert [c.contribution for c in r.components] == [480, 45.0, 30.0]


def test_debt_repayment_is_capped_at_an_hour() -> None:
    assert sleep_need(480, strain_today=0, debt_min=1000).value == 540


def test_rest_day_without_debt_needs_the_baseline() -> None:
    assert sleep_need(480, strain_today=None, debt_min=0).value == 480


@pytest.mark.parametrize(("asleep", "pct"), [(480, 100), (360, 75), (600, 100)])
def test_performance(asleep: float, pct: int) -> None:
    assert sleep_performance(asleep, 480).value == pct


def test_performance_without_data() -> None:
    assert sleep_performance(None, 480).value is None


def test_consistency_handles_bedtimes_either_side_of_midnight() -> None:
    nights = [
        datetime(2026, 10, d, h, m)
        for d, h, m in [(1, 23, 30), (2, 0, 30), (3, 23, 30), (4, 0, 30)]
    ]
    r = sleep_consistency(nights)
    assert r.components[0].value == 30.0 and r.value == 70  # ±30 min, not ±11.5 h


def test_consistency_needs_three_nights() -> None:
    assert (
        sleep_consistency([datetime(2026, 10, 1, 23), None, datetime(2026, 10, 2, 23)]).value
        is None
    )
