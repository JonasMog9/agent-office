from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from app.scout.paper import (
    MOON,
    QUICK,
    RUNNER,
    STRATEGIES,
    Position,
    Strategy,
    Trade,
    pnl,
    replay,
    step,
    summary,
)

T0 = datetime(2026, 10, 19, 12, tzinfo=UTC)
TOKENS = 10 * 0.98  # $10 at an entry price of 1.0, after the 2% buy cost


def run(s: Strategy, prices, liquidity=200_000, every=timedelta(minutes=10)) -> Position:
    """Feed a price path to a fresh position, one check every ``every``."""
    p = Position(entry=1.0, opened_at=T0, last=1.0, peak=1.0)
    for i, price in enumerate(prices, 1):
        p = step(s, p, price, liquidity, T0 + i * every)
    return p


def test_three_strategies_with_their_own_keys():
    assert [s.key for s in STRATEGIES] == ["quick", "runner", "moon"]
    assert all(s.blurb and s.stake_usd == 10 for s in STRATEGIES)


# --- Quick 2× (the original rules) ---


def test_quick_holds_while_no_rule_fires():
    p = run(QUICK, [1.3, 0.6, 1.9])
    assert p.closed is None and p.held == 1.0 and p.peak == 1.9 and p.last == 1.9


def test_quick_sells_everything_at_2x_even_when_it_gaps_past():
    p = run(QUICK, [1.5, 3.7])
    assert (p.closed, p.exit_price, p.held, p.rungs) == ("take_profit", 3.7, 0.0, 1)
    assert pnl(QUICK, p) == pytest.approx(TOKENS * 3.7 * 0.98 - 10)
    assert p.closed_at == T0 + timedelta(minutes=20)


def test_quick_stop_loss_and_time_limit():
    assert run(QUICK, [0.8, 0.5]).closed == "stop_loss"
    p = run(QUICK, [1.2] * 3, every=timedelta(hours=24))
    assert (p.closed, p.exit_price) == ("time", 1.2)
    assert run(QUICK, [1.2] * 2, every=timedelta(hours=24)).closed is None


def test_round_trip_at_the_same_price_pays_costs_both_ways():
    p = run(QUICK, [1.0] * 3, every=timedelta(hours=24))
    assert pnl(QUICK, p) == pytest.approx(10 * 0.98 * 0.98 - 10)  # -0.40


# --- Runner: trailing stop once it has doubled ---


def test_runner_rides_past_2x_and_sells_30_percent_below_the_peak():
    p = run(RUNNER, [1.5, 2.2, 4.0, 5.0, 4.0])
    assert p.closed is None  # 4.0 is only 20% off the 5.0 peak
    p = run(RUNNER, [1.5, 2.2, 4.0, 5.0, 4.0, 3.4])
    assert (p.closed, p.exit_price, p.peak) == ("trailing_stop", 3.4, 5.0)
    assert pnl(RUNNER, p) == pytest.approx(TOKENS * 3.4 * 0.98 - 10)


def test_runner_trail_is_not_armed_before_2x():
    # 1.9 → 1.3 is a 32% fall, but it never doubled, so only the −50% stop applies
    assert run(RUNNER, [1.9, 1.3]).closed is None
    assert run(RUNNER, [1.9, 1.3, 0.45]).closed == "stop_loss"


def test_runner_sells_after_seven_days():
    assert run(RUNNER, [1.4] * 6, every=timedelta(days=1)).closed is None
    assert run(RUNNER, [1.4] * 7, every=timedelta(days=1)).closed == "time"


# --- Moon bag: ladder, then a wide trailing stop on the rest ---


def test_moon_sells_half_at_2x_and_a_quarter_at_5x():
    p = run(MOON, [2.1])
    assert (p.closed, p.held, p.rungs) == (None, 0.5, 1)
    assert p.proceeds == pytest.approx(TOKENS * 0.5 * 2.1 * 0.98)
    p = run(MOON, [2.1, 5.5])
    assert (p.closed, p.held, p.rungs) == (None, 0.25, 2)


def test_moon_gap_through_both_rungs_sells_both_at_the_price_seen():
    p = run(MOON, [6.0])
    assert (p.held, p.rungs) == (0.25, 2)
    assert p.proceeds == pytest.approx(TOKENS * 0.75 * 6.0 * 0.98)


def test_moon_bag_rides_to_a_10x_then_trails_50_percent():
    p = run(MOON, [2.0, 5.0, 12.0, 7.0])
    assert p.closed is None  # 7 is 42% off the 12 peak
    p = run(MOON, [2.0, 5.0, 12.0, 7.0, 5.9])
    assert (p.closed, p.exit_price, p.held) == ("trailing_stop", 5.9, 0.0)
    expected = TOKENS * 0.98 * (0.5 * 2.0 + 0.25 * 5.0 + 0.25 * 5.9)
    assert pnl(MOON, p) == pytest.approx(expected - 10)


def test_moon_after_its_first_sale_never_hits_the_minus_50_stop():
    # sold half at 2×; the 50% trail from the 2.4 peak sells the rest at 1.1, not at the stop
    p = run(MOON, [2.4, 1.1])
    assert (p.closed, p.exit_price) == ("trailing_stop", 1.1)
    assert pnl(MOON, p) > 0  # the stake came back at 2×


