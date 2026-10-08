"""Roll stored health samples up into one ``daily_metrics`` row per day (pure functions).

Rules per metric:

- mean of the day's samples: HRV, resting HR, respiratory rate, wrist temperature, running form
- latest sample of the day: VO2max
- sum: active energy (the Shortcut sends it grouped by day, so this is normally one value)
- sleep: minutes per stage over the night ending that morning. Stages are merged as a union of
  time intervals, because iPhone and Watch can both record the same night and summing them
  would double count.
"""

from collections import defaultdict
from collections.abc import Iterable
from datetime import datetime
from statistics import fmean
from typing import Any

from app.ingest.shortcut import Sample

MEAN_COLUMNS = {
    "hrv": "hrv_sdnn_ms",
    "resting_hr": "resting_hr_bpm",
    "respiratory_rate": "respiratory_rate_bpm",
    "wrist_temp": "wrist_temp_c",
    "ground_contact": "ground_contact_ms",
    "vertical_oscillation": "vertical_oscillation_cm",
    "stride_length": "stride_length_m",
}
SLEEP_COLUMNS = {
    "core": "sleep_core_min",
    "deep": "sleep_deep_min",
    "rem": "sleep_rem_min",
    "awake": "sleep_awake_min",
    "in_bed": "sleep_in_bed_min",
}
ASLEEP_STAGES = {"core", "deep", "rem", "asleep"}
ALL_COLUMNS = [
    *MEAN_COLUMNS.values(),
    "active_energy_kcal",
    "vo2max",
    "sleep_asleep_min",
    *SLEEP_COLUMNS.values(),
    "sleep_start",
    "sleep_end",
]


def merge_intervals(
    intervals: Iterable[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def minutes(intervals: Iterable[tuple[datetime, datetime]]) -> float:
    return round(sum((e - s).total_seconds() for s, e in merge_intervals(intervals)) / 60, 1)


def summarize_day(samples: Iterable[Sample]) -> dict[str, Any]:
    """Return every daily_metrics column for one day; columns with no data are None."""
    values: dict[str, list[Sample]] = defaultdict(list)
    for s in samples:
        values[s.metric].append(s)

    row: dict[str, Any] = dict.fromkeys(ALL_COLUMNS)
    for metric, column in MEAN_COLUMNS.items():
        nums = [s.value for s in values[metric] if s.value is not None]
        if nums:
            row[column] = round(fmean(nums), 2)
    if energy := [s.value for s in values["active_energy"] if s.value is not None]:
        row["active_energy_kcal"] = round(sum(energy), 1)
    if vo2 := [s for s in values["vo2max"] if s.value is not None]:
        row["vo2max"] = max(vo2, key=lambda s: s.start).value

    sleep = values["sleep"]
    for stage, column in SLEEP_COLUMNS.items():
        stage_intervals = [(s.start, s.end) for s in sleep if s.category == stage]
        if stage_intervals:
            row[column] = minutes(stage_intervals)
    asleep = [(s.start, s.end) for s in sleep if s.category in ASLEEP_STAGES]
    if asleep:
        row["sleep_asleep_min"] = minutes(asleep)
        row["sleep_start"] = min(s for s, _ in asleep)
        row["sleep_end"] = max(e for _, e in asleep)
    return row
