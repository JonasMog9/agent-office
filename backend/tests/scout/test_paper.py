from datetime import UTC, datetime, timedelta

import pytest

from app.scout.paper import PaperRules, Trade, exit_reason, pnl_usd, summary

T0 = datetime(2026, 10, 19, 12, tzinfo=UTC)


def reason(price, liquidity=200_000, hours=1):
    return exit_reason(1.0, price, liquidity, T0, T0 + timedelta(hours=hours))


def test_holds_while_no_rule_fires():
    assert reason(1.3) is None
    assert reason(0.6) is None


def test_take_profit_and_stop_loss_fire_at_their_multiples():
    assert reason(2.0) == "take_profit"
    assert reason(3.7) == "take_profit"  # gapped past 2x: still sells, at 3.7
    assert reason(0.5) == "stop_loss"
    assert reason(0.01) == "stop_loss"


def test_vanished_liquidity_closes_it():
    assert reason(0.9, liquidity=400) == "liquidity_gone"


def test_sells_after_three_days():
    assert reason(1.2, hours=71) is None
    assert reason(1.2, hours=72) == "time"


def test_no_price_keeps_holding_until_the_time_limit():
    assert reason(None) is None
    assert reason(None, hours=80) == "time"


def test_rules_are_adjustable():
    tight = PaperRules(take_profit=1.5)
    assert exit_reason(1.0, 1.6, None, T0, T0, tight) == "take_profit"


def test_pnl_pays_costs_both_ways():
    assert pnl_usd(10, 1.0, 1.0) == pytest.approx(10 * 0.98 * 0.98 - 10)  # -0.40
    assert pnl_usd(10, 1.0, 2.0) == pytest.approx(10 * 0.98 * 2 * 0.98 - 10)  # +9.21
    assert pnl_usd(10, 1.0, 0.0) == -10
    assert pnl_usd(10, 0.0, 1.0) == -10  # no entry price: count it as lost


def test_summary_counts_only_closed_trades():
    trades = [
        Trade("WIN", 10, 9.21, 2.0),
        Trade("LOSS", 10, -5.2, 0.49),
        Trade("FLAT", 10, -0.4, 1.0),
        Trade("OPEN", 10, None, 1.4),
    ]
    s = summary(trades)
    assert (s["closed"], s["open"], s["wins"], s["win_rate_pct"]) == (3, 1, 1, 33)
    assert s["total_pnl_usd"] == 3.61 and s["return_pct"] == 12.0
    assert s["best"] == {"symbol": "WIN", "pnl_usd": 9.21}
    assert s["worst"] == {"symbol": "LOSS", "pnl_usd": -5.2}


def test_summary_with_nothing_closed_yet():
    s = summary([Trade("OPEN", 10, None, 1.1)])
    assert s["closed"] == 0 and s["win_rate_pct"] is None and s["best"] is None
    assert summary([])["total_pnl_usd"] == 0
