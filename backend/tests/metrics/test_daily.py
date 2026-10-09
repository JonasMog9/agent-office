import math
from datetime import date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.db.models import DailyMetric, DailyScore, Workout
from app.db.session import SessionLocal
from app.main import app
from app.metrics import daily
from app.metrics.daily import days_affected_by, estimate_hr_max, recompute_all, recompute_scores

END = date(2026, 10, 8)


def seed(days: int = 70, with_workout: bool = True) -> None:
    with SessionLocal() as s:
        for i in range(days):
            d = END - timedelta(days=days - 1 - i)
            w = math.sin(i)
            s.add(
                DailyMetric(
                    day=d,
                    hrv_sdnn_ms=50 + 5 * w,
                    resting_hr_bpm=52 + w,
                    respiratory_rate_bpm=16 + 0.3 * w,
                    sleep_asleep_min=450 + 20 * w,
                    sleep_start=datetime(d.year, d.month, d.day, 0, 30),
                )
            )
        if with_workout:
            hr = [150] * 1800
            hr[100] = 230  # a one-second optical spike
            s.add(
                Workout(
                    id=1,
                    sport_type="Run",
                    name="Tempo",
                    start_at=datetime(2026, 10, 7, 10),
                    day=date(2026, 10, 7),
                    moving_s=1800,
                    avg_hr=150,
                    max_hr=230,
                    summary={},
                    streams={"time": list(range(1800)), "heartrate": hr},
                )
            )
        s.commit()


def score(d: date) -> DailyScore:
    with SessionLocal() as s:
        return s.get(DailyScore, d)


@pytest.mark.usefixtures("db")
def test_scores_are_stored_with_their_breakdowns() -> None:
    seed()
    with SessionLocal() as s:
        recompute_scores(s, [date(2026, 10, 7), END])
    run_day, after = score(date(2026, 10, 7)), score(END)
    assert run_day.recovery is not None and run_day.recovery_label in ("green", "yellow", "red")
    assert run_day.strain > 0 and after.strain == 0
    assert after.sleep_need_min >= 480 and after.sleep_debt_min > 0
    assert 0 < after.sleep_performance <= 100 and after.sleep_consistency == 100
    assert {c["name"] for c in run_day.details["recovery"]["components"]} >= {
        "hrv",
        "resting_hr",
        "sleep",
    }
    assert run_day.details["strain"]["components"][0]["note"] == "TRIMP from HR stream"


@pytest.mark.usefixtures("db")
def test_early_days_without_enough_history_have_no_recovery() -> None:
    seed(days=70)
    first = END - timedelta(days=69)
    with SessionLocal() as s:
        recompute_scores(s, [first, first + timedelta(days=20)])
    assert score(first).recovery is None
    assert score(first + timedelta(days=20)).recovery is not None


@pytest.mark.usefixtures("db")
def test_max_hr_estimate_ignores_a_sensor_spike() -> None:
    seed()
    with SessionLocal() as s:
        assert estimate_hr_max(s, END) == 150  # 99th percentile, not the 230 spike


@pytest.mark.usefixtures("db")
def test_max_hr_setting_overrides_the_estimate(monkeypatch: pytest.MonkeyPatch) -> None:
    seed()
    monkeypatch.setenv("MAX_HR", "195")
    get_settings.cache_clear()
    try:
        with SessionLocal() as s:
            assert estimate_hr_max(s, END) == 195
    finally:
        get_settings.cache_clear()


@pytest.mark.usefixtures("db")
def test_no_workouts_means_no_max_hr_and_no_strain() -> None:
    seed(with_workout=False)
    with SessionLocal() as s:
        assert estimate_hr_max(s, END) is None
        recompute_scores(s, [END])
    assert score(END).strain is None and score(END).recovery is not None


def test_a_change_affects_the_next_60_days_but_not_the_future() -> None:
    days = days_affected_by([date(2026, 10, 1)], today=date(2026, 10, 9))
    assert days[0] == date(2026, 10, 1) and days[-1] == date(2026, 10, 9) and len(days) == 9
    assert len(days_affected_by([date(2026, 1, 1)], today=date(2026, 10, 9))) == 61


@pytest.mark.usefixtures("db")
def test_recompute_all_rebuilds_from_the_first_day(monkeypatch: pytest.MonkeyPatch) -> None:
    seed(days=10)

    class Today(date):
        @classmethod
        def today(cls) -> date:
            return END

    monkeypatch.setattr(daily, "date", Today)
    assert recompute_all(SessionLocal) == 10
    assert recompute_all(SessionLocal) == 10  # idempotent
    with SessionLocal() as s:
        assert s.query(DailyScore).count() == 10


@pytest.mark.usefixtures("db")
def test_shortcut_upload_recomputes_scores(ingest_secret: str) -> None:
    seed(with_workout=False)
    TestClient(app).post(
        "/ingest/health",
        headers={"X-Ingest-Secret": ingest_secret},
        json={"hrv": "2026-10-08T03:00:00-04:00|2026-10-08T03:01:00-04:00|80|ms"},
    )
    assert score(END) is not None


@pytest.mark.usefixtures("db")
def test_a_scoring_failure_never_fails_the_upload(
    ingest_secret: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object) -> None:
        raise RuntimeError("bug in a score")

    monkeypatch.setattr(daily, "compute_day", boom)
    response = TestClient(app).post(
        "/ingest/health",
        headers={"X-Ingest-Secret": ingest_secret},
        json={"hrv": "2026-10-08T03:00:00-04:00|2026-10-08T03:01:00-04:00|80|ms"},
    )
    assert response.status_code == 200
    with SessionLocal() as s:
        assert s.get(DailyMetric, END).hrv_sdnn_ms == 80
