"""Training load: fitness (CTL), fatigue (ATL), form, and the acute:chronic workload ratio.

Daily load is the day's TRIMP (see ``metrics.strain``). Days without a workout count as 0.

    CTL_t = CTL_{t−1} + (TRIMP_t − CTL_{t−1}) / 42      fitness: ~6-week weighted average
    ATL_t = ATL_{t−1} + (TRIMP_t − ATL_{t−1}) / 7       fatigue: ~1-week weighted average
    form  = CTL − ATL                                   (a.k.a. TSB) using yesterday's values,
                                                        so it says how fresh you are this morning
    ACWR  = mean TRIMP of the last 7 days / mean TRIMP of the last 28 days

Flags (rules of thumb from the training-load literature; TRIMP is on a similar scale to
TrainingPeaks' TSS, so its form bands are used):

    ACWR > 1.5               injury risk high: this week is far above what you're used to
    ACWR 1.3–1.5             load rising fast
    ACWR < 0.8               load well below usual (fine for a taper or rest week)
    form < −30               deep fatigue: overreaching if it lasts
    form −30 to −10          productive training block
    form > +25               very fresh: fitness will start to fade without training
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.metrics.common import Component, ScoreResult

CTL_DAYS = 42
ATL_DAYS = 7
ACUTE_DAYS = 7
CHRONIC_DAYS = 28


@dataclass(frozen=True)
class LoadDay:
    trimp: float
    ctl: float
    atl: float
    form: float  # yesterday's CTL − ATL: freshness going into the day
    acwr: float | None


def load_series(daily_trimp: Sequence[float | None]) -> list[LoadDay]:
    """Load for each day of a gap-free daily series, oldest first (None = no workout = 0)."""
    out: list[LoadDay] = []
    ctl = atl = 0.0
    loads = [t or 0.0 for t in daily_trimp]
    for i, trimp in enumerate(loads):
        form = ctl - atl
        ctl += (trimp - ctl) / CTL_DAYS
        atl += (trimp - atl) / ATL_DAYS
        acwr = None
        if i + 1 >= CHRONIC_DAYS:
            chronic = sum(loads[i + 1 - CHRONIC_DAYS : i + 1]) / CHRONIC_DAYS
            acute = sum(loads[i + 1 - ACUTE_DAYS : i + 1]) / ACUTE_DAYS
            acwr = acute / chronic if chronic > 0 else None
        out.append(LoadDay(trimp, ctl, atl, form, acwr))
    return out


def flags(day: LoadDay) -> list[str]:
    out = []
    if day.acwr is not None:
        if day.acwr > 1.5:
            out.append("Injury risk high: this week's load is over 1.5× your 4-week average.")
        elif day.acwr >= 1.3:
            out.append("Load rising fast: this week is 1.3–1.5× your 4-week average.")
        elif day.acwr < 0.8:
            out.append("Load well below your 4-week average (fine for a taper or rest week).")
    if day.form < -30:
        out.append("Deep fatigue (form below −30): overreaching if it lasts more than a week.")
    elif day.form <= -10:
        out.append("Productive training block (form −10 to −30).")
    elif day.form > 25:
        out.append("Very fresh (form above +25): fitness starts to fade without training.")
    return out


def training_load(daily_trimp: Sequence[float | None]) -> ScoreResult:
    """Load on the last day of ``daily_trimp`` with its breakdown and flags. Value = form."""
    if not daily_trimp:
        return ScoreResult(None, notes=["No training history."])
    series = load_series(daily_trimp)
    day = series[-1]
    loads = [t or 0.0 for t in daily_trimp]
    acute = sum(loads[-ACUTE_DAYS:]) / min(len(loads), ACUTE_DAYS)
    chronic = sum(loads[-CHRONIC_DAYS:]) / min(len(loads), CHRONIC_DAYS)
    comps = [
        Component("fitness (CTL)", round(day.ctl, 1), note="42-day weighted average TRIMP"),
        Component("fatigue (ATL)", round(day.atl, 1), note="7-day weighted average TRIMP"),
        Component("form", round(day.form, 1), note="fitness − fatigue, as of this morning"),
        Component(
            "ACWR",
            None if day.acwr is None else round(day.acwr, 2),
            note=f"7-day mean {acute:.0f} / 28-day mean {chronic:.0f}",
        ),
        Component("TRIMP today", round(day.trimp, 1)),
    ]
    notes = flags(day)
    if len(daily_trimp) < CTL_DAYS:
        notes.append(
            f"Only {len(daily_trimp)} days of history; fitness needs ~{CTL_DAYS} to settle."
        )
    return ScoreResult(round(day.form, 1), comps, notes)