def test_moon_dump_before_2x_is_a_plain_stop():
    p = run(MOON, [1.6, 0.4])
    assert (p.closed, p.rungs) == ("stop_loss", 0)
    assert pnl(MOON, p) == pytest.approx(TOKENS * 0.4 * 0.98 - 10)


def test_moon_holds_up_to_14_days():
    assert run(MOON, [2.5, 3.0] + [3.0] * 11, every=timedelta(days=1)).closed is None
    p = run(MOON, [2.5, 3.0] + [3.0] * 12, every=timedelta(days=1))
    assert (p.closed, p.held) == ("time", 0.0)


# --- shared rules ---


@pytest.mark.parametrize("s", STRATEGIES, ids=lambda s: s.key)
def test_vanished_liquidity_sells_what_is_left(s):
    p = run(s, [0.9], liquidity=400)
    assert (p.closed, p.exit_price) == ("liquidity_gone", 0.9)


@pytest.mark.parametrize("s", STRATEGIES, ids=lambda s: s.key)
def test_no_price_keeps_holding_then_sells_at_the_last_price_seen(s):
    p = run(s, [1.2, None, None])
    assert p.closed is None and p.last == 1.2
    p = step(s, p, None, None, T0 + s.max_hold)
    assert (p.closed, p.exit_price) == ("time", 1.2)


def test_never_priced_counts_as_lost():
    p = Position(entry=1.0, opened_at=T0)
    p = step(QUICK, p, None, None, T0 + QUICK.max_hold)
    assert p.closed == "no_price" and pnl(QUICK, p) == -10
    bad = step(QUICK, Position(entry=0.0, opened_at=T0), 1.0, None, T0)
    assert bad.closed == "no_price" and pnl(QUICK, bad) == -10


def test_a_closed_position_ignores_later_prices():
    p = run(QUICK, [2.0])
    assert step(QUICK, p, 10.0, None, T0 + timedelta(days=1)) == p


def test_strategies_are_adjustable():
    tight = replace(QUICK, ladder=((1.5, 1.0),))
    assert run(tight, [1.6]).closed == "take_profit"


# --- replay on past prices ---


def test_replay_skips_prices_from_before_the_entry_and_stops_at_the_close():
    history = [
        (T0 - timedelta(minutes=15), 9.0),  # before the alert: ignored
        (T0 + timedelta(minutes=15), 2.2),
        (T0 + timedelta(minutes=30), 5.0),
        (T0 + timedelta(minutes=45), 3.4),
        (T0 + timedelta(minutes=60), 100.0),  # after the close: ignored
    ]
    p = replay(RUNNER, Position(entry=1.0, opened_at=T0, last=1.0, peak=1.0), history)
    assert (p.closed, p.exit_price, p.peak) == ("trailing_stop", 3.4, 5.0)
    assert p.closed_at == T0 + timedelta(minutes=45)


def test_replay_of_a_short_history_leaves_it_open():
    p = replay(MOON, Position(entry=1.0, opened_at=T0, last=1.0), [(T0 + timedelta(hours=1), 2.3)])
    assert (p.closed, p.held, p.last) == (None, 0.5, 2.3)


def test_same_path_three_outcomes():
    """One coin that runs to 8× and fades: the moon bag and runner keep more of it."""
    path = [1.4, 2.1, 3.5, 6.0, 8.0, 6.5, 5.5, 3.9, 2.0, 1.2]
    results = {s.key: round(pnl(s, run(s, path)), 2) for s in STRATEGIES}
    assert results["quick"] == pytest.approx(TOKENS * 2.1 * 0.98 - 10, abs=0.01)  # sold at 2.1
    assert results["runner"] == pytest.approx(TOKENS * 5.5 * 0.98 - 10, abs=0.01)  # 31% off 8
    moon = TOKENS * 0.98 * (0.5 * 2.1 + 0.25 * 6.0 + 0.25 * 3.9)
    assert results["moon"] == pytest.approx(moon - 10, abs=0.01)  # 51% off 8
    assert results["runner"] > results["moon"] > results["quick"]


# --- summary ---


def test_summary_counts_only_closed_trades():
    trades = [
        Trade("WIN", 10, 9.21, 2.0),
        Trade("LOSS", 10, -5.2, 0.49),
        Trade("FLAT", 10, -0.4, 1.0),
        Trade("OPEN", 10, None, 1.4, open_pnl=3.45),
    ]
    s = summary(trades)
    assert (s["closed"], s["open"], s["wins"], s["win_rate_pct"]) == (3, 1, 1, 33)
    assert s["total_pnl_usd"] == 3.61 and s["return_pct"] == 12.0
    assert s["open_pnl_usd"] == 3.45
    assert s["best"] == {"symbol": "WIN", "pnl_usd": 9.21}
    assert s["worst"] == {"symbol": "LOSS", "pnl_usd": -5.2}


def test_summary_with_nothing_closed_yet():
    s = summary([Trade("OPEN", 10, None, 1.1)])
    assert s["closed"] == 0 and s["win_rate_pct"] is None and s["best"] is None
    assert summary([])["total_pnl_usd"] == 0
