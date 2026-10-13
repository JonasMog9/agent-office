import random
from datetime import date, timedelta

import pytest

from app.coach.fitness import Segment, fitness, segments
from app.coach.vdot import velocity_at

TODAY = date(2026, 10, 13)
REST, MAX = 52, 191


def stream(minutes: int, hr: float, speed: float, start_s: int = 0) -> dict:
    t = list(range(start_s, start_s + minutes * 60))
    return {"time": t, "heartrate": [hr] * len(t), "velocity_smooth": [speed] * len(t)}


def test_segments_skip_warmup_walking_and_surges() -> None:
    s = stream(20, 140, 2.8)
    # 2-minute windows from 0:00; the first past the 5-minute warm-up starts at 6:00, the last
    # full one at 16:00 (one ending exactly at the last sample is dropped)
    assert len(segments(1, TODAY, s)) == 6
    walking = stream(20, 110, 1.4)
    assert segments(1, TODAY, walking) == []
    surges = stream(20, 160, 3.0)
    surges["velocity_smooth"] = [2.5 if (i // 30) % 2 else 4.0 for i in range(len(surges["time"]))]
    assert segments(1, TODAY, surges) == []
    assert segments(1, TODAY, {"time": [0, 1]}) == []  # no heart rate


def runner(vdot: float, n_runs: int = 12, seed: int = 1) -> list[Segment]:
    """Segments of a runner who follows Swain: VO2 − 3.5 = HRR fraction × (VO2max − 3.5)."""
    rng = random.Random(seed)
    out = []
    for r in range(n_runs):
        for _ in range(15):
            hrr = rng.uniform(0.55, 0.8)
            speed = velocity_at(3.5 + hrr * (vdot - 3.5)) / 60 * rng.uniform(0.97, 1.03)
            hr = REST + hrr * (MAX - REST) + rng.gauss(0, 2)
            out.append(Segment(r, TODAY - timedelta(days=3 * r), hr, speed, 0.0))
    return out


def test_recovers_the_runners_vdot_and_beats_the_baseline() -> None:
    r = fitness(runner(42), REST, MAX, TODAY)
    assert r.value == pytest.approx(42, abs=1.5)
    cv = next(c for c in r.components if c.name == "cross-validated error")
    assert cv.value < cv.baseline


def test_easy_runs_at_six_minutes_per_km_mean_about_vdot_42() -> None:
    # The owner's case: easy runs around 6:00/km at ~63% HRR (HR ≈ 140) → VDOT ≈ 42–43.
    segs = [
        Segment(r, TODAY - timedelta(days=r), 140 + d, 1000 / (360 - 4 * d), 0.0)
        for r in range(6)
        for d in (-6, -3, 0, 3, 6)
    ]
    r = fitness(segs, REST, MAX, TODAY)
    assert r.value == pytest.approx(43, abs=1.5)
    pace150 = r.components[0].value
    assert 320 < pace150 < 345  # faster than easy pace at a higher heart rate


def test_fitter_runner_is_faster_at_hr_150() -> None:
    slow = fitness(runner(40), REST, MAX, TODAY).components[0].value
    fast = fitness(runner(50), REST, MAX, TODAY).components[0].value
    assert fast < slow


def test_says_so_when_it_cannot_beat_the_baseline() -> None:
    rng = random.Random(3)
    noise = [
        Segment(r, TODAY - timedelta(days=r), rng.uniform(130, 170), rng.uniform(2.5, 3.5), 0.0)
        for r in range(6)
        for _ in range(10)
    ]
    r = fitness(noise, REST, MAX, TODAY)
    assert r.value is None and any("doesn't beat" in n for n in r.notes)


def test_needs_enough_recent_runs() -> None:
    old = [Segment(1, TODAY - timedelta(days=90), 140, 2.8, 0.0)] * 30
    assert "Needs 3+ runs" in fitness(old, REST, MAX, TODAY).notes[0]
    assert fitness(runner(42), None, MAX, TODAY).value is None
