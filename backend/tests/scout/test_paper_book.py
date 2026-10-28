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


def trades() -> dict[str, PaperTrade]:
    with SessionLocal() as s:
        return {t.strategy: t for t in s.scalars(select(PaperTrade))}


def test_every_alert_gets_one_trade_per_strategy_at_its_alert_price():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    with SessionLocal() as s:
        assert len(paper_book.open_missing(s)) == 3
        assert paper_book.open_missing(s) == []  # idempotent
    ts = trades()
    assert sorted(ts) == ["moon", "quick", "runner"]
    assert {(t.entry_price, t.stake_usd, t.held, t.closed_at) for t in ts.values()} == {
        (0.004, 10, 1.0, None)
    }


def test_a_double_closes_quick_and_half_of_the_moon_bag():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.006)
    assert step(market, 1) == []
    at(market, 0.0084)  # 2.1x
    [t] = step(market, 2)
    assert t.strategy == "quick" and t.exit_reason == "take_profit"
    assert t.pnl_usd == pytest.approx(10.17, abs=0.01) and t.peak_price == 0.0084
    ts = trades()
    assert (ts["moon"].held, ts["moon"].rungs, ts["moon"].closed_at) == (0.5, 1, None)
    assert ts["runner"].held == 1.0 and ts["runner"].closed_at is None


def test_a_dump_stops_all_three_and_a_rug_closes_on_liquidity():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.0015)
    closed = step(market, 1)
    assert {t.exit_reason for t in closed} == {"stop_loss"} and len(closed) == 3
    assert all(t.pnl_usd < -6 for t in closed)


def test_vanished_liquidity_closes_at_the_price_seen():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.003, liquidity=200)
    closed = step(market, 1)
    assert {(t.exit_reason, t.exit_price) for t in closed} == {("liquidity_gone", 0.003)}


def test_each_strategy_keeps_its_own_time_limit():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.005)
    step(market, 10)
    market.prices.clear()  # the pool stops showing up
    assert step(market, 30) == []
    [t] = step(market, 73)
    assert (t.strategy, t.exit_reason, t.exit_price) == ("quick", "time", 0.005)
    [t] = step(market, 7 * 24)
    assert t.strategy == "runner"
    [t] = step(market, 14 * 24)
    assert t.strategy == "moon"


def test_old_alerts_are_replayed_on_price_history():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    e = 0.004
    market.history["POOL"] = [
        (NOW + timedelta(minutes=15 * i), e * x)
        for i, x in enumerate([1.0, 1.5, 2.2, 4.0, 6.0, 4.1, 3.2], 1)
    ]
    later = NOW + timedelta(hours=3)
    with SessionLocal() as s:
        assert len(paper_book.open_missing(s, market, later)) == 3
    assert market.history_calls == ["POOL"]  # one fetch serves all three strategies
    ts = trades()
    assert ts["quick"].exit_reason == "take_profit" and ts["quick"].exit_price == e * 2.2
    assert ts["runner"].exit_reason == "trailing_stop" and ts["runner"].exit_price == e * 4.1
    assert ts["runner"].closed_at.replace(tzinfo=None) == (NOW + timedelta(minutes=90)).replace(
        tzinfo=None
    )
    # moon: half at 2.2, a quarter at 6.0, and the last quarter still riding (3.2 > half of 6)
    assert (ts["moon"].held, ts["moon"].rungs, ts["moon"].closed_at) == (0.25, 2, None)


def test_a_fresh_alert_is_opened_live_and_a_failed_history_is_retried():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    with SessionLocal() as s:
        assert len(paper_book.open_missing(s, market, NOW + timedelta(minutes=10))) == 3
    assert market.history_calls == []  # too fresh to need a replay

    with SessionLocal() as s:
        for t in s.scalars(select(PaperTrade).where(PaperTrade.strategy != "quick")):
            s.delete(t)
        s.commit()
    market.down.add("history")
    with SessionLocal() as s:
        assert paper_book.open_missing(s, market, NOW + timedelta(days=1)) == []
    market.down.clear()
    with SessionLocal() as s:
        assert len(paper_book.open_missing(s, market, NOW + timedelta(days=1))) == 2


def test_book_and_one_message_when_a_coin_is_done():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    for hours, x in [(1, 2.1), (2, 5.2), (3, 3.5), (4, 2.7)]:
        at(market, 0.004 * x)
        step(market, hours)
    ts = trades()
    assert ts["runner"].exit_reason == "trailing_stop" and ts["moon"].closed_at is None
    at(market, 0.004 * 2.7, liquidity=300)  # rugged: the moon bag sells the rest
    [moon] = step(market, 5)
    with SessionLocal() as s:
        b = paper_book.book(s)
        totals = paper_book.summaries(s)
        all_three = s.scalars(select(PaperTrade)).all()
    by = {x["strategy"]: x for x in b["strategies"]}
    assert list(by) == ["Quick 2×", "Runner", "Moon bag"]
    assert by["Quick 2×"]["summary"]["win_rate_pct"] == 100
    assert by["Runner"]["recent_closed"][0]["last_sale_x"] == 3.5
    assert by["Moon bag"]["open"] == [] and "rules" in by["Moon bag"]
    msg = paper_book.closed_message(list(all_three), totals)
    assert msg.startswith("📄 Paper trades closed: RUN")
    assert "Quick 2×: hit its target, last sale at 2.1× → +$10.17" in msg
    assert "Runner: trailing stop, last sale at 3.5× → +$" in msg
    assert "Moon bag: liquidity vanished after 2 ladder sales, last sale at 2.7× → +$" in msg
    assert msg.endswith("Paper money only. Not financial advice.")
    assert moon.pnl_usd == pytest.approx(
        10 * 0.98 * 0.98 * (0.5 * 2.1 + 0.25 * 5.2 + 0.25 * 2.7) - 10, abs=0.01
    )


def test_open_trades_show_what_selling_now_would_make():
    market = FakeMarket({"solana": [runner()]})
    alerted(market)
    at(market, 0.004 * 2.5)
    step(market, 1)
    with SessionLocal() as s:
        moon = next(x for x in paper_book.book(s)["strategies"] if x["strategy"] == "Moon bag")
    [o] = moon["open"]
    assert (o["sold_pct"], o["now_x"]) == (50, 2.5)
    assert o["pnl_if_sold_now_usd"] == pytest.approx(10 * 0.98 * 0.98 * 2.5 - 10, abs=0.01)
