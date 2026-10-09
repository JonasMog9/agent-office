"""Parse the iOS Shortcut's payload into normalized health samples (pure functions).

The Shortcut sends one JSON field per metric. Each field is text with one sample per line:

    start|end|value|unit

``start`` and ``end`` are ISO 8601 with the phone's UTC offset (Shortcuts "Format Date: ISO
8601"), ``value`` is a number (or a sleep stage name for ``sleep``) and ``unit`` is optional.
A list of such lines is accepted too. Building plain text keeps the Shortcut simple; see
docs/health-shortcut.md for how it's built.
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

# metric key -> (canonical unit, {accepted unit: converter to canonical})
_SAME: Callable[[float], float] = lambda v: v  # noqa: E731
UNITS: dict[str, dict[str, Callable[[float], float]]] = {
    "hrv": {"ms": _SAME, "s": lambda v: v * 1000},
    "resting_hr": {"count/min": _SAME, "bpm": _SAME},
    "respiratory_rate": {"count/min": _SAME, "bpm": _SAME, "breaths/min": _SAME},
    "wrist_temp": {
        "°c": _SAME,
        "degc": _SAME,
        "c": _SAME,
        "°f": lambda v: (v - 32) * 5 / 9,
        "degf": lambda v: (v - 32) * 5 / 9,
        "f": lambda v: (v - 32) * 5 / 9,
    },
    "active_energy": {"kcal": _SAME, "cal": _SAME, "kj": lambda v: v / 4.184},
    "vo2max": {
        "ml/(kg·min)": _SAME,
        "ml/kg/min": _SAME,
        "ml/(kg*min)": _SAME,
        "ml/min·kg": _SAME,  # Apple Health export.xml spelling
        "ml/(min·kg)": _SAME,
        "ml/kg·min": _SAME,
    },
    "ground_contact": {"ms": _SAME, "s": lambda v: v * 1000},
    "vertical_oscillation": {
        "cm": _SAME,
        "mm": lambda v: v / 10,
        "m": lambda v: v * 100,
        "in": lambda v: v * 2.54,
    },
    "stride_length": {
        "m": _SAME,
        "cm": lambda v: v / 100,
        "ft": lambda v: v * 0.3048,
        "in": lambda v: v * 0.0254,
    },
}

# Apple's sleep stage names, as Shortcuts prints them, mapped to our categories.
SLEEP_STAGES = {
    "in bed": "in_bed",
    "inbed": "in_bed",
    "awake": "awake",
    "core": "core",
    "asleep core": "core",
    "deep": "deep",
    "asleep deep": "deep",
    "rem": "rem",
    "asleep rem": "rem",
    "asleep": "asleep",
    "asleep unspecified": "asleep",
}

# Metrics that belong to a night, counted toward the morning you wake up. A night starts at
# 18:00: anything starting from then on counts toward the next day, so a night that begins at
# 23:40 stays whole instead of splitting at midnight.
NIGHT_METRICS = {"sleep", "wrist_temp"}
NIGHT_STARTS_HOUR = 18
METRICS = set(UNITS) | {"sleep"}


@dataclass(frozen=True)
class Sample:
    metric: str
    start: datetime
    end: datetime
    value: float | None
    category: str
    day: date


@dataclass
class ParseResult:
    samples: list[Sample] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)  # human-readable reasons, one per bad line
    unknown_fields: list[str] = field(default_factory=list)


def _to_number(text: str) -> float:
    text = text.strip().replace(" ", "").replace(" ", "")
    if "," in text and "." not in text:  # decimal comma locales: "52,3"
        text = text.replace(",", ".")
    return float(text)


def sample_day(metric: str, start: datetime, end: datetime) -> date:
    """The local day a sample counts toward (night metrics: the morning after 18:00)."""
    if metric in NIGHT_METRICS:
        return (start + timedelta(hours=24 - NIGHT_STARTS_HOUR)).date()
    return start.date()


def convert_unit(metric: str, value: float, unit: str) -> float:
    """``value`` in ``metric``'s canonical unit. Raises ValueError for an unknown unit."""
    key = unit.lower().replace(" ", "")
    convert = UNITS[metric].get(key) if key else _SAME
    if convert is None:
        raise ValueError(f"unit {unit!r} not supported for {metric}")
    return convert(value)


def parse_line(metric: str, line: str) -> Sample:
    """Parse one ``start|end|value|unit`` line. Raises ValueError with a readable reason."""
    parts = [p.strip() for p in line.split("|")]
    if len(parts) not in (3, 4):
        raise ValueError(f"expected start|end|value[|unit], got {len(parts)} fields")
    start, end = datetime.fromisoformat(parts[0]), datetime.fromisoformat(parts[1])
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("dates need a UTC offset (use Format Date: ISO 8601)")
    if end < start:
        raise ValueError("end is before start")
    day = sample_day(metric, start, end)

    if metric == "sleep":
        stage = SLEEP_STAGES.get(parts[2].lower())
        if stage is None:
            raise ValueError(f"unknown sleep stage {parts[2]!r}")
        return Sample(metric, start, end, None, stage, day)

    unit = parts[3] if len(parts) == 4 else ""
    return Sample(metric, start, end, convert_unit(metric, _to_number(parts[2]), unit), "", day)


def parse_payload(body: dict) -> ParseResult:
    result = ParseResult()
    for key, raw in body.items():
        metric = key.strip().lower()
        if metric not in METRICS:
            result.unknown_fields.append(key)
            continue
        lines = raw if isinstance(raw, list) else str(raw).splitlines()
        for line in lines:
            if not str(line).strip():
                continue
            try:
                result.samples.append(parse_line(metric, str(line)))
            except ValueError as err:
                result.skipped.append(f"{metric}: {err} ({str(line)[:80]!r})")
    return result
