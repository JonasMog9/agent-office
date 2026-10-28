"""Paper trading: would the Scout's alerts have made money, and which way of selling works
best? Pure rules, no real trades.

Every alert "buys" a pretend STAKE at the price when the alert went out, once for each
strategy. Each scan checks the price again and the strategy decides whether to sell:

    1 Quick 2×   sell everything at 2×; stop at −50%; sell what's left after 3 days.
    2 Runner     no fixed target. Once it has reached 2×, sell everything when it falls 30%
                 below its peak (so a 5× that fades sells near 3.5×); stop at −50% before
                 that; sell after 7 days.
    3 Moon bag   sell half at 2× (the stake back), a quarter at 5×, and let the last quarter
                 ride for a 10×+ with a wide 50% trailing stop, up to 14 days; stop at −50%
                 before the first sale.

All three also sell what's left if the pool's liquidity falls below $1,000 (as good as
rugged).

Why these: new-coin returns are extremely skewed. Most fall 90%+ from their peak (Coin
Metrics / Talos, 2025: 81% of Solana memecoins), while a few run far past 2×, so selling
everything at 2× caps the winners that have to pay for all the losers. The common trader
advice is to take the stake out around 2× and let a small "moon bag" ride, or to trail a
stop 25–35% under the peak instead of using a fixed target. None of it is backed by
independent backtests, which is the point of running all three side by side on the same
alerts.

It sells at the price seen when a rule fires, not at the threshold: with a check every
10 minutes a price can gap past 2× or 0.5×, and pretending otherwise would flatter the
results. Fees and slippage are charged on both sides (COST per side), so a round trip at an
unchanged price loses about 4%.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import datetime, timedelta

COST = 0.02  # fees + slippage, per side
DUST = 1e-9


@dataclass(frozen=True)
class Strategy:
    key: str
    name: str
    blurb: str  # one line for the stats page and the Scout
    ladder: tuple[tuple[float, float], ...]  # (× entry, share of the position to sell there)
    max_hold: timedelta
    stop_loss: float = 0.5  # × entry; only before the first sale and before the trail arms
    trail: float | None = None  # sell what's left this far below the peak...
    trail_from: float = 2.0  # ...once the peak has reached this × entry
    stake_usd: float = 10.0
    min_liquidity_usd: float = 1_000
    cost: float = COST


QUICK = Strategy(
    "quick",
    "Quick 2×",
    "Sell everything at 2×. Stop at −50%, sell after 3 days.",
    ladder=((2.0, 1.0),),
    max_hold=timedelta(days=3),
)
RUNNER = Strategy(
    "runner",
    "Runner",
    "No fixed target: once it hits 2×, sell when it drops 30% from its peak. "
    "Stop at −50%, sell after 7 days.",
    ladder=(),
    max_hold=timedelta(days=7),
    trail=0.30,
)
MOON = Strategy(
    "moon",
    "Moon bag",
    "Sell half at 2× (stake back) and a quarter at 5×; the last quarter rides for 10× or "
    "more with a 50% trailing stop, up to 14 days.",
    ladder=((2.0, 0.5), (5.0, 0.25)),
    max_hold=timedelta(days=14),
    trail=0.50,
)
STRATEGIES = (QUICK, RUNNER, MOON)
BY_KEY = {s.key: s for s in STRATEGIES}


@dataclass(frozen=True)
class Position:
    """One strategy's pretend trade on one alert."""

    entry: float
    opened_at: datetime
    held: float = 1.0  # share of the position still held
    proceeds: float = 0.0  # USD from sales so far, after costs
    rungs: int = 0  # ladder steps sold
    peak: float | None = None
    last: float | None = None  # the last price seen
    closed: str | None = None  # the exit reason, once nothing is held
    exit_price: float | None = None  # the price of the last sale
    closed_at: datetime | None = None


def _sell(s: Strategy, p: Position, share: float, price: float, reason: str) -> Position:
    tokens = s.stake_usd * (1 - s.cost) / p.entry
    held = p.held - share
    done = held <= DUST
    return replace(
        p,
        held=0.0 if done else held,
        proceeds=p.proceeds + tokens * share * price * (1 - s.cost),
        exit_price=price,
        closed=reason if done else None,
    )


