from datetime import date, timedelta

import pytest

from app.coach.plan import (
    MAX_WEEKLY_GROWTH,
    Workout,
    adjust,
    build_plan,
    plan_as_dict,
    weekly_volumes,
)

START = date(2026, 10, 14)  # a Wednesday; plans start on that week's Monday
MONDAY = date(2026, 10, 12)


def growth_ok(volumes: list[float]) -> bool:
    """No week more than 10% above the biggest week before it (cutback weeks don't reset it)."""
    return all(v <= max(volumes[:i]) * MAX_WEEKLY_GROWTH + 0.15 for i, v in enumerate(volumes) if i)


def test_twelve_week_half_marathon_plan() -> None:
    race = MONDAY + timedelta(weeks=11, days=6)  # Sunday of week 12
    plan = build_plan(START, 40, 45, race_distance="half marathon", race_date=race)
    assert len(plan.weeks) == 12 and plan.weeks[0].start == MONDAY
    phases = [w.phase for w in plan.weeks]
    assert phases[0] == "base" and phases[-2:] == ["taper", "taper"] and "peak" in phases
    assert phases == sorted(phases, key=["base", "build", "peak", "taper"].index)
    vols = [w.km for w in plan.weeks]
    assert growth_ok(vols[:-2])  # never more than +10% a week
    assert vols[-1] < vols[-2] < max(vols)  # taper
    assert plan.weeks[-1].workouts[-1].kind == "race"
    assert plan.notes == []  # 40 km/week is enough for a half


def test_every_week_adds_up_to_its_target() -> None:
    plan = build_plan(
        START, 35, 42, race_distance="10K", race_date=MONDAY + timedelta(weeks=9, days=6)
    )
    for w in plan.weeks[:-1]:
        assert sum(x.km for x in w.workouts) == pytest.approx(w.km, abs=0.5)
        long_run = next(x for x in w.workouts if x.kind in ("long", "marathon pace"))
        assert long_run.km >= max(x.km for x in w.workouts if x.kind not in ("long",)) - 0.01


def test_quality_sessions_follow_the_phase() -> None:
    plan = build_plan(
        START, 40, 45, race_distance="marathon", race_date=MONDAY + timedelta(weeks=15, days=6)
    )
    kinds = {w.phase: {x.kind for x in w.workouts} for w in plan.weeks}
    assert "strides" in kinds["base"] and "threshold" in kinds["build"]
    assert {"threshold", "intervals", "marathon pace"} <= kinds["peak"]
    assert "race pace" in kinds["taper"]


def test_paces_come_from_vdot() -> None:
    plan = build_plan(
        START, 40, 50, race_distance="10K", race_date=MONDAY + timedelta(weeks=9, days=6)
    )
    threshold = next(x for w in plan.weeks for x in w.workouts if x.kind == "threshold").description
    assert "4:13/km" in threshold  # VDOT 50 threshold; Daniels' table says 4:15 (zones test: ±3 s)


def test_return_from_injury_is_easy_gradual_and_says_so() -> None:
    plan = build_plan(START, 15, 40, returning_from_injury=True, usual_weekly_km=35)
    returning = [w for w in plan.weeks if w.phase == "return"]
    assert len(returning) == 4
    assert returning[0].km == 10.5  # 70% of the current 15 km
    assert all(x.kind in ("easy", "long", "rest") for w in returning for x in w.workouts)
    assert growth_ok([w.km for w in plan.weeks])
    assert any("Return from injury" in n for n in plan.notes)
    assert all(x.km >= 3 or x.kind == "rest" for w in returning for x in w.workouts)


def test_warns_when_a_race_is_too_soon_for_the_volume() -> None:
    plan = build_plan(
        START, 15, 40, race_distance="marathon", race_date=MONDAY + timedelta(weeks=13, days=6)
    )
    assert any("Consider a later race" in n for n in plan.notes)


def test_rejects_impossible_requests() -> None:
    with pytest.raises(ValueError):
        build_plan(START, 30, 40, race_distance="10K", race_date=START + timedelta(days=10))
    with pytest.raises(ValueError):
        build_plan(START, 30, 40, runs_per_week=7)


def test_cutback_every_fourth_week() -> None:
    vols = weekly_volumes(["base"] * 8, 30, 100)
    assert vols[3] < vols[2] and vols[7] < vols[6] and vols[4] > vols[3]


def threshold_day() -> Workout:
    return Workout(START, "threshold", 10, "10 km incl. 4 × 6 min at threshold")


def test_red_recovery_swaps_the_hard_session_for_easy() -> None:
    w = adjust(threshold_day(), "red")
    assert w.kind == "easy" and w.km <= 5 and "red" in w.notes[0]
    easy = adjust(Workout(START, "easy", 8, "8 km easy"), "red")
    assert easy.kind == "rest"


def test_yellow_keeps_running_but_drops_intensity() -> None:
    w = adjust(threshold_day(), "yellow")
    assert w.kind == "strides" and w.km == 10


def test_high_acwr_shortens_and_removes_hard_work() -> None:
    w = adjust(threshold_day(), "green", acwr=1.45)
    assert w.kind == "easy" and w.km == 7.5 and "ACWR 1.45" in w.notes[-1]


def test_pain_means_rest_and_green_means_as_planned() -> None:
    assert adjust(threshold_day(), "green", pain=True).kind == "rest"
    assert adjust(threshold_day(), "green", acwr=1.0) == threshold_day()


def test_plan_is_json_ready() -> None:
    d = plan_as_dict(build_plan(START, 30, 40))
    assert d["weeks"][0]["start"] == "2026-10-12"
    assert isinstance(d["weeks"][0]["workouts"][0]["day"], str)
