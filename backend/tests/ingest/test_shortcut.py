from datetime import date

import pytest

from app.ingest.shortcut import parse_line, parse_payload


def test_numeric_line_with_unit() -> None:
    s = parse_line("hrv", "2026-10-07T03:12:00-07:00|2026-10-07T03:13:00-07:00|52.3|ms")
    assert (s.metric, s.value, s.category, s.day) == ("hrv", 52.3, "", date(2026, 10, 7))


def test_unit_is_optional() -> None:
    assert parse_line("resting_hr", "2026-10-07T00:00:00Z|2026-10-07T23:59:00Z|51").value == 51


@pytest.mark.parametrize(
    ("metric", "value", "unit", "expected"),
    [
        ("wrist_temp", "95.0", "°F", 35.0),
        ("wrist_temp", "35.0", "°C", 35.0),
        ("stride_length", "4", "ft", 1.2192),
        ("vertical_oscillation", "3.5", "in", 8.89),
        ("active_energy", "4184", "kJ", 1000.0),
        ("active_energy", "650", "Cal", 650.0),
        ("ground_contact", "0.25", "s", 250.0),
    ],
)
def test_units_are_converted(metric: str, value: str, unit: str, expected: float) -> None:
    line = f"2026-10-07T07:00:00-07:00|2026-10-07T08:00:00-07:00|{value}|{unit}"
    assert parse_line(metric, line).value == pytest.approx(expected)


def test_decimal_comma_is_accepted() -> None:
    assert (
        parse_line("hrv", "2026-10-07T03:00:00+02:00|2026-10-07T03:01:00+02:00|52,3").value == 52.3
    )


def test_day_is_local_to_the_phone_not_utc() -> None:
    # 23:30 in Los Angeles is already the next day in UTC; it still counts for the 7th.
    s = parse_line("hrv", "2026-10-07T23:30:00-07:00|2026-10-07T23:31:00-07:00|40")
    assert s.day == date(2026, 10, 7)


def test_sleep_counts_toward_the_morning_it_ends() -> None:
    s = parse_line("sleep", "2026-10-06T23:10:00-07:00|2026-10-07T01:00:00-07:00|Core")
    assert (s.category, s.value, s.day) == ("core", None, date(2026, 10, 7))


@pytest.mark.parametrize(
    ("metric", "line", "reason"),
    [
        ("hrv", "2026-10-07T03:00:00|2026-10-07T03:01:00|50", "UTC offset"),
        ("hrv", "2026-10-07T03:00:00Z|2026-10-07T02:00:00Z|50", "before start"),
        ("hrv", "2026-10-07T03:00:00Z|2026-10-07T03:01:00Z", "fields"),
        ("hrv", "2026-10-07T03:00:00Z|2026-10-07T03:01:00Z|50|bananas", "not supported"),
        ("sleep", "2026-10-07T03:00:00Z|2026-10-07T04:00:00Z|Dreaming", "unknown sleep stage"),
    ],
)
def test_bad_lines_raise_a_readable_reason(metric: str, line: str, reason: str) -> None:
    with pytest.raises(ValueError, match=reason):
        parse_line(metric, line)


def test_payload_skips_bad_lines_and_reports_unknown_fields() -> None:
    result = parse_payload(
        {
            "hrv": "2026-10-07T03:00:00Z|2026-10-07T03:01:00Z|50\n\nnot a line\n",
            "Resting_HR": ["2026-10-07T00:00:00Z|2026-10-07T23:59:00Z|52"],
            "steps": "whatever",
        }
    )
    assert [s.metric for s in result.samples] == ["hrv", "resting_hr"]
    assert len(result.skipped) == 1 and result.skipped[0].startswith("hrv:")
    assert result.unknown_fields == ["steps"]
