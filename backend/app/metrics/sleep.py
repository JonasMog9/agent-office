"""Sleep: tonight's need, recent debt, last night's performance, and timing consistency.

    debt          = a running balance over the last 30 nights, oldest first:
                    debt = max(0, debt × 0.85 + base need − time asleep)
                    short nights add to it, long nights pay it off, it never goes below
                    zero (extra sleep can't be banked), and old debt fades by 15% a night
    need tonight  = base need + strain extra + debt repayment
                    strain extra    = strain / 21 × 45 min   (a 21-strain day adds 45 minutes)
                    debt repayment  = min(debt / 4, 60 min)  (pay back a quarter, at most an hour)
    performance   = time asleep / that night's need, capped at 100%
    consistency   = 100 − standard deviation of bedtimes in minutes (floored at 0)

Nights without data add nothing to the debt (rather than counting as zero sleep) but old
debt still fades, and the result says how many nights it's based on. Whoop's exact formulas
aren't public; these are simple, explainable stand-ins.
"""

from collections.abc import Sequence
from datetime import datetime
from statistics import pstdev

from app.metrics.common import Component, ScoreResult

# A "night" this short is almost always a watch that died or came off, not real sleep, so it's
# scored as a night without data. Daily_metrics keeps the raw number.
MIN_NIGHT_MIN = 240
DEBT_NIGHTS = 7  # bedtimes used for consistency
DEBT_WINDOW = 30  # nights the balance runs over; 0.85^30 ≈ 0.008, so dropping one is invisible
DEBT_DECAY = 0.85
STRAIN_EXTRA_MAX_MIN = 45
DEBT_REPAY_SHARE = 0.25
DEBT_REPAY_CAP_MIN = 60


def sleep_debt(recent_asleep_min: Sequence[float | None], base_need_min: float) -> ScoreResult:
    """Sleep debt after the last of ``recent_asleep_min`` (one entry per night, oldest first)."""
    window = recent_asleep_min[-DEBT_WINDOW:]
    debt = 0.0
    comps = []
    for asleep in window:
        faded = debt * DEBT_DECAY
        if asleep is None:
            debt = faded
            continue
        debt = max(0.0, faded + base_need_min - asleep)
        comps.append(Component("night", asleep, base_need_min, contribution=round(debt - faded, 1)))
    nights = len(comps)
    notes = [f"Based on {nights} of the last {len(window)} nights."]
    if not nights:
        notes.append("No sleep recorded recently.")
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


def usable_night(asleep_min: float | None) -> bool:
    return asleep_min is not None and asleep_min > MIN_NIGHT_MIN