def step(
    s: Strategy,
    p: Position,
    price: float | None,
    liquidity_usd: float | None,
    now: datetime,
) -> Position:
    """Apply one price check to an open position: sell whatever the rules say."""
    if p.closed:
        return p
    out = _step(s, p, price, liquidity_usd, now)
    return replace(out, closed_at=now) if out.closed else out


def _step(
    s: Strategy, p: Position, price: float | None, liquidity_usd: float | None, now: datetime
) -> Position:
    if p.entry <= 0:
        return replace(p, held=0.0, exit_price=0.0, closed="no_price")
    if price is not None:
        p = replace(p, peak=max(p.peak or price, price), last=price)
        while p.rungs < len(s.ladder) and price >= p.entry * s.ladder[p.rungs][0]:
            share = min(s.ladder[p.rungs][1], p.held)
            p = replace(_sell(s, p, share, price, "take_profit"), rungs=p.rungs + 1)
        if p.closed:
            return p
        armed = s.trail is not None and p.peak >= p.entry * s.trail_from  # type: ignore[operator]
        if armed and price <= p.peak * (1 - s.trail):  # type: ignore[operator]
            return _sell(s, p, p.held, price, "trailing_stop")
        if not armed and p.rungs == 0 and price <= p.entry * s.stop_loss:
            return _sell(s, p, p.held, price, "stop_loss")
    seen = price if price is not None else p.last
    if liquidity_usd is not None and liquidity_usd < s.min_liquidity_usd:
        return _sell(s, p, p.held, seen or 0.0, "liquidity_gone")
    if now - p.opened_at >= s.max_hold:
        if seen is None:
            return _sell(s, p, p.held, 0.0, "no_price")  # never priced: count it as lost
        return _sell(s, p, p.held, seen, "time")
    return p


def replay(s: Strategy, p: Position, history: Sequence[tuple[datetime, float]]) -> Position:
    """Run a position through past prices (oldest first), for alerts sent before a strategy
    existed. Prices from before the entry are skipped."""
    for at, price in history:
        if at <= p.opened_at:
            continue
        p = step(s, p, price, None, at)
        if p.closed:
            break
    return p


def pnl(s: Strategy, p: Position) -> float:
    """Profit or loss in USD: sales so far plus what's still held at the last price, after
    costs. Final once the position is closed."""
    if p.entry <= 0:
        return -s.stake_usd
    tokens = s.stake_usd * (1 - s.cost) / p.entry
    return p.proceeds + tokens * p.held * (p.last or 0.0) * (1 - s.cost) - s.stake_usd


@dataclass(frozen=True)
class Trade:
    symbol: str
    stake: float
    pnl: float | None  # None while open
    multiple: float | None  # exit (or latest) price / entry
    open_pnl: float = 0.0  # while open: what it would make if sold now


def summary(trades: Sequence[Trade]) -> dict:
    """Win rate, total P/L and the best and worst calls, over closed trades; plus what the
    open ones would make if sold now."""
    closed = [t for t in trades if t.pnl is not None]
    still_open = [t for t in trades if t.pnl is None]
    wins = [t for t in closed if t.pnl > 0]  # type: ignore[operator]
    total = sum(t.pnl for t in closed)  # type: ignore[misc]
    staked = sum(t.stake for t in closed)
    best = max(closed, key=lambda t: t.pnl, default=None)  # type: ignore[arg-type, return-value]
    worst = min(closed, key=lambda t: t.pnl, default=None)  # type: ignore[arg-type, return-value]
    return {
        "closed": len(closed),
        "open": len(still_open),
        "wins": len(wins),
        "win_rate_pct": round(100 * len(wins) / len(closed)) if closed else None,
        "total_pnl_usd": round(total, 2),
        "return_pct": round(100 * total / staked, 1) if staked else None,
        "open_pnl_usd": round(sum(t.open_pnl for t in still_open), 2),
        "best": None if best is None else {"symbol": best.symbol, "pnl_usd": round(best.pnl, 2)},
        "worst": None
        if worst is None
        else {"symbol": worst.symbol, "pnl_usd": round(worst.pnl, 2)},
    }
