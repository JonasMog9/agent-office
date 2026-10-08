from datetime import date, datetime, timedelta, timezone

from app.ingest.daily import summarize_day
from app.ingest.shortcut import Sample

TZ = timezone(timedelta(hours=-7))
DAY = date(2026, 10, 7)


def at(hour: float) -> datetime:
    """A time on DAY (negative hours reach back into the previous evening)."""
    return datetime(2026, 10, 7, tzinfo=TZ) + timedelta(hours=hour)


def num(metric: str, value: float, hour: float = 8) -> Sample:
    return Sample(metric, at(hour), at(hour) + timedelta(minutes=1), value, "", DAY)


def stage(category: str, start: float, end: float) -> Sample:
    return Sample("sleep", at(start), at(end), None, category, DAY)


def test_empty_day_is_all_none() -> None:
    assert set(summarize_day([]).values()) == {None}


def test_means_latest_and_sums() -> None:
    row = summarize_day(
        [
            num("hrv", 40),
            num("hrv", 60),
            num("resting_hr", 50),
            num("vo2max", 48.0, hour=7),
            num("vo2max", 49.5, hour=18),
            num("active_energy", 300),
            num("active_energy", 250),
        ]
    )
    assert row["hrv_sdnn_ms"] == 50
    assert row["resting_hr_bpm"] == 50
    assert row["vo2max"] == 49.5
    assert row["active_energy_kcal"] == 550
    assert row["respiratory_rate_bpm"] is None


def test_hrv_outlier_is_kept_in_the_raw_mean() -> None:
    # Ingestion doesn't judge data; outlier handling belongs to the recovery score (metrics/).
    assert summarize_day([num("hrv", 45), num("hrv", 47), num("hrv", 250)])["hrv_sdnn_ms"] == 114


def test_sleep_stages_in_minutes() -> None:
    row = summarize_day(
        [
            stage("in_bed", -1.5, 7),  # 22:30 -> 07:00
            stage("core", -1, 1),
            stage("deep", 1, 2),
            stage("rem", 2, 3),
            stage("awake", 3, 3.25),
            stage("core", 3.25, 6.5),
        ]
    )
    assert row["sleep_core_min"] == 315
    assert row["sleep_deep_min"] == 60
    assert row["sleep_rem_min"] == 60
    assert row["sleep_awake_min"] == 15
    assert row["sleep_in_bed_min"] == 510
    assert row["sleep_asleep_min"] == 435
    assert row["sleep_start"] == at(-1)
    assert row["sleep_end"] == at(6.5)


def test_watch_and_phone_recording_the_same_night_are_not_double_counted() -> None:
    watch = [stage("core", 0, 3), stage("deep", 3, 4)]
    phone = [stage("asleep", 0.5, 4)]  # iPhone only knows "asleep", overlapping the Watch
    row = summarize_day(watch + phone)
    assert row["sleep_asleep_min"] == 240
    assert row["sleep_core_min"] == 180
