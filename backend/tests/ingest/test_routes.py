from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.db.models import DailyMetric, HealthSample, RawPayload
from app.db.session import SessionLocal
from app.main import app

client = TestClient(app)

PAYLOAD = {
    "hrv": "2026-10-07T03:00:00-07:00|2026-10-07T03:01:00-07:00|40|ms\n"
    "2026-10-07T05:00:00-07:00|2026-10-07T05:01:00-07:00|60|ms",
    "resting_hr": "2026-10-07T00:00:00-07:00|2026-10-07T23:59:00-07:00|52|count/min",
    "sleep": "2026-10-06T23:00:00-07:00|2026-10-07T06:30:00-07:00|Core",
}


def post(body: dict, secret: str | None) -> object:
    headers = {"X-Ingest-Secret": secret} if secret else {}
    return client.post("/ingest/health", json=body, headers=headers)


def day_row(day: date) -> DailyMetric:
    with SessionLocal() as s:
        return s.get(DailyMetric, day)


def count(model: type) -> int:
    with SessionLocal() as s:
        return s.scalar(select(func.count()).select_from(model))


@pytest.mark.usefixtures("db")
def test_rejects_everything_when_no_secret_is_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.config import get_settings

    monkeypatch.setenv("INGEST_SECRET", "")
    get_settings.cache_clear()
    assert post(PAYLOAD, "anything").status_code == 503
    get_settings.cache_clear()


@pytest.mark.usefixtures("db")
@pytest.mark.parametrize("secret", [None, "wrong"])
def test_rejects_a_missing_or_wrong_secret(ingest_secret: str, secret: str | None) -> None:
    assert post(PAYLOAD, secret).status_code == 401
    assert count(RawPayload) == 0


@pytest.mark.usefixtures("db")
def test_stores_raw_samples_and_daily_row(ingest_secret: str) -> None:
    response = post(PAYLOAD, ingest_secret)
    assert response.status_code == 200
    assert response.json() == {
        "samples": 4,
        "days_updated": ["2026-10-07"],
        "skipped": [],
        "skipped_count": 0,
        "unknown_fields": [],
    }
    row = day_row(date(2026, 10, 7))
    assert (row.hrv_sdnn_ms, row.resting_hr_bpm, row.sleep_core_min) == (50, 52, 450)
    assert count(RawPayload) == 1


@pytest.mark.usefixtures("db")
def test_resending_the_same_days_does_not_duplicate(ingest_secret: str) -> None:
    for _ in range(3):
        assert post(PAYLOAD, ingest_secret).status_code == 200
    assert count(HealthSample) == 4
    assert count(DailyMetric) == 1
    assert day_row(date(2026, 10, 7)).hrv_sdnn_ms == 50


@pytest.mark.usefixtures("db")
def test_a_partial_resend_never_loses_earlier_samples(ingest_secret: str) -> None:
    # The 3-day window can cut the oldest day in half; the earlier, fuller upload must survive.
    post(PAYLOAD, ingest_secret)
    post({"hrv": "2026-10-07T05:00:00-07:00|2026-10-07T05:01:00-07:00|60|ms"}, ingest_secret)
    assert day_row(date(2026, 10, 7)).hrv_sdnn_ms == 50


@pytest.mark.usefixtures("db")
def test_new_samples_update_the_day(ingest_secret: str) -> None:
    post(PAYLOAD, ingest_secret)
    post({"hrv": "2026-10-07T21:00:00-07:00|2026-10-07T21:01:00-07:00|80|ms"}, ingest_secret)
    assert day_row(date(2026, 10, 7)).hrv_sdnn_ms == 60


@pytest.mark.usefixtures("db")
def test_missing_days_simply_have_no_row(ingest_secret: str) -> None:
    post(PAYLOAD, ingest_secret)
    post({"hrv": "2026-10-09T03:00:00-07:00|2026-10-09T03:01:00-07:00|55|ms"}, ingest_secret)
    assert day_row(date(2026, 10, 8)) is None
    assert day_row(date(2026, 10, 9)).hrv_sdnn_ms == 55


@pytest.mark.usefixtures("db")
def test_bad_lines_are_reported_not_fatal(ingest_secret: str) -> None:
    response = post({"hrv": "garbage\n" + PAYLOAD["hrv"], "steps": "1"}, ingest_secret)
    body = response.json()
    assert response.status_code == 200
    assert (body["samples"], body["skipped_count"], body["unknown_fields"]) == (2, 1, ["steps"])
