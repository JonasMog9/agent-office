from datetime import date

import pytest

from app.coach.fitness_age import MEDIANS, MIDPOINTS, age_on, fitness_age, median_at


def test_age_from_birth_month() -> None:
    assert age_on("2002-01", date(2026, 11, 5)) == pytest.approx(24 + 10 / 12)
    assert age_on("2002-01", date(2002, 1, 31)) == 0
    for bad in ("", "2002", "2002-13", "jan 2002", "2030-01"):
        assert age_on(bad, date(2026, 11, 5)) is None


def test_the_median_reads_back_as_its_decade() -> None:
    for sex, med in MEDIANS.items():
        for age, v in zip(MIDPOINTS, med, strict=True):
            assert fitness_age(v, sex).value == age
            assert median_at(age, sex) == v


def test_interpolates_between_decades() -> None:
    assert median_at(30, "male") == pytest.approx((48.0 + 42.4) / 2)
    assert fitness_age((48.0 + 42.4) / 2, "male").value == 30
    assert median_at(10, "male") == 48.0 and median_at(90, "male") == 24.4


def test_clamps_to_the_table_and_says_so() -> None:
    young, old = fitness_age(70, "male"), fitness_age(10, "male")
    assert young.value == 20 and "younger than 20" in young.notes[-1]
    assert old.value == 80 and "older than 80" in old.notes[-1]


def test_labels_against_real_age() -> None:
    assert fitness_age(45, "male", 24.8).label == "older"
    assert fitness_age(48, "male", 24.8).label == "same"
    assert fitness_age(52, "male", 24.8).label == "younger"
    assert fitness_age(48, "male").label is None


def test_women_use_their_own_table() -> None:
    assert fitness_age(37.6, "female").value == 25
    assert fitness_age(37.6, "male").value > 40


def test_no_vo2max_gives_no_age() -> None:
    assert fitness_age(None, "male", 25).value is None
