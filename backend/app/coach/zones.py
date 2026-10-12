"""Personal training zones: heart rate (Karvonen) and pace (Daniels, from VDOT).

Heart-rate zones use heart-rate reserve, so they fit your resting HR as well as your max:

    zone bpm = HRrest + fraction × (HRmax − HRrest)
    Z1 50–60%  Z2 60–70%  Z3 70–80%  Z4 80–90%  Z5 90–100%

Pace zones are Daniels' training intensities for a VDOT:

    Easy        62–70% of VDOT              most of your running
    Marathon    predicted marathon pace
    Threshold   pace you could hold for an hour (≈ 88% of VDOT)
    Interval    predicted 5K pace (≈ vVO2max)
    Repetition  predicted mile pace

Paces are seconds per km and per mile.
"""

from dataclasses import dataclass

from app.coach.vdot import DISTANCES_M, race_time_s, vdot, velocity_at
from app.metrics.common import Component, ScoreResult

HR_ZONES = [(1, 0.5, 0.6), (2, 0.6, 0.7), (3, 0.7, 0.8), (4, 0.8, 0.9), (5, 0.9, 1.0)]
HR_ZONE_NAMES = {1: "recovery", 2: "aerobic / easy", 3: "tempo", 4: "threshold", 5: "max"}
EASY_FRACTIONS = (0.62, 0.70)
MILE_M = DISTANCES_M["mile"]


@dataclass(frozen=True)
class PaceZone:
    name: str
    fast_s_per_km: float  # the faster end (smaller number); same as slow for a single pace
    slow_s_per_km: float

    @property
    def fast_s_per_mile(self) -> float:
        return self.fast_s_per_km * MILE_M / 1000

    @property
    def slow_s_per_mile(self) -> float:
        return self.slow_s_per_km * MILE_M / 1000


def hr_zones(hr_rest: float, hr_max: float) -> ScoreResult:
    """Karvonen zones. Value = the top of zone 2, the ceiling for easy runs."""
    if not hr_rest or not hr_max or hr_max <= hr_rest:
        return ScoreResult(None, notes=["Needs a resting HR below the max HR."])
    reserve = hr_max - hr_rest
    comps = [
        Component(
            f"Z{z} {HR_ZONE_NAMES[z]}",
            round(hr_rest + lo * reserve),
            round(hr_rest + hi * reserve),
            note=f"{lo:.0%}–{hi:.0%} of heart-rate reserve",
        )
        for z, lo, hi in HR_ZONES
    ]
    notes = [
        f"Resting HR {hr_rest:.0f}, max HR {hr_max:.0f}. Each zone: value = low, baseline = high."
    ]
    return ScoreResult(comps[1].baseline, comps, notes)


def _pace_s_per_km(v_m_per_min: float) -> float:
    return 1000 / v_m_per_min * 60


def _race_pace(vdot_value: float, distance_m: float) -> float:
    return race_time_s(vdot_value, distance_m) / distance_m * 1000


def pace_zones(vdot_value: float) -> list[PaceZone]:
    easy_fast = _pace_s_per_km(velocity_at(EASY_FRACTIONS[1] * vdot_value))
    easy_slow = _pace_s_per_km(velocity_at(EASY_FRACTIONS[0] * vdot_value))
    # Threshold: the distance you'd race in 60 minutes, as a pace.
    lo, hi = 1000.0, 30000.0
    for _ in range(60):
        mid = (lo + hi) / 2
        lo, hi = (mid, hi) if vdot(mid, 3600) < vdot_value else (lo, mid)
    threshold = 3600 / ((lo + hi) / 2) * 1000
    single = {
        "marathon": _race_pace(vdot_value, DISTANCES_M["marathon"]),
        "threshold": threshold,
        "interval": _race_pace(vdot_value, DISTANCES_M["5K"]),
        "repetition": _race_pace(vdot_value, MILE_M),
    }
    return [PaceZone("easy", easy_fast, easy_slow)] + [
        PaceZone(name, p, p) for name, p in single.items()
    ]


def format_pace(seconds: float) -> str:
    s = round(seconds)
    return f"{s // 60}:{s % 60:02d}"
