from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.agents import coach_tools
from app.config import get_settings
from app.db.models import DailyScore, PaperTrade, ScoutAlert, ScoutScan
from app.db.session import SessionLocal
from app.main import app

TODAY = date(2026, 10, 19)
NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


@pytest.fixture
def client(db, monkeypatch: pytest.MonkeyPatch):  # noqa: ANN001, ANN201
    monkeypatch.setenv("OFFICE_VIEW_KEY", "k" * 24)
    get_settings.cache_clear()
    monkeypatch.setattr(coach_tools, "today", lambda: TODAY)
    import app.stats as stats

    monkeypatch.setattr(stats, "today", lambda: TODAY)
    yield TestClient(app)
    get_settings.cache_clear()


def seed() -> None:
    with SessionLocal() as s:
        s.add(
            DailyScore(
                day=TODAY,
                recovery=74.4,
                recovery_label="green",
                strain=11.26,
                ctl=31.04,
                atl=40.6,
                details={},
            )
        )
        s.add(
            DailyScore(day=TODAY - timedelta(days=2), recovery=31, recovery_label="red", details={})
        )
        s.add(
            DailyScore(
                day=TODAY - timedelta(days=40), recovery=99, recovery_label="green", details={}
            )
        )
        a = ScoutAlert(
            chain="solana",
            token_address="M",
            pool_address="P",
            symbol="RUN",
            alerted_at=NOW - timedelta(days=3),
            price_usd=0.01,
            fdv_usd=9e6,
            liquidity_usd=3e5,
            volume_h24_usd=6.1e6,
            details={},
            message="",
        )
        b = ScoutAlert(
            chain="base",
            token_address="0x1",
            pool_address="0xp",
            symbol="UHI",
            alerted_at=NOW - timedelta(days=1),
            price_usd=1.0,
            fdv_usd=2e6,
            liquidity_usd=1e5,
            volume_h24_usd=1.2e6,
            details={},
            message="",
        )
        s.add_all([a, b])
        s.flush()
        s.add(
            PaperTrade(
                alert_id=a.id,
                chain="solana",
                pool_address="P",
                symbol="RUN",
                opened_at=a.alerted_at,
                stake_usd=10,
                entry_price=0.01,
                last_price=0.021,
                peak_price=0.024,
                closed_at=NOW,
                exit_price=0.021,
                exit_reason="take_profit",
                pnl_usd=10.17,
                held=0.0,
                proceeds_usd=20.17,
                rungs=1,
            )
        )
        s.add(
            PaperTrade(
                alert_id=a.id,
                strategy="moon",
                chain="solana",
                pool_address="P",
                symbol="RUN",
                opened_at=a.alerted_at,
                stake_usd=10,
                entry_price=0.01,
                last_price=0.03,
                peak_price=0.052,
                held=0.25,
                proceeds_usd=22.5,
                rungs=2,
            )
        )
        s.add(
            PaperTrade(
                alert_id=b.id,
                chain="base",
                pool_address="0xp",
                symbol="UHI",
                opened_at=b.alerted_at,
                stake_usd=10,
                entry_price=1.0,
                last_price=0.9,
                peak_price=1.05,
            )
        )
        s.add(
            ScoutScan(
                ran_at=NOW, pools_seen=60, young=8, screened=1, alerts=0, near_misses=[], errors=[]
            )
        )
        s.commit()


def test_needs_the_office_key(client: TestClient) -> None:
    assert client.get("/stats").status_code == 401
    assert client.get("/stats", headers={"X-Office-Key": "wrong"}).status_code == 401


def test_thirty_days_with_gaps_and_scout_outcomes(client: TestClient) -> None:
    seed()
    body = client.get("/stats", headers={"X-Office-Key": "k" * 24}).json()
    days = body["health"]
    assert len(days) == 30 and days[-1]["day"] == "2026-10-19"
    assert days[-1]["recovery"] == 74 and days[-1]["fitness"] == 31.0
    assert days[-3]["label"] == "red"
    assert days[-2]["recovery"] is None  # a missing day stays a gap
    assert all(d["recovery"] != 99 for d in days)  # older than 30 days
    scout = body["scout"]
    assert scout["scans_30d"] == 1
    newest, oldest = scout["alerts"]
    assert (newest["symbol"], newest["peak_x"]) == ("UHI", 1.05)
    assert newest["trades"]["quick"] == {
        "status": "open",
        "exit_reason": None,
        "now_x": 0.9,
        "sold_pct": 0,
        "pnl_usd": None,
        "pnl_now_usd": round(10 * 0.98 * 0.9 * 0.98 - 10, 2),
    }
    assert oldest["peak_x"] == 5.2  # the highest any strategy saw
    quick, moon = oldest["trades"]["quick"], oldest["trades"]["moon"]
    assert (quick["status"], quick["now_x"], quick["pnl_usd"]) == ("closed", 2.1, 10.17)
    assert (moon["status"], moon["sold_pct"], moon["now_x"]) == ("open", 75, 3.0)
    assert moon["pnl_now_usd"] == round(22.5 + 0.25 * 980 * 0.03 * 0.98 - 10, 2)

    by = {x["key"]: x for x in scout["strategies"]}
    assert list(by) == ["quick", "runner", "moon"]
    assert by["quick"]["name"] == "Quick 2×" and by["moon"]["blurb"].startswith("Sell half")
    assert by["quick"]["summary"]["total_pnl_usd"] == 10.17
    assert by["quick"]["curve"] == [{"at": by["quick"]["curve"][0]["at"], "pnl_usd": 10.17}]
    assert by["moon"]["summary"]["closed"] == 0 and by["moon"]["summary"]["open"] == 1
    assert by["runner"]["curve"] == [] and by["runner"]["summary"]["open"] == 0
    assert scout["paper"]["closed"] == 1 and scout["paper"]["win_rate_pct"] == 100
