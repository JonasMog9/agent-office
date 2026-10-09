"""Sleep: tonight's need, recent debt, last night's performance, and timing consistency.

    debt          = Σ over the last 7 nights of max(0, base need − time asleep)
    need tonight  = base need + strain extra + debt repayment
                    strain extra    = strain / 21 × 45 min   (a 21-strain day adds 45 minutes)
                    debt repayment  = min(debt / 4, 60 min)  (pay back a quarter, at most an hour)
    performance   = time asleep / that night's need, capped at 100%
    consistency   = 100 − standard deviation of bedtimes in minutes (floored at 0)

Nights without data are left out of the debt rather than counted as zero sleep, and the
result says how many nights it's based on. Whoop's exact formulas aren't public; these are
simple, explainable stand-ins.
"""

from collections.abc import Sequence
from datetime import datetime
from statistics import pstdev

from app.metrics.common import Component, ScoreResult

DEBT_NIGHTS = 7
STRAIN_EXTRA_MAX_MIN = 45
DEBT_REPAY_SHARE = 0.25
DEBT_REPAY_CAP_MIN = 60


def sleep_debt(recent_asleep_min: Sequence[float | None], base_need_min: float) -> ScoreResult:
    nights = [a for a in recent_asleep_min[-DEBT_NIGHTS:] if a is not None]
    debt = sum(max(0.0, base_need_min - a) for a in nights)
    notes = [f"Based on {len(nights)} of the last {DEBT_NIGHTS} nights."]
    if not nights:
        notes.append("No sleep recorded recently.")
    comps = [
        Component("night", a, base_need_min, contribution=round(max(0.0, base_need_min - a), 1))
        for a in nights
    ]
    return ScoreResult(round(debt, 1), comps, notes)


def sleep_need(base_need_min: float, strain_today: float | None, debt_min: float) -> ScoreResult:
    strain_extra = (strain_today or 0) / 21 * STRAIN_EXTRA_MAX_MIN
    repay = min(debt_min * DEBT_REPAY_SHARE, DEBT_REPAY_CAP_MIN)
    comps = [
        Component("baseline need", base_need_min, contribution=base_need_min),
        Component("extra for today's strain", strain_today, contribution=round(strain_extra, 1)),
        Component("sleep debt repayment", debt_min, contribution=round(repay, 1)),
    ]
    return ScoreResult(round(base_need_min + strain_extra + repay), comps)


def sleep_performance(asleep_min: float | None, need_min: float) -> ScoreResult:
    if asleep_min is None:
        return ScoreResult(None, notes=["No sleep recorded."])
    pct = min(asleep_min / need_min, 1.0) * 100
    return ScoreResult(round(pct), [Component("asleep", asleep_min, need_min)])


def _bedtime_minutes(start: datetime) -> float:
    """Minutes after 18:00, so 23:30 and 00:30 are 60 minutes apart, not 23 hours."""
    minutes = start.hour * 60 + start.minute
    return (minutes - 18 * 60) % (24 * 60)


def sleep_consistency(bedtimes: Sequence[datetime | None]) -> ScoreResult:
    starts = [b for b in bedtimes[-DEBT_NIGHTS:] if b is not None]
    if len(starts) < 3:
        return ScoreResult(None, notes=[f"Needs at least 3 nights, has {len(starts)}."])
    spread = pstdev(_bedtime_minutes(s) for s in starts)
    return ScoreResult(
        round(max(0.0, 100 - spread)),
        [Component("bedtime spread (min)", round(spread, 1))],
        [f"Based on {len(starts)} nights."],
    )
