from datetime import timedelta

import pytest

from app.agents import trader
from app.agents.events import EventBus
from app.agents.team import MANAGER_MODEL, SCOUT_MODEL, ask_manager
from app.db.session import SessionLocal
from app.scout import paper_book
from tests.agents.fake_claude import FakeClaude, reply
from tests.scout.fake_market import FakeMarket
from tests.scout.test_paper_book import alerted, at, step
from tests.scout.test_screen import NOW, runner

TOTALS = {
    "quick": {"total_pnl_usd": 14.86, "closed": 3},
    "runner": {"total_pnl_usd": 43.99, "closed": 3},
    "moon": {"total_pnl_usd": -0.21, "closed": 2},
}


def steps(bus: EventBus, run_id: str | None = None) -> list[tuple]:
    return [(e.agent, e.status, e.target) for e in bus.recent(run_id)]


def test_books_line_is_plain_numbers_per_strategy():
    assert trader.books_line(TOTALS) == (
        "Closed so far: Quick 2× +$14.86 (3) · Runner +$43.99 (3) · Moon bag −$0.21 (2). "
        "Paper money only."
    )


def test_bringing_the_books_to_the_scout():
    bus = EventBus()
    trader.report_books(bus, "r", TOTALS)
    assert steps(bus, "r") == [
        ("paper_trader", "working", "paper_trades"),
        ("paper_trader", "walking", "market_scout"),
        ("paper_trader", "talking", "market_scout"),
        ("paper_trader", "idle", None),
    ]


@pytest.mark.usefixtures("db")
def test_a_scan_reports_fresh_trades_and_sales_but_not_replays():
    bus = EventBus()
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    with SessionLocal() as s:
        opened = paper_book.open_missing(s)
    trader.report_scan(opened, [], bus)
    [e, idle] = bus.recent()
    assert (e.agent, e.status) == ("paper_trader", "working") and idle.status == "idle"
    assert e.text == "Opening paper trades on RUN: $10 with each of 3 strategies"

    at(market, 0.004 * 2.1)
    sales: list[str] = []
    with SessionLocal() as s:
        paper_book.update(s, market, NOW + timedelta(hours=1), sales.append)
    assert sorted(sales) == [
        "Moon bag sold half of RUN at 2.1×",
        "Quick 2× sold all of RUN at 2.1× (hit its target): +$10.17",
    ]
    bus = EventBus()
    trader.report_scan([], sales, bus)
    assert [s[1] for s in steps(bus)] == ["walking", "talking", "idle"]

    replayed = step(market, 2)  # nothing new opened or sold: the Trader stays put
    bus = EventBus()
    trader.report_scan(replayed, [], bus)
    assert bus.recent() == []


@pytest.mark.usefixtures("db")
def test_the_scout_reading_paper_trades_brings_the_trader_over():
    claude = FakeClaude(
        {
            MANAGER_MODEL: [
                reply(("tool", "ask_market_scout", {"question": "How are my paper trades?"})),
                reply(("text", "On paper, all flat so far.")),
            ],
            SCOUT_MODEL: [
                reply(("tool", "paper_trades", {})),
                reply(("text", "Nothing closed yet. Paper money only.")),
            ],
        }
    )
    bus = EventBus()
    ask_manager(claude, SessionLocal, "How are my paper trades?", bus, run_id="m")
    seen = steps(bus, "m")
    i = seen.index(("market_scout", "working", "paper_trades"))
    assert seen[i + 1 : i + 5] == [
        ("paper_trader", "working", "paper_trades"),
        ("paper_trader", "walking", "market_scout"),
        ("paper_trader", "talking", "market_scout"),
        ("paper_trader", "idle", None),
    ]
    assert seen[i + 5][0] == "market_scout"  # then the Scout carries on with its answer
    assert ("market_scout", "talking", "manager") in seen[i + 5 :]
