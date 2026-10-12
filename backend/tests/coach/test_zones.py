import pytest

from app.coach.zones import format_pace, hr_zones, pace_zones


def test_karvonen_zones_use_heart_rate_reserve() -> None:
    r = hr_zones(52, 191)  # reserve 139
    lows = [c.value for c in r.components]
    highs = [c.baseline for c in r.components]
    assert lows == [122, 135, 149, 163, 177]
    assert highs[-1] == 191 and highs[:-1] == lows[1:]  # contiguous
    assert r.value == 149  # top of zone 2


def test_zones_need_sane_heart_rates() -> None:
    assert hr_zones(60, 55).value is None
    assert hr_zones(None, 190).value is None


def by_name(vdot_value: float) -> dict:
    return {z.name: z for z in pace_zones(vdot_value)}


def test_pace_zones_match_daniels_table_at_vdot_50() -> None:
    z = by_name(50)
    # Daniels' VDOT 50 paces per km: M 4:31, T 4:15, I ≈ 4:00, E ≈ 5:08–5:40.
    assert z["marathon"].fast_s_per_km == pytest.approx(271, abs=2)
    assert z["threshold"].fast_s_per_km == pytest.approx(255, abs=3)
    assert z["interval"].fast_s_per_km == pytest.approx(240, abs=3)
    assert z["easy"].fast_s_per_km == pytest.approx(306, abs=8)
    assert z["easy"].slow_s_per_km == pytest.approx(340, abs=8)


def test_zones_get_faster_in_order() -> None:
    z = pace_zones(45)
    paces = [p.fast_s_per_km for p in z]
    assert paces == sorted(paces, reverse=True)  # easy slowest … repetition fastest
    assert z[0].slow_s_per_km > z[0].fast_s_per_km


def test_mile_pace_and_formatting() -> None:
    t = by_name(50)["threshold"]
    assert t.fast_s_per_mile == pytest.approx(t.fast_s_per_km * 1.609344)
    assert format_pace(255.4) == "4:15" and format_pace(59.6) == "1:00"
