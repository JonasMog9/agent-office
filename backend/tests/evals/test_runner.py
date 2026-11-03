import pytest

from app.agents.team import COACH_MODEL, MANAGER_MODEL, SCOUT_MODEL
from app.db.session import SessionLocal
from app.evals import runner, world
from app.evals.cases import CASES
from app.evals.grade import Case
from tests.agents.fake_claude import FakeClaude, reply

pytestmark = pytest.mark.usefixtures("db")


def test_the_cases_are_well_formed():
    ids = [c.id for c in CASES]
    assert len(ids) == len(set(ids)) >= 50
    assert {c.route for c in CASES} == {"health_coach", "market_scout", "none", "both"}
    assert [c.id for c in CASES if c.mutates] == ["new-plan"]


def test_the_world_is_built_from_the_real_pipeline():
    from app.agents.coach_tools import coach_tools
    from app.agents.scout_tools import scout_tools
    from app.scout.screen import Rules

    with SessionLocal() as s:
        market = world.build(s)
    tools = {t.name: t for t in coach_tools(SessionLocal)}
    rec = tools["get_recovery"].handler({"date": "today"})
    assert rec["label"] == "red"  # run down today
    assert tools["get_plan"].handler({"pain": False})["today"]["today"]["kind"] == "rest"
    scout = {t.name: t for t in scout_tools(SessionLocal, lambda: market, Rules())}
    scan = scout["latest_scan"].handler({})
    assert [a["symbol"] for a in scan["alerts_last_7_days"]] == ["DUD", "RUN"]
    assert scan["near_misses"][0]["symbol"] == "MEH"
    rug = scout["check_token"].handler({"address": world.RUG_MINT, "chain": "auto"})
    assert rug["rug_tests"] == "fail"


def test_a_case_runs_through_the_real_manager_and_is_graded():
    with SessionLocal() as s:
        market = world.build(s)
    claude = FakeClaude(
        {
            MANAGER_MODEL: [
                reply(("tool", "ask_market_scout", {"question": "How are my paper trades?"})),
                reply(("text", "Runner leads with +$9.99 so far. Not financial advice.")),
            ],
            SCOUT_MODEL: [
                reply(("tool", "paper_trades", {})),
                reply(("text", "Runner leads. Not financial advice.")),
            ],
        }
    )
    case = Case("paper", "How are my paper trades?", "market_scout", ("paper_trades",))
    r = runner.run_case(claude, case, runner.SETUPS["production"], market)
    assert r["specialists"] == ["market_scout"] and r["tools"] == ["paper_trades"]
    assert r["checks"]["route"] and r["checks"]["tools"] and r["checks"]["disclaimer"]
    assert r["checks"]["grounded"] is False and r["ungrounded"] == ["$9.99"]  # made up
    assert r["calls"] == 4


def test_summary_and_report():
    rows = [
        {
            "id": "a",
            "passed": True,
            "checks": {"route": True, "grounded": True},
            "seconds": 4,
            "cost_usd": 0.02,
            "output_tokens": 300,
            "error": None,
            "ungrounded": [],
            "answer": "ok",
            "specialists": ["health_coach"],
            "tools": ["get_recovery"],
        },
        {
            "id": "b",
            "passed": False,
            "checks": {"route": True, "grounded": False},
            "seconds": 8,
            "cost_usd": 0.04,
            "output_tokens": 500,
            "error": None,
            "ungrounded": ["81%"],
            "answer": "Recovery 81%.",
            "specialists": ["health_coach"],
            "tools": ["get_recovery"],
        },
    ]
    s = runner.summarise(rows)
    assert (s["passed"], s["pass_rate_pct"], s["cost_per_answer_usd"]) == (1, 50.0, 0.03)
    assert s["check_pass_rate_pct"] == {"route": 100.0, "grounded": 50.0}
    md = runner.report(
        [
            {
                "setup": "production",
                "models": runner.SETUPS["production"],
                "summary": s,
                "cases": rows,
            }
        ],
        "2026-11-03",
    )
    assert "| production | haiku 5.5 / sonnet 5.5 / sonnet 5.5 | 1/2 (50.0%) |" in md
    assert "**b** (grounded)" in md and "Unbacked numbers: 81%." in md
    assert COACH_MODEL  # the production setup mirrors team.py's models
    assert runner.SETUPS["production"] == {
        "manager": MANAGER_MODEL,
        "health_coach": COACH_MODEL,
        "market_scout": SCOUT_MODEL,
    }
