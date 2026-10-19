from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import PaperTrade
from app.db.session import SessionLocal
from app.scout import paper_book
from app.scout.scan import run_scan
from app.scout.screen import Rules
from tests.scout.fake_market import FakeMarket
from tests.scout.test_screen import NOW, runner

pytestmark = pytest.mark.usefixtures("db")


def alerted(market: FakeMarket) -> None:
    with SessionLocal() as s:
        run_scan(s, market, NOW, ["solana"], Rules(), 3)


def at(market: FakeMarket, price: float | None, liquidity: float = 300_000) -> None:
    market.prices["POOL"] = replace(runner(), price_usd=price, liquidity_usd=liquidity)


def step(market: FakeMarket, hours: float) -> list[PaperTrade]:
    with SessionLocal() as s:
        paper_book.open_missing(s)
        return paper_book.update(s, market, NOW + timedelta(hours=hours))


def test_every_alert_gets_one_paper_trade_at_its_alert_price():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    with SessionLocal() as s:
        assert len(paper_book.open_missing(s)) == 1
        assert paper_book.open_missing(s) == []  # idempotent
        t = s.scalar(select(PaperTrade))
    assert (t.symbol, t.entry_price, t.stake_usd, t.closed_at) == ("RUN", 0.004, 10, None)


def test_a_double_closes_with_profit_after_costs():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.006)
    assert step(market, 1) == []
    at(market, 0.0084)  # 2.1x
    [t] = step(market, 2)
    assert t.exit_reason == "take_profit" and t.pnl_usd == pytest.approx(10.17, abs=0.01)
    assert t.peak_price == 0.0084


def test_a_dump_hits_the_stop_and_a_rug_closes_on_liquidity():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.0015)
    [t] = step(market, 1)
    assert t.exit_reason == "stop_loss" and t.pnl_usd < -6


def test_vanished_liquidity_closes_at_the_price_seen():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.003, liquidity=200)
    [t] = step(market, 1)
    assert t.exit_reason == "liquidity_gone" and t.exit_price == 0.003


def test_after_three_days_it_sells_at_the_last_price_it_saw():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.005)
    step(market, 10)
    market.prices.clear()  # the pool stops showing up
    assert step(market, 30) == []
    [t] = step(market, 73)
    assert (t.exit_reason, t.exit_price) == ("time", 0.005)


def test_book_and_close_message():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.0084)
    [t] = step(market, 2)
    with SessionLocal() as s:
        b = paper_book.book(s)
    assert b["summary"]["closed"] == 1 and b["summary"]["win_rate_pct"] == 100
    assert b["recent_closed"][0]["exit_x"] == 2.1 and b["open"] == []
    msg = paper_book.closed_message(t, b["summary"])
    assert "RUN (hit 2×), sold at 2.1× → +$10.17 on $10" in msg
    assert msg.endswith("Paper money only. Not financial advice.")
