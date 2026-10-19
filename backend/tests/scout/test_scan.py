from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.models import ScoutAlert, ScoutCheck, ScoutScan
from app.db.session import SessionLocal
from app.scout.scan import run_scan
from app.scout.screen import Rules
from tests.scout.fake_market import FakeMarket
from tests.scout.test_screen import NOW, runner

pytestmark = pytest.mark.usefixtures("db")
CHAINS = ["solana", "base"]


def coin(symbol: str, **kw):
    return runner(symbol=symbol, token_address=f"T{symbol}", pool_address=f"P{symbol}", **kw)


def scan(market, now=NOW, cap=3, notify=None):
    with SessionLocal() as s:
        return run_scan(s, market, now, CHAINS, Rules(), cap, notify)


def alerts():
    with SessionLocal() as s:
        return s.scalars(select(ScoutAlert).order_by(ScoutAlert.id)).all()


def test_a_runner_that_passes_rug_tests_alerts_once():
    sent = []
    market = FakeMarket({"solana": [coin("RUN")]})
    first = scan(market, notify=sent.append)
    assert first.alerts == 1 and [a.symbol for a in sent] == ["RUN"]
    a = alerts()[0]
    assert a.volume_h24_usd == 3_000_000 and a.details["rug"]["label"] == "pass"
    # Next scan, same coin: never alerted again.
    second = scan(market, now=NOW + timedelta(minutes=10), notify=sent.append)
    assert second.alerts == 0 and len(sent) == 1


def test_failing_rug_tests_means_no_alert_but_a_recorded_near_miss():
    market = FakeMarket({"solana": [coin("RUG")]}, {"RUG": False})
    s = scan(market)
    assert s.alerts == 0 and not alerts()
    assert s.near_misses[0]["failed"] == ["rug: lp_locked"]


def test_quiet_market_records_the_closest_near_misses():
    quiet = coin("MEH", volume_usd={"h1": 40_000, "h24": 500_000})
    old = coin("OLD", created_at=NOW - timedelta(days=5))
    s = scan(FakeMarket({"solana": [quiet, old]}))
    assert (s.pools_seen, s.young, s.screened, s.alerts) == (2, 1, 0, 0)
    assert s.near_misses[0]["symbol"] == "MEH" and "volume" in s.near_misses[0]["failed"]


def test_daily_cap_holds_back_extra_runners():
    market = FakeMarket({"solana": [coin("A"), coin("B")], "base": [coin("C")]})
    s = scan(market, cap=2)
    assert s.alerts == 2
    assert any(m["failed"] == ["daily alert limit reached"] for m in s.near_misses)
    # A day later the cap has room again for the one held back.
    assert scan(market, now=NOW + timedelta(days=1, minutes=1), cap=2).alerts == 1


def test_rug_tests_are_cached_for_six_hours():
    market = FakeMarket({"solana": [coin("RUG")]}, {"RUG": False})
    scan(market)
    scan(market, now=NOW + timedelta(hours=1))
    assert market.rug_calls == ["RUG"]
    scan(market, now=NOW + timedelta(hours=7))
    assert market.rug_calls == ["RUG", "RUG"]
    with SessionLocal() as s:
        assert s.scalar(select(ScoutCheck.passed)) is False


def test_one_chain_down_still_scans_the_others():
    market = FakeMarket({"base": [coin("RUN", chain="base")]})
    market.down.add("solana")
    s = scan(market)
    assert s.alerts == 1 and s.errors == ["solana: ConnectionError"]


def test_a_failed_send_keeps_the_alert_recorded():
    def boom(alert):
        raise RuntimeError("telegram down")

    s = scan(FakeMarket({"solana": [coin("RUN")]}), notify=boom)
    assert s.alerts == 1 and len(alerts()) == 1
    with SessionLocal() as session:
        assert session.scalar(select(ScoutScan.alerts)) == 1


def test_the_deepest_pool_represents_a_token():
    shallow = replace(coin("RUN"), pool_address="P2", liquidity_usd=20_000)
    scan(FakeMarket({"solana": [shallow, coin("RUN")]}))
    assert alerts()[0].pool_address == "PRUN"
