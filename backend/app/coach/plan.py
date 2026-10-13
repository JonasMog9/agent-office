"""Training plans: goal race + date → weeks of runs, and each day's workout adjusted to how you are.

Building a plan (pure, deterministic):

    phases      return (injury mode only) → base → build → peak → taper, counted back from race
                week. Taper: 3 weeks for a marathon, 2 for a half, 1 for 10K/5K. Peak: 2–3 weeks.
                Build takes ~40% of what's left, base the rest. No race = base weeks only.
    volume      starts at your current weekly km and grows ≤ 10% a week toward the distance's
                target peak, with every 4th base/build week a 20% cutback. Taper weeks run at
                75%, 55% and 40% of peak volume, ending at the race.
    return mode (coming back from injury) starts at 70% of current volume, at least 10 km a
                week, all easy running, growing ≤ 10% a week (so ACWR stays near 1.1, well
                under 1.3). Quality sessions only start once the volume is back to the
                pre-injury level, or after 4 weeks.
    sessions    one long run (~30% of the week, capped per distance) and, by phase:
                  base   strides after one easy run
                  build  threshold intervals
                  peak   threshold + intervals (marathon: marathon-pace long-run finish)
                  taper  short race-pace sharpener
    paces       from your VDOT (``coach.zones``), with the zone-2 HR ceiling for easy days.

Adjusting a day (``adjust``): pain → rest, red recovery → hard sessions become 30 minutes
easy (easy days become rest), yellow → hard sessions drop to easy with strides, ACWR above 1.3
→ no hard session and 25% less distance. Every change says why.
"""

from dataclasses import asdict, dataclass, field, replace
from datetime import date, timedelta

from app.coach.zones import format_pace, pace_zones

PEAK_KM = {"5K": 45, "10K": 55, "half marathon": 65, "marathon": 75}
LONG_RUN_CAP_KM = {"5K": 14, "10K": 18, "half marathon": 22, "marathon": 32}
TAPER_WEEKS = {"5K": 1, "10K": 1, "half marathon": 2, "marathon": 3}
TAPER_SHARES = [0.75, 0.55, 0.40]
MAX_WEEKLY_GROWTH = 1.10
CUTBACK_EVERY = 4
CUTBACK_SHARE = 0.8
RETURN_START_SHARE = 0.7
RETURN_MIN_KM = 10
RETURN_MAX_WEEKS = 4
MIN_RUN_KM = 4  # below this many km per run, the week gets fewer runs instead
SHORT_OF_PEAK = 0.6  # warn when the plan peaks below this share of the distance's usual volume
HARD = {"threshold", "intervals", "race pace", "marathon pace"}
# Weekday (Mon=0) of each run, by runs per week. The last one is the long run.
LAYOUT = {3: [1, 3, 6], 4: [1, 3, 5, 6], 5: [1, 2, 3, 5, 6], 6: [0, 1, 2, 3, 5, 6]}


@dataclass(frozen=True)
class Workout:
    day: date
    kind: str  # rest, easy, strides, long, threshold, intervals, marathon pace, race pace, race
    km: float
    description: str
    notes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Plan:
    weeks: list["Week"]
    notes: list[str]


@dataclass(frozen=True)
class Week:
    start: date
    phase: str
    km: float
    workouts: list[Workout]


def _phases(n_weeks: int, distance: str | None, return_weeks: int) -> list[str]:
    if not distance:
        return ["return"] * return_weeks + ["base"] * (n_weeks - return_weeks)
    taper = TAPER_WEEKS[distance]
    left = n_weeks - return_weeks - taper
    peak = min(3 if distance == "marathon" else 2, max(left - 2, 0))
    build = round((left - peak) * 0.4)
    base = left - peak - build
    return (
        ["return"] * return_weeks
        + ["base"] * base
        + ["build"] * build
        + ["peak"] * peak
        + ["taper"] * taper
    )


