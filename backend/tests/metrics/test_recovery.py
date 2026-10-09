import math

import pytest

from app.metrics.recovery import MIN_HISTORY, label_for, recovery


def day(hrv=50.0, rhr=52.0, resp=16.0, temp=None, asleep=480.0) -> dict:
    return {
        "hrv_sdnn_ms": hrv,
        "resting_hr_bpm": rhr,
        "respiratory_rate_bpm": resp,
        "wrist_temp_c": temp,
        "sleep_asleep_min": asleep,
    }


def history(n=60, **overrides) -> list[dict]:
    # Gentle day-to-day variation around 50 ms HRV / 52 bpm / 16 breaths.
    rows = []
    for i in range(n):
        wobble = math.sin(i)
        rows.append(day(hrv=50 + 5 * wobble, rhr=52 + wobble, resp=16 + 0.3 * wobble) | overrides)
    return rows


def comp(result, name):
    return next(c for c in result.components if c.name == name)


def test_a_typical_day_scores_near_the_middle() -> None:
    r = recovery(day(), history())
    assert 40 <= r.value <= 60 and r.label == "yellow"


def test_better_than_usual_is_green_and_worse_is_red() -> None:
    assert recovery(day(hrv=70, rhr=48, resp=15.5), history()).label == "green"
    bad = recovery(day(hrv=32, rhr=58, resp=17.5, asleep=330), history())
    assert bad.label == "red"
    assert comp(bad, "hrv").z < 0 and comp(bad, "resting_hr").z < 0  # signed: negative = worse


def test_weights_of_used_components_sum_to_one_and_contributions_add_up() -> None:
    r = recovery(day(), history())
    used = [c for c in r.components if c.z is not None]
    assert sum(c.weight for c in used) == pytest.approx(1, abs=1e-3)
    assert {c.name for c in used} == {"hrv", "resting_hr", "respiratory_rate", "sleep"}


def test_missing_inputs_are_reweighted_and_noted() -> None:
    r = recovery(day(resp=None, asleep=None), history())
    assert r.value is not None
    assert comp(r, "respiratory_rate").note == "no reading today"
    assert sum(c.weight for c in r.components if c.weight) == pytest.approx(1, abs=1e-3)
    assert any("reweighted" in n for n in r.notes)


def test_a_signal_never_recorded_is_left_out_quietly() -> None:
    r = recovery(day(), history())  # no wrist temperature anywhere, as on older watches
    assert "wrist_temp" not in {c.name for c in r.components}
    assert not any("reweighted" in n for n in r.notes)
    assert any("wrist_temp" in n for n in r.notes)


def test_a_tracked_signal_missing_today_is_still_listed() -> None:
    r = recovery(day(), history(wrist_temp_c=36.0))
    assert comp(r, "wrist_temp").note == "no reading today"
    assert any("reweighted" in n for n in r.notes)


def test_no_hrv_and_no_resting_hr_means_no_score() -> None:
    r = recovery(day(hrv=None, rhr=None), history())
    assert r.value is None and r.label is None


def test_short_history_drops_components_until_there_are_enough_days() -> None:
    r = recovery(day(), history(n=MIN_HISTORY - 1))
    assert r.value is None  # neither HRV nor RHR has a baseline yet
    assert f"has {MIN_HISTORY - 1}" in comp(r, "hrv").note
    assert recovery(day(), history(n=MIN_HISTORY)).value is not None


def test_missing_days_in_history_only_count_what_exists() -> None:
    rows = history()
    for i in range(0, 60, 2):
        rows[i] = day(hrv=None, rhr=None, resp=None, asleep=None)  # watch off every other day
    r = recovery(day(), rows)
    assert r.value is not None and comp(r, "hrv").baseline == pytest.approx(50, abs=3)


def test_an_outlier_in_the_baseline_does_not_move_it() -> None:
    clean = recovery(day(), history())
    rows = history()
    rows[10] = day(hrv=400)  # a sensor glitch, 8× normal
    # The median moves by at most one rank, so the score barely changes (a mean would jump).
    assert abs(recovery(day(), rows).value - clean.value) <= 1


def test_an_extreme_reading_today_is_capped() -> None:
    r = recovery(day(hrv=5), history())
    assert comp(r, "hrv").z == -3.0


def test_a_perfectly_flat_baseline_still_gives_sane_z_scores() -> None:
    # Resting HR was exactly 52 every day: a 2 bpm rise must not read as infinitely bad.
    r = recovery(day(rhr=54), history(resting_hr_bpm=52.0))
    assert comp(r, "resting_hr").z == pytest.approx(-2.0)


def test_wrist_temperature_shift_hurts_in_either_direction() -> None:
    rows = history(wrist_temp_c=36.0)
    warm, cold = recovery(day(temp=36.5), rows), recovery(day(temp=35.5), rows)
    assert comp(warm, "wrist_temp").z < 0 and comp(cold, "wrist_temp").z < 0


def test_short_sleep_lowers_the_score() -> None:
    assert recovery(day(asleep=300), history()).value < recovery(day(asleep=480), history()).value


@pytest.mark.parametrize(
    ("score", "label"), [(67, "green"), (66, "yellow"), (34, "yellow"), (33, "red")]
)
def test_zone_boundaries(score: int, label: str) -> None:
    assert label_for(score) == label
