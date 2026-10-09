"""Read Apple Health's "Export All Health Data" file into health samples (streaming, pure).

The export is a zip holding ``apple_health_export/export.xml``: one ``<Record>`` per sample,

    <Record type="HKQuantityTypeIdentifierHeartRateVariabilitySDNN" sourceName="…Watch"
            unit="ms" startDate="2026-10-05 01:34:22 -0400" endDate="…" value="40.67"/>

Multi-year exports run to gigabytes, so the XML is parsed incrementally and each element is
discarded once read. Samples go through the same unit conversion and day rules as the
Shortcut (``ingest.shortcut``) and land in the same table, so the two never double count:
an identical sample from both sources has the same (metric, start, end) key.

Active energy is the exception. The export holds every small raw sample from both iPhone and
Watch, and summing them would count calories twice. They're totalled per day per device
and the larger device total kept, which matches the deduplicated daily total the Shortcut gets
from Health with "Group by: Day".
"""

import xml.etree.ElementTree as ET
import zipfile
from collections import defaultdict
from collections.abc import Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from typing import IO

from app.ingest.shortcut import Sample, convert_unit, sample_day

QUANTITY_TYPES = {
    "HKQuantityTypeIdentifierHeartRateVariabilitySDNN": "hrv",
    "HKQuantityTypeIdentifierRestingHeartRate": "resting_hr",
    "HKQuantityTypeIdentifierRespiratoryRate": "respiratory_rate",
    "HKQuantityTypeIdentifierAppleSleepingWristTemperature": "wrist_temp",
    "HKQuantityTypeIdentifierVO2Max": "vo2max",
    "HKQuantityTypeIdentifierRunningGroundContactTime": "ground_contact",
    "HKQuantityTypeIdentifierRunningVerticalOscillation": "vertical_oscillation",
    "HKQuantityTypeIdentifierRunningStrideLength": "stride_length",
}
ACTIVE_ENERGY = "HKQuantityTypeIdentifierActiveEnergyBurned"
SLEEP = "HKCategoryTypeIdentifierSleepAnalysis"
SLEEP_VALUES = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAwake": "awake",
    "HKCategoryValueSleepAnalysisAsleepCore": "core",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
    "HKCategoryValueSleepAnalysisAsleep": "asleep",  # pre-iOS 16 exports
}


@dataclass
class ExportStats:
    records_seen: int = 0
    samples: int = 0
    skipped: int = 0
    by_metric: dict[str, int] = field(default_factory=lambda: defaultdict(int))


def parse_date(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z")


def open_export_xml(path: str) -> IO[bytes]:
    """export.xml as a stream, from the zip Apple produces or from a bare export.xml."""
    if not zipfile.is_zipfile(path):
        return open(path, "rb")  # noqa: SIM115  (caller closes it)
    archive = zipfile.ZipFile(path)
    names = [n for n in archive.namelist() if n.rsplit("/", 1)[-1] == "export.xml"]
    if not names:
        raise ValueError("no export.xml in the zip: is this Apple Health's export?")
    return archive.open(names[0])


def iter_samples(
    stream: IO[bytes], since: date, stats: ExportStats | None = None
) -> Iterator[Sample]:
    """Yield samples from ``stream`` whose day is on or after ``since``."""
    stats = stats or ExportStats()
    # (day, source) -> [kcal, tzinfo of that day's records]
    energy: dict[tuple[date, str], list] = {}
    seen_energy: set[int] = set()  # hashes of (source, start, end): repeated records count once

    depth = 0
    root: ET.Element | None = None
    for event, elem in ET.iterparse(stream, events=("start", "end")):
        if event == "start":
            depth += 1
            root = root if root is not None else elem
            continue
        depth -= 1
        if depth != 1:  # only top-level children of <HealthData> (Record, Workout, ...)
            continue
        if elem.tag == "Record":
            stats.records_seen += 1
            try:
                sample = _record(elem.get("type", ""), elem, since, energy, seen_energy)
            except (ValueError, TypeError):
                stats.skipped += 1
                sample = None
            if sample is not None:
                stats.samples += 1
                stats.by_metric[sample.metric] += 1
                yield sample
        root.clear()  # drop everything parsed so far: memory stays flat on huge exports

    best: dict[date, tuple[float, object]] = {}
    for (day, _source), (kcal, tz) in energy.items():
        if day not in best or kcal > best[day][0]:
            best[day] = (kcal, tz)
    for day, (kcal, tz) in sorted(best.items()):
        start = datetime.combine(day, time(), tzinfo=tz)
        stats.samples += 1
        stats.by_metric["active_energy"] += 1
        yield Sample("active_energy", start, start + timedelta(days=1), round(kcal, 1), "", day)


def _record(
    kind: str, elem: ET.Element, since: date, energy: dict, seen_energy: set[int]
) -> Sample | None:
    if kind not in QUANTITY_TYPES and kind not in (ACTIVE_ENERGY, SLEEP):
        return None
    start, end = parse_date(elem.get("startDate", "")), parse_date(elem.get("endDate", ""))
    if end < start:
        raise ValueError("end before start")

    if kind == SLEEP:
        stage = SLEEP_VALUES.get(elem.get("value", ""))
        day = sample_day("sleep", start, end)
        if stage is None or day < since:
            return None
        return Sample("sleep", start, end, None, stage, day)

    value = float(elem.get("value", ""))
    if kind == ACTIVE_ENERGY:
        day = start.date()
        key = hash((elem.get("sourceName", ""), elem.get("startDate"), elem.get("endDate")))
        if day >= since and key not in seen_energy:
            seen_energy.add(key)
            kcal = convert_unit("active_energy", value, elem.get("unit", ""))
            slot = energy.setdefault((day, elem.get("sourceName", "")), [0.0, start.tzinfo])
            slot[0] += kcal
        return None

    metric = QUANTITY_TYPES[kind]
    day = sample_day(metric, start, end)
    if day < since:
        return None
    return Sample(metric, start, end, convert_unit(metric, value, elem.get("unit", "")), "", day)