def weekly_volumes(phases: list[str], start_km: float, peak_km: float) -> list[float]:
    """Target km per week: ≤ 10% growth, 4th-week cutbacks, taper shares of peak volume."""
    out: list[float] = []
    km, since_cutback, taper_i = start_km, 0, 0
    reached = start_km
    for phase in phases:
        if phase == "taper":
            out.append(round(reached * TAPER_SHARES[min(taper_i, len(TAPER_SHARES) - 1)], 1))
            taper_i += 1
            continue
        since_cutback += 1
        if phase in ("base", "build") and since_cutback == CUTBACK_EVERY:
            out.append(round(km * CUTBACK_SHARE, 1))
            since_cutback = 0
            continue
        out.append(round(km, 1))
        reached = max(reached, km)
        km = min(km * MAX_WEEKLY_GROWTH, peak_km) if phase != "peak" else km
    return out


def _session(kind: str, km: float, paces: dict, distance: str | None) -> str:
    e, t, i = paces["easy"], paces["threshold"], paces["interval"]
    easy = f"{format_pace(e.fast_s_per_km)}–{format_pace(e.slow_s_per_km)}/km"
    if kind == "easy":
        return f"{km:.0f} km easy at {easy}"
    if kind == "strides":
        return f"{km:.0f} km easy at {easy}, then 6 × 20 s strides"
    if kind == "long":
        return f"{km:.0f} km long run at {easy}"
    if kind == "marathon pace":
        mp = format_pace(paces["marathon"].fast_s_per_km)
        return f"{km:.0f} km long run, last third at marathon pace {mp}/km"
    if kind == "threshold":
        return (
            f"{km:.0f} km incl. 4 × 6 min at threshold {format_pace(t.fast_s_per_km)}/km, 2 min jog"
        )
    if kind == "intervals":
        return f"{km:.0f} km incl. 5 × 3 min at {format_pace(i.fast_s_per_km)}/km, 3 min jog"
    if kind == "race pace":
        race = {"marathon": "marathon", "half marathon": "threshold"}.get(
            distance or "", "interval"
        )
        return (
            f"{km:.0f} km incl. 3 × 5 min at race pace {format_pace(paces[race].fast_s_per_km)}/km"
        )
    return kind


