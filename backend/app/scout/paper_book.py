"""The paper-trading book: open a pretend trade for every alert, re-price open trades on
each scan, close them by the rules in ``paper.py``. No real money is ever involved."""

from collections import defaultdict
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import PaperTrade, ScoutAlert
from app.scout.paper import DEFAULT, PaperRules, Trade, exit_reason, pnl_usd, summary


def _aware(t: datetime, like: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=like.tzinfo)  # SQLite returns naive times


def open_missing(session: Session, rules: PaperRules = DEFAULT) -> list[PaperTrade]:
    """A trade for every alert that has none yet (idempotent; covers alerts sent earlier)."""
    have = set(session.scalars(select(PaperTrade.alert_id)))
    opened = []
    for a in session.scalars(select(ScoutAlert).order_by(ScoutAlert.id)):
        if a.id in have or not a.price_usd:
            continue
        t = PaperTrade(
            alert_id=a.id,
            chain=a.chain,
            pool_address=a.pool_address,
            symbol=a.symbol,
            opened_at=a.alerted_at,
            stake_usd=rules.stake_usd,
            entry_price=a.price_usd,
            last_price=a.price_usd,
            peak_price=a.price_usd,
        )
        session.add(t)
        opened.append(t)
    session.commit()
    return opened


def update(session: Session, src, now: datetime, rules: PaperRules = DEFAULT) -> list[PaperTrade]:  # noqa: ANN001
    """Re-price open trades and close those a rule fires on. Returns the ones just closed."""
    open_trades = session.scalars(select(PaperTrade).where(PaperTrade.closed_at.is_(None))).all()
    by_chain: dict[str, list[PaperTrade]] = defaultdict(list)
    for t in open_trades:
        by_chain[t.chain].append(t)
    closed = []
    for chain, trades in by_chain.items():
        pools = src.pool_prices(chain, [t.pool_address for t in trades])
        for t in trades:
            pool = pools.get(t.pool_address)
            price = pool.price_usd if pool else None
            liquidity = pool.liquidity_usd if pool else None
            if price is not None:
                t.last_price = price
                t.peak_price = max(t.peak_price or price, price)
            t.last_checked_at = now
            reason = exit_reason(
                t.entry_price, price, liquidity, _aware(t.opened_at, now), now, rules
            )
            if reason is None:
                continue
            exit_price = price if price is not None else t.last_price
            if exit_price is None:
                exit_price, reason = 0.0, "no_price"  # never priced: count it as lost
            t.closed_at, t.exit_price, t.exit_reason = now, exit_price, reason
            t.pnl_usd = round(pnl_usd(t.stake_usd, t.entry_price, exit_price, rules.cost), 2)
            closed.append(t)
    session.commit()
    return closed


def as_trade(t: PaperTrade) -> Trade:
    price = t.exit_price if t.closed_at else t.last_price
    multiple = None if not price or not t.entry_price else price / t.entry_price
    return Trade(t.symbol, t.stake_usd, t.pnl_usd if t.closed_at else None, multiple)


def book(session: Session) -> dict:
    """Everything the Scout needs for "how are my paper trades?"."""
    trades = session.scalars(select(PaperTrade).order_by(PaperTrade.opened_at.desc())).all()
    return {
        "summary": summary([as_trade(t) for t in trades]),
        "open": [
            {
                "symbol": t.symbol,
                "opened": t.opened_at,
                "now_x": _x(t.last_price, t.entry_price),
                "peak_x": _x(t.peak_price, t.entry_price),
                "unrealised_pnl_usd": round(
                    pnl_usd(t.stake_usd, t.entry_price, t.last_price or 0), 2
                ),
            }
            for t in trades
            if t.closed_at is None
        ],
        "recent_closed": [
            {
                "symbol": t.symbol,
                "closed": t.closed_at,
                "reason": t.exit_reason,
                "exit_x": _x(t.exit_price, t.entry_price),
                "peak_x": _x(t.peak_price, t.entry_price),
                "pnl_usd": t.pnl_usd,
            }
            for t in trades
            if t.closed_at is not None
        ][:10],
        "rules": "Paper money only: $10 per alert, sell at 2x, -50%, if liquidity "
        "vanishes, or after 3 days; 2% fees+slippage each way.",
    }


def _x(price: float | None, entry: float) -> float | None:
    return None if price is None or not entry else round(price / entry, 2)


REASONS = {
    "take_profit": "hit 2×",
    "stop_loss": "hit the −50% stop",
    "liquidity_gone": "its liquidity vanished",
    "time": "3 days were up",
    "no_price": "no price could be found",
}


def closed_message(t: PaperTrade, totals: dict) -> str:
    """Telegram text for a closed paper trade. Plain numbers, no model involved."""
    sign = "+" if (t.pnl_usd or 0) >= 0 else "−"
    x = _x(t.exit_price, t.entry_price)
    return (
        f"📄 Paper trade closed: {t.symbol} ({REASONS.get(t.exit_reason or '', t.exit_reason)}), "
        f"sold at {x}× → {sign}${abs(t.pnl_usd or 0):.2f} on ${t.stake_usd:.0f}.\n"
        f"Paper total: {'+' if totals['total_pnl_usd'] >= 0 else '−'}"
        f"${abs(totals['total_pnl_usd']):.2f} over {totals['closed']} closed trades "
        f"({totals['win_rate_pct']}% wins).\n\nPaper money only. Not financial advice."
    )
