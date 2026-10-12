import pytest

from app.coach.vdot import DISTANCES_M, race_time_s, vdot

M = DISTANCES_M


def hms(h: int, m: int, s: int) -> int:
    return h * 3600 + m * 60 + s


# Rows from Daniels' Running Formula VDOT table: (VDOT, 5K, 10K, half, marathon).
TABLE = [
    (40, hms(0, 24, 8), hms(0, 50, 3), hms(1, 50, 59), hms(3, 49, 45)),
    (50, hms(0, 19, 57), hms(0, 41, 21), hms(1, 31, 35), hms(3, 10, 49)),
    (60, hms(0, 17, 3), hms(0, 35, 22), hms(1, 18, 9), hms(2, 43, 25)),
]
RACES = ["5K", "10K", "half marathon", "marathon"]


@pytest.mark.parametrize("row", TABLE)
def test_vdot_matches_daniels_table(row: tuple) -> None:
    expected, *times = row
    for race, t in zip(RACES, times, strict=True):
        assert vdot(M[race], t) == pytest.approx(expected, abs=0.15), race


@pytest.mark.parametrize("row", TABLE)
def test_race_times_match_daniels_table_within_half_a_percent(row: tuple) -> None:
    value, *times = row
    for race, t in zip(RACES, times, strict=True):
        assert race_time_s(value, M[race]) == pytest.approx(t, rel=0.005), race


def test_round_trip() -> None:
    t = race_time_s(47.3, M["10K"])
    assert vdot(M["10K"], t) == pytest.approx(47.3, abs=1e-6)


def test_faster_is_higher() -> None:
    assert vdot(M["5K"], hms(0, 18, 0)) > vdot(M["5K"], hms(0, 22, 0))


def test_rejects_nonsense() -> None:
    with pytest.raises(ValueError):
        vdot(0, 600)
