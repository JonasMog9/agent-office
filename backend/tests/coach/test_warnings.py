from datetime import date, datetime, timedelta

import pytest

from app.coach.warnings import early_warnings, running_form, warnings_for
from app.db.models import DailyMetric, DailyScore, Workout
from app.db.session import SessionLocal

TODAY = date(2026, 10, 13)


def days(n: int, **values) -> dict:
    """``n`` days of identical metrics ending yesterday, with a little day-to-day wobble."""
    out = {}
    for i in range(1, n + 1):
        wobble = (i % 3 - 1) * 0.01  # ±1%
        out[TODAY - timedelta(days=i)] = {k: v * (1 + wobble) for k, v in values.items()}
    return out


NORMAL = {"resting_hr_bpm": 52, "hrv_sdnn_ms": 55, "respiratory_rate_bpm": 16.5}


def sick_days(rhr: float, hrv: float, resp: float = 16.5) -> dict:
    d = days(30, **NORMAL)
    for i in (0, 1):
        d[TODAY - timedelta(days=i)] = {
            "resting_hr_bpm": rhr,
            "hrv_sdnn_ms": hrv,
            "respiratory_rate_bpm": resp,
        }
    return d


def test_illness_needs_both_rhr_up_and_hrv_down_for_two_days() -> None:
    [w] = early_warnings(sick_days(rhr=58, hrv=40), TODAY)
    assert w.kind == "possible illness" and "resting HR 58 vs your usual 52" in w.evidence[0]
    assert early_warnings(sick_days(rhr=58, hrv=54), TODAY) == []  # HRV fine
    assert early_warnings(sick_days(rhr=55, hrv=40), TODAY) == []  # RHR only +3

    one_day = sick_days(rhr=58, hrv=40)
    one_day[TODAY - timedelta(days=1)] = dict(NORMAL)
    assert early_warnings(one_day, TODAY) == []  # just today: wait for a second day


def test_raised_breathing_rate_supports_or_replaces_the_hrv_signal() -> None:
    [w] = early_warnings(sick_days(rhr=58, hrv=54, resp=18), TODAY)
    assert any("breathing rate" in e for e in w.evidence)


def test_no_baseline_no_illness_call() -> None:
    d = {TODAY: {"resting_hr_bpm": 70, "hrv_sdnn_ms": 20}}
    assert early_warnings(d, TODAY) == []


def test_injury_risk_from_load_fatigue_or_form() -> None:
    normal = days(30, **NORMAL)
    assert early_warnings(normal, TODAY, acwr=1.2, form=-5) == []
    [w] = early_warnings(normal, TODAY, acwr=1.6)
    assert w.kind == "injury risk" and "1.6×" in w.evidence[0]
    assert early_warnings(normal, TODAY, form=-35)[0].kind == "injury risk"
    assert early_warnings(normal, TODAY, form_flags=["a"]) == []  # one form flag isn't enough
    assert early_warnings(normal, TODAY, form_flags=["a", "b"])[0].kind == "injury risk"


def form_history(recent: dict, base: dict) -> dict:
    out = {}
    for i in range(1, 15):
        out[TODAY - timedelta(days=i - 1)] = dict(recent)
    for i in range(15, 80):
        out[TODAY - timedelta(days=i)] = dict(base)
    return out


BASE_FORM = {"ground_contact_ms": 250, "vertical_oscillation_cm": 9.0, "stride_length_m": 1.10}


def test_running_form_flags_more_ground_time_and_shorter_strides() -> None:
    tired = {"ground_contact_ms": 268, "vertical_oscillation_cm": 9.1, "stride_length_m": 1.04}
    r = running_form([], form_history(tired, BASE_FORM), TODAY)
    assert r.value == 2
    assert any("ground contact +7%" in n for n in r.notes)
    assert any("stride length -5%" in n for n in r.notes)


def test_running_form_quiet_when_stable_or_unknown() -> None:
    assert running_form([], form_history(BASE_FORM, BASE_FORM), TODAY).value == 0
    r = running_form([], {}, TODAY)
    assert r.value == 0 and all(c.value is None for c in r.components)


def run(days_ago: int, cadence_per_foot: float, pace_s_per_km: float) -> dict:
    return {
        "day": TODAY - timedelta(days=days_ago),
        "avg_cadence": cadence_per_foot,
        "avg_speed_mps": 1000 / pace_s_per_km,
    }


def test_cadence_is_compared_at_the_same_pace() -> None:
    base = [run(20 + i, 82, 360) for i in range(6)] + [run(20 + i, 88, 290) for i in range(6)]
    # Recent easy runs at 6:00/km, same cadence as before: no flag, even though the old
    # fast runs had higher cadence.
    same = running_form(base + [run(i, 82, 362) for i in range(1, 5)], {}, TODAY)
    assert same.value == 0
    cad = next(c for c in same.components if c.name == "cadence")
    assert cad.value == 164 and cad.baseline == 164  # per-foot × 2
    dropped = running_form(base + [run(i, 78, 360) for i in range(1, 5)], {}, TODAY)
    assert dropped.value == 1 and "cadence -5% at the same pace" in dropped.notes


@pytest.mark.usefixtures("db")
def test_warnings_for_reads_stored_data() -> None:
    with SessionLocal() as s:
        for d, m in sick_days(rhr=58, hrv=40).items():
            s.add(DailyMetric(day=d, **m))
        s.add(DailyScore(day=TODAY, acwr=1.7, form=-10, details={}))
        s.add(
            Workout(
                id=1,
                sport_type="Run",
                name="r",
                start_at=datetime(2026, 10, 12, 7),
                day=TODAY - timedelta(days=1),
                avg_cadence=82,
                avg_speed_mps=2.8,
                summary={},
            )
        )
        s.commit()
        out = warnings_for(s, TODAY)
    kinds = [w["kind"] for w in out["warnings"]]
    assert kinds == ["possible illness", "injury risk"]
    assert out["running_form"]["value"] == 0
