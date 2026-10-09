import io
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.db.models import DailyMetric, HealthSample
from app.db.session import SessionLocal
from app.ingest import apple_routes
from app.ingest.apple_export import ExportStats, iter_samples
from app.main import app

WATCH, PHONE = "Jonas’s Apple Watch", "Jonas’s iPhone"


def rec(kind: str, start: str, end: str, value: str, unit: str = "", source: str = WATCH) -> str:
    unit_attr = f' unit="{unit}"' if unit else ""
    return (
        f'<Record type="{kind}" sourceName="{source}"{unit_attr} creationDate="{end}"'
        f' startDate="{start}" endDate="{end}" value="{value}"/>'
    )


EXPORT = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE HealthData [
<!ELEMENT HealthData (ExportDate,Me,(Record|Workout)*)>
<!ATTLIST HealthData locale CDATA #REQUIRED>
]>
<HealthData locale="en_US">
 <ExportDate value="2026-10-09 09:00:00 -0400"/>
 <Me HKCharacteristicTypeIdentifierBiologicalSex="HKBiologicalSexMale"/>
 {
    rec(
        "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
        "2026-10-05 01:34:22 -0400",
        "2026-10-05 01:35:21 -0400",
        "40",
        "ms",
    )
}
 <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" sourceName="{WATCH}" unit="ms"
   startDate="2026-10-05 03:34:25 -0400" endDate="2026-10-05 03:35:24 -0400" value="60">
  <HeartRateVariabilityMetadataList>
   <InstantaneousBeatsPerMinute bpm="55" time="3:34:26.1 AM"/>
  </HeartRateVariabilityMetadataList>
 </Record>
 {
    rec(
        "HKQuantityTypeIdentifierRestingHeartRate",
        "2026-10-05 00:00:00 -0400",
        "2026-10-05 23:59:00 -0400",
        "52",
        "count/min",
    )
}
 {
    rec(
        "HKQuantityTypeIdentifierVO2Max",
        "2026-10-05 08:00:00 -0400",
        "2026-10-05 08:00:00 -0400",
        "48.5",
        "mL/min·kg",
    )
}
 {
    rec(
        "HKCategoryTypeIdentifierSleepAnalysis",
        "2026-10-04 23:00:00 -0400",
        "2026-10-05 03:00:00 -0400",
        "HKCategoryValueSleepAnalysisAsleepCore",
    )
}
 {
    rec(
        "HKCategoryTypeIdentifierSleepAnalysis",
        "2026-10-05 03:00:00 -0400",
        "2026-10-05 04:00:00 -0400",
        "HKCategoryValueSleepAnalysisAsleepDeep",
    )
}
 {
    rec(
        "HKQuantityTypeIdentifierActiveEnergyBurned",
        "2026-10-05 10:00:00 -0400",
        "2026-10-05 10:01:00 -0400",
        "300",
        "kcal",
        WATCH,
    )
}
 {
    rec(
        "HKQuantityTypeIdentifierActiveEnergyBurned",
        "2026-10-05 18:00:00 -0400",
        "2026-10-05 18:01:00 -0400",
        "200",
        "kcal",
        WATCH,
    )
}
 {
    rec(
        "HKQuantityTypeIdentifierActiveEnergyBurned",
        "2026-10-05 10:00:00 -0400",
        "2026-10-05 10:01:00 -0400",
        "280",
        "kcal",
        PHONE,
    )
}
 {
    rec(
        "HKQuantityTypeIdentifierStepCount",
        "2026-10-05 10:00:00 -0400",
        "2026-10-05 10:01:00 -0400",
        "100",
        "count",
    )
}
 {
    rec(
        "HKQuantityTypeIdentifierHeartRateVariabilitySDNN",
        "2025-01-01 01:00:00 -0500",
        "2025-01-01 01:01:00 -0500",
        "70",
        "ms",
    )
}
 {
    rec(
        "HKQuantityTypeIdentifierRestingHeartRate",
        "2026-10-06 00:00:00 -0400",
        "2026-10-06 23:59:00 -0400",
        "fifty",
        "count/min",
    )
}
 <Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30"/>
