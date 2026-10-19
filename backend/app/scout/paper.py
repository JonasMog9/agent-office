"""Paper trading: would the Scout's alerts have made money? Pure rules, no real trades.

Every alert "buys" a pretend STAKE at the price when the alert went out. Each scan checks
the price again and "sells" at the first rule that fires:

    take_profit    price ≥ 2× the entry
    stop_loss      price ≤ 0.5× the entry
    liquidity_gone the pool's liquidity fell below $1,000 (as good as rugged)
    time           3 days after the entry

It sells at the price seen when the rule fires, not at the threshold: with a check every
10 minutes a price can gap past 2× or 0.5×, and pretending otherwise would flatter the
results. Fees and slippage are charged on both sides (COST per side), so a round trip at an
unchanged price loses about 4%.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime, timedelta


@dataclass(frozen=True)
class PaperRules:
    stake_usd: float = 10.0
    take_profit: float = 2.0  # × entry
    stop_loss: float = 0.5  # × entry
    max_hold: timedelta = timedelta(days=3)
    min_liquidity_usd: float = 1_000
    cost: float = 0.02  # fees + slippage, per side


DEFAULT = PaperRules()


def exit_reason(
    entry: float,
    price: float | None,
    liquidity_usd: float | None,
    opened_at: datetime,
    now: datetime,
    rules: PaperRules = DEFAULT,
) -> str | None:
    """Which rule closes the trade now, or None to keep holding."""
    if price is not None and entry > 0:
        if price >= entry * rules.take_profit:
            return "take_profit"
        if price <= entry * rules.stop_loss:
            return "stop_loss"
    if liquidity_usd is not None and liquidity_usd < rules.min_liquidity_usd:
        return "liquidity_gone"
    if now - opened_at >= rules.max_hold:
        return "time"
    return None


def pnl_usd(stake: float, entry: float, exit_price: float, cost: float = DEFAULT.cost) -> float:
    """Profit or loss in USD, after paying ``cost`` on the way in and on the way out."""
    if entry <= 0:
        return -stake
    tokens = stake * (1 - cost) / entry
    return tokens * exit_price * (1 - cost) - stake


@dataclass(frozen=True)
class Trade:
    symbol: str
    stake: float
    pnl: float | None  # None while open
    multiple: float | None  # exit (or latest) price / entry


def summary(trades: Sequence[Trade]) -> dict:
    """Win rate, total P/L and the best and worst calls, over closed trades."""
    closed = [t for t in trades if t.pnl is not None]
    wins = [t for t in closed if t.pnl > 0]  # type: ignore[operator]
    total = sum(t.pnl for t in closed)  # type: ignore[misc]
    staked = sum(t.stake for t in closed)
    best = max(closed, key=lambda t: t.pnl, default=None)  # type: ignore[arg-type, return-value]
    worst = min(closed, key=lambda t: t.pnl, default=None)  # type: ignore[arg-type, return-value]
    return {
        "closed": len(closed),
        "open": len(trades) - len(closed),
        "wins": len(wins),
        "win_rate_pct": round(100 * len(wins) / len(closed)) if closed else None,
        "total_pnl_usd": round(total, 2),
        "return_pct": round(100 * total / staked, 1) if staked else None,
        "best": None if best is None else {"symbol": best.symbol, "pnl_usd": round(best.pnl, 2)},
        "worst": None
        if worst is None
        else {"symbol": worst.symbol, "pnl_usd": round(worst.pnl, 2)},
    }
