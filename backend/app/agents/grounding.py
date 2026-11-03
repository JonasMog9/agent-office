"""Grounding: is every number in an agent's answer backed by what the model was given?

This is the check behind CLAUDE.md's "the AI never invents a number". The agent loop uses
it live (``loop.py``: an answer with an unbacked number goes back for one rewrite), and the
evals grade with it (``app/evals/grade.py``).

It pulls every number out of the answer and looks for it in what the model was given: the
tool results (field names included, like ``coins_under_48h``), the agent's instructions and
tool descriptions (like "Strain (0-21)"), and the question, allowing for the answer
rounding it. Small whole numbers (0–10, like "3 strategies" or "2×"), dates and race names
like "10K" are not checked: they're phrasing, not measurements.
"""

import json
import re
from dataclasses import dataclass

MONTHS = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
DATE_PATTERNS = [
    r"\b\d{4}-\d{2}-\d{2}(?:[ T][\d:.]+)?",  # 2026-11-03, with an optional time
    rf"\b(?:{MONTHS})[a-z]*\.? \d{{1,2}}\s*(?:-|–|to)\s*\d{{1,2}}\b",  # Oct 28 to 31
    rf"\b\d{{1,2}}\s*(?:-|–|to)\s*\d{{1,2}} (?:{MONTHS})[a-z]*\b",  # 28–31 Oct
    rf"\b(?:{MONTHS})[a-z]*\.? \d{{1,2}}(?:st|nd|rd|th)?\b",  # Nov 3, November 3rd
    rf"\b\d{{1,2}}(?:st|nd|rd|th)? (?:of )?(?:{MONTHS})[a-z]*\b",  # 3 Nov
    r"(?<![$\d.,])\b\d{1,2}K\b",  # race distances: 5K, 10K (money uses $ or a lower-case k)
    r"(?<![$\d.,])\b(?:19|20)\d{2}\b(?![.,]\d)",  # years: 2027
]
NUMBER = re.compile(r"(?<![\w.])[-−]?\$?(\d(?:[\d,]*\d)?(?:\.\d+)?)\s?([kKMB]\b|%)?")
CLOCK = re.compile(r"\b\d{1,2}:\d{2}(?::\d{2})?\b")  # paces and times: 4:57, 1:32:10
SCALE = {"k": 1e3, "K": 1e3, "M": 1e6, "B": 1e9}


@dataclass(frozen=True)
class Num:
    raw: str
    value: float
    decimals: int


def _strip_dates(text: str) -> str:
    for p in DATE_PATTERNS:
        text = re.sub(p, " ", text, flags=re.IGNORECASE)
    return text


def numbers(text: str) -> list[Num]:
    """The numbers in a piece of text, with $, k/M/B and % understood."""
    out = []
    for m in NUMBER.finditer(CLOCK.sub(" ", _strip_dates(text))):
        digits, suffix = m.group(1).replace(",", ""), m.group(2) or ""
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        value = float(digits) * SCALE.get(suffix, 1)
        out.append(Num(m.group(0).strip(), value, decimals))
    return out


def _key_text(key: str) -> str:
    """A field name as words, so its numbers count: "coins_under_48h" → "coins under 48 h"."""
    return re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", key.replace("_", " "))


def _flatten(obj: object) -> list[str]:
    """Every scalar in a JSON tool result, as text (numbers and strings alike)."""
    if isinstance(obj, dict):
        return [s for k, v in obj.items() for s in [_key_text(str(k)), *_flatten(v)]]
    if isinstance(obj, list):
        return [s for v in obj for s in _flatten(v)]
    return [str(obj)]


def evidence(
    tool_results: list[str], question: str = "", instructions: list[str] | None = None
) -> tuple[set[float], str]:
    """What an answer may quote: the numbers in the tool results, the agents' instructions
    and tool descriptions, and the question (plus hours and minutes of any minute counts),
    and the raw text for clock times like 4:57."""
    texts = [question, *(instructions or [])]
    for r in tool_results:
        try:
            texts += _flatten(json.loads(r))
        except (json.JSONDecodeError, TypeError):
            texts.append(str(r))
    blob = "\n".join(texts)
    values = {n.value for t in texts for n in numbers(t)}
    for v in list(values):
        if v == int(v) and 60 <= v < 1440:  # minutes → "7 h 48 min"
            values |= {v // 60, v % 60}
    return values, blob


def _matches(n: Num, values: set[float]) -> bool:
    tol = 0.5 * 10**-n.decimals
    for v in values:
        for cand in (v, v * 100):  # a fraction quoted as a percentage
            if abs(cand - n.value) <= tol + 1e-9 or abs(abs(cand) - n.value) <= tol + 1e-9:
                return True
        if n.value >= 1e3 and v and abs(v - n.value) / max(abs(v), 1) < 0.05:
            return True  # "$3.1M" quoting 3,140,000
    return False


def ungrounded(
    answer: str, tool_results: list[str], question: str = "", instructions: list[str] | None = None
) -> list[str]:
    """Numbers in the answer that nothing the model was given backs up."""
    values, blob = evidence(tool_results, question, instructions)
    bad = [c for c in CLOCK.findall(_strip_dates(answer)) if c not in blob]
    for n in numbers(answer):
        if n.decimals == 0 and n.value <= 10:
            continue
        if not _matches(n, values):
            bad.append(n.raw)
    return bad
