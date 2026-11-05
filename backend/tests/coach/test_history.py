from datetime import date

import pytest

from app.coach import history

D = date(2026, 11, 5)  # a Thursday; its week starts Mon 2 Nov


def run(day, km, minutes, **kw):
    return {
        "day": day,
        "name": kw.pop("name", "Run"),
        "distance_m": km * 1000,
        "moving_s": minutes * 60,
    } | kw


def test_weekly_totals_include_empty_weeks_and_start_on_monday():
    runs = [
        run(date(2026, 11, 2), 10, 50, elevation_m=40),
        run(date(2026, 11, 5), 5.5, 30),
        run(date(2026, 10, 18), 21, 110),  # a Sunday: the week of 12 Oct
        run(date(2025, 1, 1), 99, 600),  # too old: not counted
    ]
    weeks = history.weekly_totals(runs, D, weeks=4)
    assert [w["week"] for w in weeks] == ["2026-10-12", "2026-10-19", "2026-10-26", "2026-11-02"]
    assert [w["km"] for w in weeks] == [21.0, 0.0, 0.0, 15.5]
    assert weeks[-1] == {"week": "2026-11-02", "km": 15.5, "runs": 2, "minutes": 80, "climb_m": 40}


def test_daily_km_adds_up_two_runs_on_one_day():
    days = history.daily_km(
        [run(D, 5, 25), run(D, 3, 15), run(date(2026, 11, 1), 8, 40)], D, days=5
    )
    assert days == [
        {"day": "2026-11-01", "km": 8.0},
        {"day": "2026-11-02", "km": 0.0},
        {"day": "2026-11-03", "km": 0.0},
        {"day": "2026-11-04", "km": 0.0},
        {"day": "2026-11-05", "km": 8.0},
    ]


def test_totals_and_an_empty_history():
    t = history.totals([run(D, 10, 50, elevation_m=12.4), run(D, 21.1, 115, elevation_m=None)])
    assert t == {"runs": 2, "km": 31.1, "hours": 2.8, "climb_m": 12, "longest_km": 21.1}
    assert history.totals([]) == {"runs": 0, "km": 0, "hours": 0, "climb_m": 0, "longest_km": None}


def test_personal_records_keep_the_fastest_per_distance():
    efforts = lambda *be: {"best_efforts": [{"name": n, "elapsed_time": t} for n, t in be]}  # noqa: E731
    runs = [
        run(date(2026, 9, 1), 10, 50, name="Tempo", summary=efforts(("5k", 1290), ("1k", 240))),
        run(date(2026, 10, 1), 5, 21, name="Parkrun", summary=efforts(("5k", 1250), ("1k", 245))),
        run(date(2026, 10, 2), 5, 30, summary=efforts(("Ultra", 1), ("10k", None))),  # skipped
        run(date(2026, 10, 3), 5, 30),  # no summary
    ]
    prs = history.personal_records(runs)
    assert [(p["name"], p["seconds"], p["run"]) for p in prs] == [
        ("1k", 240, "Tempo"),
        ("5k", 1250, "Parkrun"),
    ]
    assert prs[1]["day"] == "2026-10-01" and prs[1]["distance_m"] == 5000


BOUNDS = [(1, 100, 120), (2, 120, 140), (3, 140, 160), (4, 160, 180), (5, 180, 200)]


def test_zone_of_clamps_below_and_above():
    assert [history.zone_of(hr, BOUNDS) for hr in (80, 119, 120, 159, 199, 230)] == [
        1,
        1,
        2,
        3,
        5,
        5,
    ]


def test_time_in_zones_skips_pauses_and_missing_samples():
    streams = [
        {"time": [0, 30, 60, 90, 400, 430], "heartrate": [130, 150, 150, 0, 170, 170]},
        {"time": [0, 30], "heartrate": [190]},  # one HR sample: nothing to time
        {},  # a run without streams
    ]
    # 0→30 at 130 (Z2), 30→90 at 150 (Z3), 90→400 is a pause, 400→430 at 170 (Z4)
    assert history.time_in_zones(streams, BOUNDS) == {1: 0, 2: 0.5, 3: 1.0, 4: 0.5, 5: 0}


def test_run_rows_are_newest_first_with_pace():
    rows = history.run_rows(
        [
            run(date(2026, 11, 1), 10, 52, avg_hr=148.6, cadence_spm=171.4, elevation_m=0),
            run(D, 0, 0, name=""),
        ],
        limit=5,
    )
    assert (
        rows[0]["day"] == "2026-11-05"
        and rows[0]["name"] == "Run"
        and rows[0]["pace_s_per_km"] is None
    )
    assert rows[1] | {} == {
        "day": "2026-11-01",
        "name": "Run",
        "km": 10.0,
        "moving_s": 3120,
        "pace_s_per_km": 312,
        "avg_hr": 149,
        "climb_m": 0,
        "cadence_spm": 171,
    }


def test_pace():
    assert history.pace_s_per_km(5000, 1500) == pytest.approx(300)
    assert history.pace_s_per_km(None, 100) is None
