"""Features for the learned marathon predictor, built the same way for training and for you.

Training data is the public BMClab dataset (Afonseca, Watanabe & Duarte 2022): daily running
totals (km, minutes) for ~36,000 runners in 2019–2020, all of whom have run a World Marathon
Major. It has no race results, so races are found in it:

    a race   = a day of 42.0–43.5 km, 2:00–7:00 h, that is either the date of a World Marathon
               Major or run at least 8% faster than that runner's training pace before it

Features come from the 8 weeks before a race (the race day itself excluded), from daily totals
only, since that's all the dataset has and all that's needed to apply it to you:

    weekly_km, pace_s_per_km      mean weekly volume and mean training pace (Tanda's inputs)
    long_run_km, runs_30k         longest day and number of 30 km+ days
    run_days_per_week             consistency
    recent_share                  share of the 8 weeks' km run in the last 4 (build vs. taper)
    best_pace_10k                 fastest pace on a 10 km+ day (s/km)
    male                          1 or 0

A window needs 8+ run days, 20+ km a week and one 10 km+ day to count; below that there's
nothing to learn from (and too few such races to learn what it would mean).
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

WINDOW_DAYS = 56
MIN_RUN_DAYS = 8
MIN_WEEKLY_KM = 20
RACE_KM = (42.0, 43.5)
RACE_MINUTES = (120, 420)
RACE_PACE_FACTOR = 0.92

# World Marathon Majors held in the dataset's years (2020's autumn races were cancelled).
MAJOR_DATES = {
    date(2019, 3, 3),  # Tokyo
    date(2019, 4, 15),  # Boston
    date(2019, 4, 28),  # London
    date(2019, 9, 29),  # Berlin
    date(2019, 10, 13),  # Chicago
    date(2019, 11, 3),  # New York
    date(2020, 3, 1),  # Tokyo (elite field only)
}

FEATURES = [
    "weekly_km",
    "pace_s_per_km",
    "long_run_km",
    "runs_30k",
    "run_days_per_week",
    "recent_share",
    "best_pace_10k",
    "male",
]


@dataclass(frozen=True)
class Day:
    day: date
    km: float
    minutes: float


def window_features(days: Sequence[Day], race_day: date, male: bool) -> dict | None:
    """Features from the 8 weeks before ``race_day``, or None if there's too little training."""
    start = race_day - timedelta(days=WINDOW_DAYS)
    window = [d for d in days if start <= d.day < race_day and d.km > 0 and d.minutes > 0]
    km = sum(d.km for d in window)
    weeks = WINDOW_DAYS / 7
    if len(window) < MIN_RUN_DAYS or km / weeks < MIN_WEEKLY_KM:
        return None
    long_days = [d for d in window if d.km >= 10]
    if not long_days:
        return None
    recent_start = race_day - timedelta(days=WINDOW_DAYS // 2)
    return {
        "weekly_km": km / weeks,
        "pace_s_per_km": sum(d.minutes for d in window) * 60 / km,
        "long_run_km": max(d.km for d in window),
        "runs_30k": sum(d.km >= 30 for d in window),
        "run_days_per_week": len(window) / weeks,
        "recent_share": sum(d.km for d in window if d.day >= recent_start) / km,
        "best_pace_10k": min(d.minutes * 60 / d.km for d in long_days),
        "male": 1.0 if male else 0.0,
        # Not a model feature: the best day's distance, for the Riegel baseline.
        "best_day_km": max(long_days, key=lambda d: d.km / d.minutes).km,
    }


def find_races(days: Sequence[Day], male: bool) -> list[tuple[Day, dict]]:
    """Marathons in one runner's history, each with the features of the 8 weeks before it."""
    out = []
    for d in days:
        if not (
            RACE_KM[0] <= d.km <= RACE_KM[1] and RACE_MINUTES[0] <= d.minutes <= RACE_MINUTES[1]
        ):
            continue
        feats = window_features(days, d.day, male)
        if feats is None:
            continue
        race_pace = d.minutes * 60 / d.km
        if d.day in MAJOR_DATES or race_pace <= RACE_PACE_FACTOR * feats["pace_s_per_km"]:
            out.append((d, feats))
    return out
