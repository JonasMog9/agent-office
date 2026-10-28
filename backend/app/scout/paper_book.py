"""The paper-trading book: for every alert, one pretend trade per strategy (``paper.py``),
re-priced on each scan. No real money is ever involved.

Alerts sent before a strategy existed get its trade replayed on the pool's 15-minute price
history, so all three strategies are judged on the same alerts."""

import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PaperTrade, ScoutAlert
from app.scout.paper import (
    BY_KEY,
    STRATEGIES,
    Position,
    Strategy,
    Trade,
    pnl,
    replay,
    step,
    summary,
)

log = logging.getLogger(__name__)

REPLAY_AFTER = timedelta(minutes=30)  # an alert older than this is replayed, not opened live
MAX_REPLAYS = 3  # alerts per scan; each costs 1–3 GeckoTerminal calls (about 30 a minute)
POOLS_PER_CALL = 30


def _aware(t: datetime, like: datetime | None = None) -> datetime:
    if t.tzinfo:
        return t  # SQLite returns naive times
    return t.replace(tzinfo=like.tzinfo if like and like.tzinfo else UTC)


def _position(t: PaperTrade) -> Position:
    return Position(
        entry=t.entry_price,
        opened_at=_aware(t.opened_at),
        held=t.held if t.held is not None else 1.0,
        proceeds=t.proceeds_usd or 0.0,
        rungs=t.rungs or 0,
        peak=t.peak_price,
        last=t.last_price,
    )


def _save(t: PaperTrade, s: Strategy, p: Position, checked_at: datetime) -> None:
    t.held, t.proceeds_usd, t.rungs = p.held, round(p.proceeds, 6), p.rungs
    t.peak_price, t.last_price, t.last_checked_at = p.peak, p.last, checked_at
    if p.closed:
        t.closed_at, t.exit_price, t.exit_reason = p.closed_at, p.exit_price, p.closed
        t.pnl_usd = round(pnl(s, p), 2)


def open_missing(session: Session, src=None, now: datetime | None = None) -> list[PaperTrade]:  # noqa: ANN001
    """A trade per strategy for every alert that lacks one (idempotent). With a market
    source, an alert older than REPLAY_AFTER is replayed on its price history first; if
    that history can't be fetched, it's tried again next scan."""
    have = {tuple(r) for r in session.execute(select(PaperTrade.alert_id, PaperTrade.strategy))}
    opened, replays = [], 0
    for a in session.scalars(select(ScoutAlert).order_by(ScoutAlert.id)):
        missing = [s for s in STRATEGIES if (a.id, s.key) not in have]
        if not missing or not a.price_usd:
            continue
        alerted = _aware(a.alerted_at, now)
        history = None
        if src is not None and now is not None and now - alerted > REPLAY_AFTER:
            if replays >= MAX_REPLAYS:
                continue
            replays += 1
            try:
                history = src.price_history(a.chain, a.pool_address, alerted)
            except Exception:  # noqa: BLE001
                log.warning("No price history for %s yet; will retry", a.symbol, exc_info=True)
                continue
            if not history:
                log.warning("%s has no price history: its new trades start from now", a.symbol)
        for s in missing:
            t = PaperTrade(
                alert_id=a.id,
                strategy=s.key,
                chain=a.chain,
                pool_address=a.pool_address,
                symbol=a.symbol,
                opened_at=a.alerted_at,
                stake_usd=s.stake_usd,
                entry_price=a.price_usd,
                last_price=a.price_usd,
                peak_price=a.price_usd,
                held=1.0,
                proceeds_usd=0.0,
                rungs=0,
            )
            if history:
                _save(t, s, replay(s, _position(t), history), history[-1][0])
            session.add(t)
            opened.append(t)
    session.commit()
    return opened


def update(
    session: Session,
    src,  # noqa: ANN001
    now: datetime,
    on_sale: Callable[[str], None] | None = None,
) -> list[PaperTrade]:
    """Re-price open trades and sell what the rules say. Returns the trades that closed;
    ``on_sale`` gets a line for every sale (the Paper Trader says them in the office)."""
    open_trades = session.scalars(select(PaperTrade).where(PaperTrade.closed_at.is_(None))).all()
    by_chain: dict[str, list[PaperTrade]] = defaultdict(list)
    for t in open_trades:
        by_chain[t.chain].append(t)
    closed = []
    for chain, trades in by_chain.items():
        addresses = list(dict.fromkeys(t.pool_address for t in trades))
        pools = {}
        for i in range(0, len(addresses), POOLS_PER_CALL):
            pools |= src.pool_prices(chain, addresses[i : i + POOLS_PER_CALL])
        for t in trades:
            s = BY_KEY.get(t.strategy)
            if s is None:
                continue
            pool = pools.get(t.pool_address)
            price = pool.price_usd if pool else None
            liquidity = pool.liquidity_usd if pool else None
            before = t.held
            p = step(s, _position(t), price, liquidity, now)
            _save(t, s, p, now)
            if on_sale and p.held < before:
                on_sale(sale_line(t, s, before - p.held, p.exit_price))
            if p.closed:
                closed.append(t)
    session.commit()
    return closed


