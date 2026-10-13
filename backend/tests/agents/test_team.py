import json
from datetime import date

import pytest

from app.agents import coach_tools
from app.agents.events import EventBus
from app.agents.loop import MAX_TURNS, Tool, run_agent
from app.agents.team import COACH_MODEL, MANAGER_MODEL, ask_manager
from app.db.models import DailyMetric, DailyScore
from app.db.session import SessionLocal
from tests.agents.fake_claude import FakeClaude, reply

TODAY = date(2026, 10, 13)


@pytest.fixture
def seeded(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(coach_tools, "today", lambda: TODAY)
    with SessionLocal() as s:
        s.add(DailyMetric(day=TODAY, sleep_asleep_min=480, hrv_sdnn_ms=70))
        s.add(
            DailyScore(
                day=TODAY,
                recovery=77,
                recovery_label="green",
                strain=0.0,
                sleep_need_min=512,
                sleep_debt_min=129,
                sleep_performance=93,
                sleep_consistency=42,
                ctl=32.3,
                atl=14.2,
                form=16.5,
                acwr=0.66,
                hr_rest_used=54,
                hr_max_used=191,
                details={
                    "recovery": {
                        "value": 77,
                        "label": "green",
                        "components": [{"name": "hrv", "value": 70.3, "baseline": 53.0, "z": 2.0}],
                        "notes": [],
                    }
                },
                load_details={"notes": ["Load well below your 4-week average."]},
            )
        )
        s.commit()


@pytest.mark.usefixtures("db", "seeded")
def test_question_flows_manager_to_coach_to_tools_and_back() -> None:
    claude = FakeClaude(
        {
            MANAGER_MODEL: [
                reply(("tool", "ask_health_coach", {"question": "How recovered am I today?"})),
                reply(("text", "You're at 77% recovery, green.")),
            ],
            COACH_MODEL: [
                reply(("tool", "get_recovery", {"date": "today"})),
                reply(("text", "77%, green: HRV 70 vs your usual 53.")),
            ],
        }
    )
    bus = EventBus()
    result = ask_manager(claude, SessionLocal, "How recovered am I today?", bus, run_id="r1")

    assert result.text == "You're at 77% recovery, green."
    assert result.tool_calls == ["ask_health_coach"]
    # The coach saw real stored numbers, not anything the model made up.
    [tool_result] = claude.tool_results(COACH_MODEL)
    payload = json.loads(tool_result["content"])
    assert payload["recovery"] == 77 and payload["label"] == "green"
    assert payload["breakdown"]["components"][0]["baseline"] == 53.0
    # The manager relays the coach's answer.
    [relay] = claude.tool_results(MANAGER_MODEL)
    assert json.loads(relay["content"])["answer"] == "77%, green: HRV 70 vs your usual 53."

    events = [(e.agent, e.status, e.target) for e in bus.recent("r1")]
    assert events == [
        ("manager", "thinking", "owner"),
        ("manager", "thinking", "owner"),
        ("manager", "working", "ask_health_coach"),
        ("manager", "walking", "health_coach"),
        ("health_coach", "thinking", "manager"),
        ("health_coach", "working", "get_recovery"),
        ("health_coach", "thinking", "manager"),
        ("health_coach", "talking", "manager"),
        ("health_coach", "idle", None),
        ("manager", "walking", "owner"),
        ("manager", "thinking", "owner"),
        ("manager", "talking", "owner"),
        ("manager", "idle", None),
    ]
    assert [e.id for e in bus.recent("r1")] == sorted(e.id for e in bus.recent("r1"))


@pytest.mark.usefixtures("db", "seeded")
def test_models_and_request_settings() -> None:
    claude = FakeClaude(
        {
            MANAGER_MODEL: [
                reply(("tool", "ask_health_coach", {"question": "q"})),
                reply(("text", "a")),
            ],
            COACH_MODEL: [reply(("text", "a"))],
        }
    )
    ask_manager(claude, SessionLocal, "q", EventBus())
    manager, coach, _ = claude.requests
    assert manager["model"] == "claude-haiku-5-5" and not manager["beta"]
    assert coach["model"] == "claude-sonnet-5-5" and coach["beta"]
    assert coach["fallbacks"] == "default" and coach["betas"] == ["server-side-fallback-2026-07-01"]
    assert all(
        t["strict"] and not t["input_schema"]["additionalProperties"] for t in coach["tools"]
    )
    assert {t["name"] for t in coach["tools"]} >= {
        "get_recovery",
        "get_sleep",
        "get_strain",
        "get_training_load",
        "predict_race",
        "get_plan",
        "adjust_plan",
        "get_warnings",
        "get_zones",
        "get_trend",
    }
    assert "2026-10-13" in coach["system"]


@pytest.mark.usefixtures("db", "seeded")
def test_coach_tools_return_stored_numbers() -> None:
    tools = {t.name: t for t in coach_tools.coach_tools(SessionLocal)}
    sleep = tools["get_sleep"].handler({"date": "today"})
    assert sleep["sleep_debt_min"] == 129 and sleep["asleep_last_night_min"] == 480
    load = tools["get_training_load"].handler({"date": "2026-10-13"})
    assert load["form"] == 16 and load["flags"] == ["Load well below your 4-week average."]
    zones = tools["get_zones"].handler({})
    assert zones["heart_rate_zones"][1]["to_bpm"] == 150  # zone 2 top, 54 rest / 191 max
    assert "no prediction yet" in zones["vdot_source"]
    assert tools["get_plan"].handler({"pain": False})["plan"] is None
    with pytest.raises(LookupError):
        tools["get_recovery"].handler({"date": "2026-01-01"})


@pytest.mark.usefixtures("db", "seeded")
def test_a_failing_tool_goes_back_to_the_model_as_an_error() -> None:
    claude = FakeClaude(
        {
            COACH_MODEL: [
                reply(("tool", "get_recovery", {"date": "2026-01-01"})),
                reply(("text", "I don't have scores for that day.")),
            ]
        }
    )
    result = run_agent(
        client=claude,
        agent="health_coach",
        model=COACH_MODEL,
        system="s",
        tools=coach_tools.coach_tools(SessionLocal),
        prompt="q",
        bus=EventBus(),
        run_id="r",
    )
    [err] = claude.tool_results(COACH_MODEL)
    assert err["is_error"] and "No scores stored" in err["content"]
    assert result.text == "I don't have scores for that day."


def test_refusal_and_runaway_loops_end_cleanly() -> None:
    bus = EventBus()
    claude = FakeClaude({"m": [reply(("text", ""), stop_reason="refusal")]})
    r = run_agent(
        client=claude,
        agent="manager",
        model="m",
        system="s",
        tools=[],
        prompt="q",
        bus=bus,
        run_id="a",
    )
    assert r.stop_reason == "refusal" and bus.recent("a")[-1].status == "idle"

    echo = Tool("echo", "d", {}, [], lambda args: {"ok": True})
    loop = FakeClaude({"m": [reply(("tool", "echo", {})) for _ in range(MAX_TURNS)]})
    r = run_agent(
        client=loop,
        agent="manager",
        model="m",
        system="s",
        tools=[echo],
        prompt="q",
        bus=bus,
        run_id="b",
    )
    assert "ran out of steps" in r.text and len(loop.requests) == MAX_TURNS


def test_market_scout_is_not_built_yet() -> None:
    claude = FakeClaude(
        {
            MANAGER_MODEL: [
                reply(("tool", "ask_market_scout", {"question": "BTC?"})),
                reply(("text", "Not yet.")),
            ]
        }
    )
    bus = EventBus()
    ask_manager(claude, SessionLocal, "BTC?", bus, run_id="s")
    assert ("market_scout", "talking") in [(e.agent, e.status) for e in bus.recent("s")]


def test_event_bus_validates_and_survives_bad_subscribers() -> None:
    bus = EventBus()
    seen = []
    bus.subscribe(lambda e: 1 / 0)
    unsubscribe = bus.subscribe(seen.append)
    bus.emit("manager", "talking", "owner", "x" * 400)
    assert len(seen) == 1 and len(seen[0].text) == 280
    unsubscribe()
    bus.emit("manager", "idle")
    assert len(seen) == 1
    with pytest.raises(ValueError):
        bus.emit("manager", "dancing")
    with pytest.raises(ValueError):
        bus.emit("intern", "idle")


def test_tool_numbers_come_rounded() -> None:
    assert coach_tools.tidy({"hrv": 26.29, "acwr": 0.664, "x": [372.5, 1.234], "n": 3}) == {
        "hrv": 26,
        "acwr": 0.66,
        "x": [372, 1.23],
        "n": 3,
    }
