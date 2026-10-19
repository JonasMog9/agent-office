import json
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.agents import scout_tools
from app.agents.events import EventBus
from app.agents.team import (
    MANAGER_MODEL,
    NOT_ADVICE,
    SCOUT_MODEL,
    ask_manager,
    with_disclaimer,
    write_alert,
)
from app.db.models import ScoutAlert
from app.db.session import SessionLocal
from app.scout.scan import run_scan
from app.scout.screen import Rules
from tests.agents.fake_claude import FakeClaude, reply
from tests.scout.fake_market import FakeMarket
from tests.scout.test_screen import NOW, runner

pytestmark = pytest.mark.usefixtures("db")


def test_money_reads_like_money():
    assert [scout_tools.usd(x) for x in (3_140_000, 412_000, 950, 0.0042, None)] == [
        "$3.1M",
        "$412k",
        "$950",
        "$0.0042",
        None,
    ]


def test_addresses_pick_their_chain():
    assert scout_tools.guess_chains("0x" + "a" * 40, "auto") == ["base", "eth"]
    assert scout_tools.guess_chains("7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr", "auto") == [
        "solana"
    ]
    assert scout_tools.guess_chains("anything", "eth") == ["eth"]
    with pytest.raises(ValueError):
        scout_tools.guess_chains("not an address!", "auto")


def test_check_token_runs_the_screen_and_rug_tests():
    market = FakeMarket({"solana": [runner()]}, {"RUN": False})
    out = scout_tools.check_token(market, "MINT", "solana", NOW, Rules())
    assert out["market_screen"] == "pass" and out["rug_tests"] == "fail"
    assert out["volume_24h"] == "$3.0M" and out["age"] == "10 h"
    assert out["chart"] == "https://dexscreener.com/solana/POOL"
    with pytest.raises(LookupError):
        scout_tools.check_token(market, "OTHERMINT11111111111111111111111", "solana", NOW, Rules())


def test_latest_scan_reports_near_misses_and_recent_alerts():
    with SessionLocal() as s:
        assert "No scan" in scout_tools.latest_scan(s, NOW)["note"]
        run_scan(s, FakeMarket({"solana": [runner()]}), NOW, ["solana"], Rules(), 3)
        meh = runner(symbol="MEH", token_address="T2", volume_usd={"h1": 9_000, "h24": 300_000})
        run_scan(
            s, FakeMarket({"solana": [meh]}), NOW + timedelta(minutes=10), ["solana"], Rules(), 3
        )
        out = scout_tools.latest_scan(s, NOW + timedelta(minutes=11))
    assert out["scans_last_24h"] == 2 and out["coins_under_48h"] == 1
    assert (
        out["near_misses"][0]["symbol"] == "MEH"
        and out["near_misses"][0]["volume_h24_usd"] == "$300k"
    )
    assert [a["symbol"] for a in out["alerts_last_7_days"]] == ["RUN"]


def test_every_scout_answer_ends_with_not_financial_advice():
    assert with_disclaimer("Nothing today.") == f"Nothing today.\n\n{NOT_ADVICE}"
    assert with_disclaimer(f"Quiet.\n{NOT_ADVICE}") == f"Quiet.\n{NOT_ADVICE}"


def _alert() -> ScoutAlert:
    with SessionLocal() as s:
        run_scan(s, FakeMarket({"solana": [runner()]}), NOW, ["solana"], Rules(), 3)
        return s.scalar(select(ScoutAlert))


def test_write_alert_words_it_and_adds_links_and_the_disclaimer():
    claude = FakeClaude(
        {
            SCOUT_MODEL: [
                reply(("tool", "get_alert", {})),
                reply(("text", "🚀 Potential runner: RUN on solana\n10 h old, $3.0M volume.")),
            ]
        }
    )
    bus = EventBus()
    text = write_alert(claude, _alert(), bus)
    assert text.startswith("🚀 Potential runner: RUN")
    assert "Chart: https://dexscreener.com/solana/POOL" in text and "Contract: MINT" in text
    assert text.endswith(NOT_ADVICE) and text.count(NOT_ADVICE) == 1
    got = json.loads(claude.tool_results(SCOUT_MODEL)[0]["content"])
    assert got["volume_24h"] == "$3.0M" and got["rug_tests"] == "pass"
    steps = [(e.agent, e.status, e.target) for e in bus.recent()]
    assert ("manager", "walking", "market_scout") in steps
    assert steps[-3:] == [
        ("manager", "walking", "owner"),
        ("manager", "talking", "owner"),
        ("manager", "idle", None),
    ]


def test_manager_routes_crypto_questions_to_the_scout():
    claude = FakeClaude(
        {
            MANAGER_MODEL: [
                reply(("tool", "ask_market_scout", {"question": "Any runners today?"})),
                reply(("text", "Nothing qualified today.")),  # the Manager drops the line
            ],
            SCOUT_MODEL: [
                reply(("tool", "latest_scan", {})),
                reply(("text", "Nothing qualified today; closest was MEH.")),
            ],
        }
    )
    bus = EventBus()
    result = ask_manager(claude, SessionLocal, "Any runners today?", bus, run_id="m")
    scout_answer = json.loads(claude.tool_results(MANAGER_MODEL)[0]["content"])["answer"]
    assert scout_answer.endswith(NOT_ADVICE)
    assert result.text.endswith(NOT_ADVICE)
    scout_req = next(r for r in claude.requests if r["model"] == SCOUT_MODEL)
    assert {t["name"] for t in scout_req["tools"]} == {"latest_scan", "check_token", "paper_trades"}
    assert scout_req["beta"] and scout_req["fallbacks"] == "default"
    assert ("manager", "walking", "market_scout") in [
        (e.agent, e.status, e.target) for e in bus.recent("m")
    ]
