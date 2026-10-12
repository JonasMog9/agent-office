import pytest

from app.coach.load import CTL_DAYS, flags, load_series, training_load


def test_steady_training_converges_to_the_daily_load() -> None:
    day = load_series([100] * 365)[-1]
    assert day.ctl == pytest.approx(100, abs=0.1) and day.atl == pytest.approx(100, abs=0.1)
    assert day.form == pytest.approx(0, abs=0.1) and day.acwr == pytest.approx(1)


def test_one_step_matches_the_formula() -> None:
    first = load_series([84])[0]
    assert first.ctl == pytest.approx(84 / 42) and first.atl == pytest.approx(84 / 7)
    assert first.form == 0  # nothing before it


def test_missing_days_are_rest_days() -> None:
    assert load_series([50, None, 50]) == load_series([50, 0, 50])


def test_a_big_week_after_a_quiet_month_flags_injury_risk() -> None:
    history = [40] * 21 + [150] * 7
    day = load_series(history)[-1]
    assert day.acwr > 1.5
    assert any("Injury risk high" in f for f in flags(day))
    assert day.form < -30  # fatigue jumped far above fitness


def test_acwr_needs_four_weeks_and_some_load() -> None:
    assert load_series([50] * 27)[-1].acwr is None
    assert load_series([0] * 40)[-1].acwr is None


def test_taper_reads_as_fresh_and_low_load() -> None:
    day = load_series([120] * 60 + [20] * 10)[-1]
    fl = flags(day)
    assert day.form > 25 and day.acwr < 0.8
    assert any("Very fresh" in f for f in fl) and any("well below" in f for f in fl)


def test_breakdown_and_short_history_note() -> None:
    r = training_load([60] * 10)
    names = [c.name for c in r.components]
    assert names[:4] == ["fitness (CTL)", "fatigue (ATL)", "form", "ACWR"]
    assert any(f"~{CTL_DAYS}" in n for n in r.notes)
    assert training_load([]).value is None