def _week_workouts(
    start: date,
    phase: str,
    km: float,
    runs: int,
    paces: dict,
    distance: str | None,
    race_day: date | None,
    quality_ok: bool,
) -> list[Workout]:
    runs = max(3, min(runs, int(km // MIN_RUN_KM)))  # fewer, not tiny, runs at low volume
    run_days = LAYOUT[runs]
    cap = LONG_RUN_CAP_KM.get(distance or "", 20)
    long_km = min(round(max(km * 0.3, km / len(run_days)), 1), cap)
    hard: list[str] = []
    if quality_ok:
        hard = {
            "base": ["strides"],
            "build": ["threshold"],
            "peak": ["threshold", "intervals"],
            "taper": ["race pace"],
        }.get(phase, [])
    long_kind = "marathon pace" if phase == "peak" and distance == "marathon" else "long"
    others = len(run_days) - 1
    other_km = round((km - long_km) / others, 1) if others else 0
    out = []
    for wd in range(7):
        day = start + timedelta(days=wd)
        if race_day and day == race_day:
            out.append(Workout(day, "race", 0, f"Race day: {distance}"))
            continue
        if race_day and day > race_day:
            out.append(Workout(day, "rest", 0, "Rest"))
            continue
        if wd not in run_days:
            out.append(Workout(day, "rest", 0, "Rest or cross-train"))
            continue
        if wd == run_days[-1] and not (race_day and race_day - day < timedelta(days=7)):
            out.append(
                Workout(day, long_kind, long_km, _session(long_kind, long_km, paces, distance))
            )
            continue
        kind = hard.pop(0) if hard else "easy"
        out.append(Workout(day, kind, other_km, _session(kind, other_km, paces, distance)))
    return out


def build_plan(
    start: date,
    current_weekly_km: float,
    vdot: float,
    *,
    race_distance: str | None = None,
    race_date: date | None = None,
    weeks: int = 12,
    runs_per_week: int = 4,
    returning_from_injury: bool = False,
    usual_weekly_km: float | None = None,
) -> Plan:
    """A week-by-week plan starting on the Monday of ``start``'s week, with warnings."""
    if runs_per_week not in LAYOUT:
        raise ValueError(f"runs_per_week must be one of {sorted(LAYOUT)}")
    monday = start - timedelta(days=start.weekday())
    if race_date:
        weeks = (race_date - monday).days // 7 + 1
        if weeks < 4:
            raise ValueError("A plan needs at least 4 weeks before the race.")
    peak = PEAK_KM.get(race_distance or "", max(current_weekly_km, 30))
    if returning_from_injury:
        start_km = max(current_weekly_km * RETURN_START_SHARE, RETURN_MIN_KM)
        target = usual_weekly_km or peak
        need = 0
        km = start_km
        while km < target * 0.999 and need < RETURN_MAX_WEEKS:
            km *= MAX_WEEKLY_GROWTH
            need += 1
        return_weeks = min(max(need, 1), weeks - 2)
    else:
        start_km, return_weeks = max(current_weekly_km, RETURN_MIN_KM), 0
    peak = max(peak, start_km)
    phases = _phases(weeks, race_distance, return_weeks)
    volumes = weekly_volumes(phases, start_km, peak)
    paces = {z.name: z for z in pace_zones(vdot)}
    notes = []
    if race_distance and max(volumes) < SHORT_OF_PEAK * PEAK_KM[race_distance]:
        notes.append(
            f"This plan only reaches {max(volumes):.0f} km a week, growing at most 10% a week from "
            f"{start_km:.0f}; a {race_distance} usually needs about {PEAK_KM[race_distance]}. "
            "Consider a later race or a shorter distance."
        )
    if returning_from_injury:
        notes.append(
            f"Return from injury: {return_weeks} weeks of easy running only, starting at "
            f"{start_km:.0f} km. Stop and rest if pain comes back."
        )
    out = []
    for i, (phase, km) in enumerate(zip(phases, volumes, strict=True)):
        week_start = monday + timedelta(weeks=i)
        out.append(
            Week(
                week_start,
                phase,
                km,
                _week_workouts(
                    week_start,
                    phase,
                    km,
                    runs_per_week,
                    paces,
                    race_distance,
                    race_date,
                    quality_ok=phase != "return",
                ),
            )
        )
    return Plan(out, notes)


def adjust(
    workout: Workout, recovery_label: str | None, acwr: float | None = None, pain: bool = False
) -> Workout:
    """Today's workout, changed if needed for pain, recovery and load. Reasons in ``notes``."""
    if workout.kind in ("rest", "race"):
        return workout
    if pain:
        return replace(
            workout,
            kind="rest",
            km=0,
            description="Rest",
            notes=["You reported pain: rest today, and run again only when it's gone."],
        )
    w = workout
    if recovery_label == "red":
        if w.kind in HARD or w.kind in ("long", "marathon pace"):
            return replace(
                w,
                kind="easy",
                km=min(w.km, 5),
                description="30 minutes very easy, or rest",
                notes=[f"Recovery is red: {w.kind} swapped for an easy 30 minutes."],
            )
        return replace(w, kind="rest", km=0, description="Rest", notes=["Recovery is red: rest."])
    if recovery_label == "yellow" and w.kind in HARD:
        w = replace(
            w,
            kind="strides",
            description=f"{w.km:.0f} km easy, then 6 × 20 s strides",
            notes=[f"Recovery is yellow: {w.kind} moved to easy running with strides."],
        )
    if acwr is not None and acwr > 1.3:
        km = round(w.km * 0.75, 1)
        kind = "easy" if w.kind in HARD | {"strides"} else w.kind
        w = replace(
            w,
            kind=kind,
            km=km,
            description=f"{km:.0f} km easy",
            notes=[*w.notes, f"Load is rising fast (ACWR {acwr:.2f}): 25% shorter, no hard work."],
        )
    return w


def plan_as_dict(plan: Plan) -> dict:
    """JSON-ready (dates as ISO strings), for storing and for the agents."""

    def iso(value):  # noqa: ANN001, ANN202
        if isinstance(value, date):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: iso(v) for k, v in value.items()}
        if isinstance(value, list):
            return [iso(v) for v in value]
        return value

    return iso(asdict(plan))
