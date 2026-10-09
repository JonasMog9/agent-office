"""Shared types and statistics for the scoring functions.

Every score is a pure function that returns a ``ScoreResult``: the number plus the components
that produced it. The agents explain scores from these components and never compute numbers
themselves (see CLAUDE.md, "Deterministic math, LLM for language").
"""

import math
from collections.abc import Sequence
from dataclasses import asdict, dataclass, field
from statistics import median


@dataclass(frozen=True)
class Component:
    name: str
    value: float | None  # today's input, in its natural unit
    baseline: float | None = None  # what it's compared against
    z: float | None = None  # standardized deviation, positive = better
    weight: float | None = None  # share of the final score, after reweighting
    contribution: float | None = None  # weight * z
    note: str = ""


@dataclass
class ScoreResult:
    value: float | None
    components: list[Component] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    label: str | None = None  # e.g. "green" / "yellow" / "red"

    def as_dict(self) -> dict:
        return asdict(self)


def robust_center_spread(values: Sequence[float], floor: float) -> tuple[float, float]:
    """Median and MAD scaled to a standard deviation (×1.4826), never below ``floor``.

    Median/MAD instead of mean/std keeps one bad night or a sensor glitch in the baseline
    from moving it, and the floor stops a perfectly flat history (e.g. resting HR of 52 every
    day) from turning a 1 bpm change into an extreme z-score.
    """
    center = median(values)
    mad = median(abs(v - center) for v in values) * 1.4826
    return center, max(mad, floor)


def clip(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def normal_cdf(z: float) -> float:
    return 0.5 * (1 + math.erf(z / math.sqrt(2)))
