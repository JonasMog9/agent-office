"""The Paper Trader: the office's fourth robot, on the Market Scout's team.

It isn't an AI model. It is the paper-trading book (``app/scout/paper_book.py``) given a body,
so the office shows when paper trades open and sell, and when the Scout asks it for the
numbers. Everything it says is built from the book in Python.
"""

import uuid
from collections.abc import Sequence

from app.agents.events import EventBus
from app.agents.events import bus as default_bus
from app.db.models import PaperTrade
from app.scout.paper import STRATEGIES

AGENT = "paper_trader"


def _usd(x: float) -> str:
    return f"{'+' if x >= 0 else '−'}${abs(x):.2f}"


def books_line(totals: dict[str, dict]) -> str:
    """'Closed so far: Quick 2× +$14.86 (3) · Runner +$43.99 (3) · Moon bag −$0.21 (2).'"""
    parts = [
        f"{s.name} {_usd(totals[s.key]['total_pnl_usd'])} ({totals[s.key]['closed']})"
        for s in STRATEGIES
    ]
    return "Closed so far: " + " · ".join(parts) + ". Paper money only."


def report_books(bus: EventBus, run_id: str, totals: dict[str, dict]) -> None:
    """The Scout asked for the paper trades: the Trader brings it the books."""
    bus.emit(AGENT, "working", "paper_trades", "Pulling the books", run_id)
    bus.emit(AGENT, "walking", "market_scout", "Bringing the Scout the books", run_id)
    bus.emit(AGENT, "talking", "market_scout", books_line(totals), run_id)
    bus.emit(AGENT, "idle", None, "", run_id)


def report_scan(
    opened: Sequence[PaperTrade], sales: Sequence[str], bus: EventBus = default_bus
) -> None:
    """After a scan: new paper trades opened live (not replays), and any sales."""
    fresh = list(dict.fromkeys(t.symbol for t in opened if t.last_checked_at is None))
    if not fresh and not sales:
        return
    run_id = uuid.uuid4().hex[:12]
    if fresh:
        text = f"Opening paper trades on {', '.join(fresh)}: $10 with each of 3 strategies"
        bus.emit(AGENT, "working", "paper_trades", text, run_id)
    if sales:
        bus.emit(AGENT, "walking", "market_scout", "Telling the Scout about a sale", run_id)
        bus.emit(AGENT, "talking", "market_scout", ". ".join(sales) + ".", run_id)
    bus.emit(AGENT, "idle", None, "", run_id)