def as_trade(t: PaperTrade) -> Trade:
    price = t.exit_price if t.closed_at else t.last_price
    multiple = None if not price or not t.entry_price else price / t.entry_price
    s = BY_KEY.get(t.strategy)
    open_pnl = 0.0 if t.closed_at or s is None else pnl(s, _position(t))
    return Trade(t.symbol, t.stake_usd, t.pnl_usd if t.closed_at else None, multiple, open_pnl)


def summaries(session: Session) -> dict[str, dict]:
    """Each strategy's ``paper.summary``, keyed by strategy."""
    by: dict[str, list[Trade]] = {s.key: [] for s in STRATEGIES}
    for t in session.scalars(select(PaperTrade)):
        if t.strategy in by:
            by[t.strategy].append(as_trade(t))
    return {k: summary(v) for k, v in by.items()}


def book(session: Session) -> dict:
    """Everything the Scout needs for "how are my paper trades?", strategy by strategy."""
    trades = session.scalars(select(PaperTrade).order_by(PaperTrade.opened_at.desc())).all()
    totals = summaries(session)
    out = []
    for s in STRATEGIES:
        mine = [t for t in trades if t.strategy == s.key]
        out.append(
            {
                "strategy": s.name,
                "rules": s.blurb,
                "summary": totals[s.key],
                "open": [
                    {
                        "symbol": t.symbol,
                        "opened": t.opened_at,
                        "now_x": _x(t.last_price, t.entry_price),
                        "peak_x": _x(t.peak_price, t.entry_price),
                        "sold_pct": round(100 * (1 - t.held)),
                        "pnl_if_sold_now_usd": round(pnl(s, _position(t)), 2),
                    }
                    for t in mine
                    if t.closed_at is None
                ],
                "recent_closed": [
                    {
                        "symbol": t.symbol,
                        "closed": t.closed_at,
                        "reason": t.exit_reason,
                        "last_sale_x": _x(t.exit_price, t.entry_price),
                        "peak_x": _x(t.peak_price, t.entry_price),
                        "pnl_usd": t.pnl_usd,
                    }
                    for t in mine
                    if t.closed_at is not None
                ][:5],
            }
        )
    return {
        "strategies": out,
        "note": "Paper money only: $10 per alert for each strategy, 2% fees+slippage each "
        "way. Alerts from before a strategy existed were replayed on 15-minute prices.",
    }


def _x(price: float | None, entry: float) -> float | None:
    return None if price is None or not entry else round(price / entry, 2)


REASONS = {
    "take_profit": "hit its target",
    "trailing_stop": "trailing stop",
    "stop_loss": "hit the −50% stop",
    "liquidity_gone": "liquidity vanished",
    "time": "time was up",
    "no_price": "no price could be found",
}


def _share(x: float) -> str:
    for value, words in ((1.0, "all"), (0.5, "half"), (0.25, "a quarter")):
        if abs(x - value) < 1e-6:
            return words
    return f"{round(100 * x)}%"


def sale_line(t: PaperTrade, s: Strategy, share: float, price: float | None) -> str:
    """'Moon bag sold half of RUN at 2.1×', with the P/L once the trade has closed."""
    line = f"{s.name} sold {_share(share)} of {t.symbol} at {_x(price, t.entry_price)}×"
    if t.closed_at is not None:
        line += f" ({REASONS.get(t.exit_reason or '', t.exit_reason)}): {_usd(t.pnl_usd or 0)}"
    return line


def _usd(x: float) -> str:
    return f"{'+' if x >= 0 else '−'}${abs(x):.2f}"


def closed_message(trades: list[PaperTrade], totals: dict[str, dict]) -> str:
    """Telegram text once all of a coin's paper trades have closed. Plain numbers, no model."""
    by = {t.strategy: t for t in trades}
    lines = [f"📄 Paper trades closed: {trades[0].symbol}"]
    for s in STRATEGIES:
        t = by.get(s.key)
        if t is None:
            continue
        why = REASONS.get(t.exit_reason or "", t.exit_reason)
        if t.rungs and t.exit_reason != "take_profit":
            why += f" after {t.rungs} ladder sale{'s' if t.rungs > 1 else ''}"
        lines.append(
            f"{s.name}: {why}, last sale at {_x(t.exit_price, t.entry_price)}× → "
            f"{_usd(t.pnl_usd or 0)}"
        )
    lines.append(
        "\nTotals so far: "
        + " · ".join(
            f"{s.name} {_usd(totals[s.key]['total_pnl_usd'])} ({totals[s.key]['closed']} closed)"
            for s in STRATEGIES
        )
    )
    lines.append("\nPaper money only. Not financial advice.")
    return "\n".join(lines)