</HealthData>
"""
SINCE = date(2026, 1, 1)


def samples() -> tuple[list, ExportStats]:
    stats = ExportStats()
    return list(iter_samples(io.BytesIO(EXPORT.encode()), SINCE, stats)), stats


def test_reads_the_metrics_we_use_with_shortcut_rules() -> None:
    got, _ = samples()
    by = {(s.metric, s.category or s.value) for s in got}
    assert ("hrv", 40.0) in by and ("hrv", 60.0) in by
    assert ("resting_hr", 52.0) in by
    assert ("vo2max", 48.5) in by  # Apple's "mL/min·kg" spelling is understood
    assert ("sleep", "core") in by and ("sleep", "deep") in by
    sleep = next(s for s in got if s.category == "core")
    assert sleep.day == date(2026, 10, 5)  # counted toward the morning it ends


def test_active_energy_keeps_one_device_total_per_day_not_both() -> None:
    got, _ = samples()
    energy = [s for s in got if s.metric == "active_energy"]
    assert len(energy) == 1
    assert energy[0].value == 500.0  # Watch 300+200 beats iPhone 280; never 780
    assert energy[0].start.isoformat() == "2026-10-05T00:00:00-04:00"
    assert energy[0].end.isoformat() == "2026-10-06T00:00:00-04:00"


def test_old_records_unknown_types_and_bad_values_are_left_out() -> None:
    got, stats = samples()
    assert not any(s.start.year == 2025 for s in got)  # before `since`
    assert not any(s.metric == "steps" for s in got)
    assert stats.skipped == 1  # value="fifty"
    assert stats.records_seen == 12
    assert stats.by_metric["hrv"] == 2


# --- upload endpoint -----------------------------------------------------------------------


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    # Run the import inline instead of in a thread so the test can check its result.
    monkeypatch.setattr(apple_routes, "start_import", apple_routes.process_export)
    monkeypatch.setattr(apple_routes, "STATE", {"status": "idle"})
    return TestClient(app)


def zipped() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("apple_health_export/export.xml", EXPORT)
        z.writestr("apple_health_export/export_cda.xml", "<ClinicalDocument/>")
    return buf.getvalue()


def upload(api: TestClient, secret: str, content: bytes) -> object:
    return api.post(
        "/ingest/apple-export",
        data={"secret": secret},
        files={"file": ("export.zip", content, "application/zip")},
    )


def test_form_page_renders(api: TestClient) -> None:
    assert "type=file" in api.get("/ingest/apple-export").text


@pytest.mark.usefixtures("db")
def test_upload_with_wrong_secret_is_rejected(api: TestClient, ingest_secret: str) -> None:
    assert upload(api, "wrong", zipped()).status_code == 401
    with SessionLocal() as s:
        assert s.query(HealthSample).count() == 0


@pytest.mark.usefixtures("db")
def test_zip_upload_imports_samples_and_rebuilds_days(
    api: TestClient, ingest_secret: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(apple_routes.get_settings(), "apple_export_days", 400)
    import app.ingest.apple_routes as routes

    class FixedDate(date):
        @classmethod
        def today(cls) -> date:
            return date(2026, 10, 9)

    monkeypatch.setattr(routes, "date", FixedDate)
    response = upload(api, ingest_secret, zipped())
    assert response.status_code == 200, response.text
    status = api.get("/ingest/apple-export/status").json()
    assert status["status"] == "done", status
    assert status["by_metric"]["active_energy"] == 1 and status["skipped"] == 1
    with SessionLocal() as s:
        row = s.get(DailyMetric, date(2026, 10, 5))
        assert (row.hrv_sdnn_ms, row.resting_hr_bpm, row.vo2max) == (50, 52, 48.5)
        assert (row.active_energy_kcal, row.sleep_core_min, row.sleep_deep_min) == (500, 240, 60)


@pytest.mark.usefixtures("db")
def test_export_and_shortcut_samples_do_not_double_count(
    api: TestClient, ingest_secret: str
) -> None:
    # The Shortcut already sent the same HRV reading and the same daily energy total.
    api.post(
        "/ingest/health",
        headers={"X-Ingest-Secret": ingest_secret},
        json={
            "hrv": "2026-10-05T01:34:22-04:00|2026-10-05T01:35:21-04:00|40|ms",
            "active_energy": "2026-10-05T00:00:00-04:00|2026-10-06T00:00:00-04:00|500|kcal",
        },
    )
    upload(api, ingest_secret, zipped())
    with SessionLocal() as s:
        assert s.query(HealthSample).filter_by(metric="hrv").count() == 2  # not 3
        assert s.query(HealthSample).filter_by(metric="active_energy").count() == 1
        assert s.get(DailyMetric, date(2026, 10, 5)).active_energy_kcal == 500


@pytest.mark.usefixtures("db")
def test_bad_file_reports_failure(api: TestClient, ingest_secret: str) -> None:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("notes.txt", "hi")
    upload(api, ingest_secret, buf.getvalue())
    status = api.get("/ingest/apple-export/status").json()
    assert status["status"] == "failed" and "no export.xml" in status["error"]


def test_repeated_energy_records_are_not_summed_twice() -> None:
    once = rec(
        "HKQuantityTypeIdentifierActiveEnergyBurned",
        "2026-10-05 10:00:00 -0400",
        "2026-10-05 10:01:00 -0400",
        "300",
        "kcal",
        WATCH,
    )
    xml = f"<HealthData>{once}{once}</HealthData>"
    got = list(iter_samples(io.BytesIO(xml.encode()), SINCE))
    assert [s.value for s in got] == [300.0]
