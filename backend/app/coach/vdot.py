"""Jack Daniels' VDOT: one fitness number from a race result, and race times back from it.

Daniels and Gilbert (1979) fit two curves to lab data:

    VO2(v)   = −4.60 + 0.182258 v + 0.000104 v²                 oxygen cost at v metres/min
    %max(t)  = 0.8 + 0.1894393 e^(−0.012778 t) + 0.2989558 e^(−0.1932605 t)
                                                    share of VO2max sustainable for t minutes
    VDOT     = VO2(d / t) / %max(t)

Predicting a race inverts it: the time t at which a distance d gives the same VDOT. The
equations reproduce Daniels' published tables to within about 0.1 VDOT (see the tests).
"""

import math

DISTANCES_M = {
    "mile": 1609.344,
    "5K": 5000.0,
    "10K": 10000.0,
    "half marathon": 21097.5,
    "marathon": 42195.0,
}


def vo2_cost(v_m_per_min: float) -> float:
    return -4.60 + 0.182258 * v_m_per_min + 0.000104 * v_m_per_min**2


def fraction_sustainable(t_min: float) -> float:
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot(distance_m: float, time_s: float) -> float:
    """VDOT from a race (or all-out time trial) over ``distance_m`` in ``time_s``."""
    if distance_m <= 0 or time_s <= 0:
        raise ValueError("distance and time must be positive")
    t = time_s / 60
    return vo2_cost(distance_m / t) / fraction_sustainable(t)


def race_time_s(vdot_value: float, distance_m: float) -> float:
    """Time in seconds a runner with ``vdot_value`` would race ``distance_m`` in (bisection)."""
    lo, hi = 60.0, 24 * 3600.0  # VDOT falls as time grows, so the root is bracketed
    for _ in range(100):
        mid = (lo + hi) / 2
        if vdot(distance_m, mid) > vdot_value:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def velocity_at(vo2: float) -> float:
    """Speed in metres/min whose oxygen cost is ``vo2`` (the positive root of VO2(v))."""
    a, b, c = 0.000104, 0.182258, -4.60 - vo2
    return (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)
