"""The Manager, the Health Coach and the Market Scout, and how a question flows between them.

    owner ──► Manager (Haiku 5.5) ──ask_health_coach──► Health Coach (Sonnet 5.5) ──► coach tools
                                  └─ask_market_scout──► Market Scout (Sonnet 5.5) ──► scout tools

The scanner (``app.scout.scan``) also wakes the Scout on its own when a coin passes every test:
``write_alert`` has it word the alert, and the Manager carries it to the owner.

The Manager routes and relays, it never answers health questions itself. The Health Coach
explains numbers its tools return and never invents one (CLAUDE.md).
"""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.agents import coach_tools
from app.agents.events import EventBus
from app.agents.events import bus as default_bus
from app.agents.loop import AgentResult, Tool, run_agent
from app.agents.scout_tools import alert_view, dexscreener_url, scout_tools
from app.db.models import ScoutAlert
from app.scout import settings as scout_settings
from app.scout.screen import Rules
from app.scout.sources import MarketData

MANAGER_MODEL = "claude-haiku-5-5"
COACH_MODEL = "claude-sonnet-5-5"
# Sonnet 5.5's safety classifiers can decline; "default" re-runs a declined request on
# Anthropic's recommended fallback model server-side instead of failing the turn.
COACH_REQUEST = {
    "betas": ["server-side-fallback-2026-07-01"],
    "fallbacks": "default",
    "output_config": {"effort": "medium"},
}
MANAGER_REQUEST = {"output_config": {"effort": "low"}}
SCOUT_MODEL = "claude-sonnet-5-5"
SCOUT_REQUEST = COACH_REQUEST
NOT_ADVICE = "Not financial advice."

COACH_SYSTEM = """You are the Health Coach in the owner's personal "Agent Office": a running \
coach working from their own Apple Watch and Strava data.

How you work:
- Every number you mention must come from a tool result in this conversation. Never estimate, \
compute or round a number yourself beyond what a tool returned; if no tool gives it, say you \
don't have it.
- Call the tools you need first (several at once is fine), then answer.
- "Today" means the owner's local date; pass "today" as the date unless they name a day.
- Explain the reasons behind a score using its breakdown (e.g. HRV vs. baseline), briefly.
- When recovery is red or yellow, also call get_warnings, and mention a possible-illness or \
injury-risk warning with its evidence if there is one.
- When asked what to run, use get_plan; if there's no plan, give guidance from recovery, \
load and zones and offer to build a plan with adjust_plan. Only call adjust_plan when the \
owner asks for a plan or a new goal.
- The owner is coming back from a hip injury. If they mention pain, call get_plan with \
pain=true, tell them to rest, and suggest a physio if it persists. You are not a doctor.
- Apple Watch HRV is SDNN; compare it only with the owner's own baseline.
- The owner's watch can't measure wrist temperature. Never mention wrist temperature.
- Durations (sleep, debt, need) as hours and minutes, exactly as the tools give them \
("6 h 12 min"). Say fitness, fatigue and form, not CTL/ATL/TSB.

Style: plain language, short. Lead with the answer. A few lines, no headings; this is read \
on a phone in Telegram."""

SCOUT_SYSTEM = f"""You are the Market Scout in the owner's "Agent Office". You watch new \
crypto coins for potential runners: coins at most two days old trading huge, real volume, \
that also pass rug tests. Alerts are rare by design; most days nothing qualifies.

How you work:
- Read-only. You never buy, sell or hold anything, and you never tell the owner to buy or \
sell. You say what the numbers show and what the risks are.
- Every number you mention must come from a tool result in this conversation. Never \
estimate one.
- "Anything up?", "how's the market?", "any runners?" → latest_scan. A coin the owner names \
by its address → check_token (chain "auto" unless they say which).
- Name every rug test a coin fails, plainly. A failed or unknown test means it can't be \
trusted. Passing them all still doesn't make a coin safe: new coins are extremely volatile.
- If nothing qualified, say so, and mention the closest near miss and what it failed.
- "Paper trades", "P/L", "how are the trades doing?" → paper_trades. It's paper money only: \
say so, and give the win rate and total as the tool gives them.

Style: short and plain, read on a phone in Telegram. Money as the tools give it ("$3.1M"). \
End every answer with the line: {NOT_ADVICE}"""

ALERT_PROMPT = """A coin just passed the potential-runner screen and every rug test. Call \
get_alert, then write the Telegram alert. First line: "🚀 Potential runner: SYMBOL on CHAIN". \
Then 3–5 short lines: how old it is; 24 h and last-hour volume; liquidity and FDV; buyers vs \
sellers; that it passed the rug tests (briefly, which ones matter most). Finish with one line \
on the risk: new coins can drop fast, and rug tests can't catch everything. No buy or sell \
advice. Don't add links; they're added for you."""

MANAGER_SYSTEM = """You are the Manager of the owner's "Agent Office". You don't answer \
questions yourself: you route them to the right specialist and pass the answer back.

- Health, sleep, recovery, training, running, races, plans → ask_health_coach. Pass the \
owner's question on in full, with any context they gave.
- Crypto or market questions, or a pasted token address → ask_market_scout. Pass the \
question on in full, with the address exactly as given.
- Greetings or questions about what you can do: answer briefly yourself.
- Relay the specialist's answer faithfully. Keep every number exactly as given; you may \
shorten wording, never change or add numbers. Keep the Market Scout's last line \
("Not financial advice.") as it is."""


def ask_health_coach(
    client: Any,
    session_factory: Callable[[], Session],
    question: str,
    bus: EventBus,
    run_id: str,
    asked_by: str = "manager",
) -> AgentResult:
    return run_agent(
        client=client,
        agent="health_coach",
        model=COACH_MODEL,
        system=COACH_SYSTEM + f"\n\nToday is {coach_tools.today().isoformat()}.",
        tools=coach_tools.coach_tools(session_factory),
        prompt=question,
        bus=bus,
        run_id=run_id,
        asked_by=asked_by,
        request_kwargs=COACH_REQUEST,
        use_beta=True,
    )


def with_disclaimer(text: str) -> str:
    """CLAUDE.md: every Scout brief ends with a not-financial-advice line. Guaranteed here."""
    text = text.rstrip()
    return text if text.endswith(NOT_ADVICE) else f"{text}\n\n{NOT_ADVICE}"


def ask_market_scout(
    client: Any,
    session_factory: Callable[[], Session],
    question: str,
    bus: EventBus,
    run_id: str,
    rules: Rules,
    src_factory: Callable[[], MarketData] = MarketData,
) -> AgentResult:
    result = run_agent(
        client=client,
        agent="market_scout",
        model=SCOUT_MODEL,
        system=SCOUT_SYSTEM,
        tools=scout_tools(session_factory, src_factory, rules),
        prompt=question,
        bus=bus,
        run_id=run_id,
        asked_by="manager",
        request_kwargs=SCOUT_REQUEST,
        use_beta=True,
    )
    return AgentResult(with_disclaimer(result.text), result.tool_calls, result.stop_reason)


def write_alert(client: Any, alert: ScoutAlert, bus: EventBus = default_bus) -> str:
    """The Scout words a potential-runner alert; the Manager carries it to the owner."""
    run_id = uuid.uuid4().hex[:12]
    view = alert_view(alert)
    spotted = f"Spotted a potential runner: {alert.symbol}"
    bus.emit("market_scout", "working", "get_alert", spotted, run_id)
    bus.emit("manager", "walking", "market_scout", "Picking up the Scout's alert", run_id)
    what = "The coin that just passed, with its numbers and rug tests."
    tool = Tool("get_alert", what, {}, [], lambda _: view, "Writing the alert")
    result = run_agent(
        client=client,
        agent="market_scout",
        model=SCOUT_MODEL,
        system=SCOUT_SYSTEM,
        tools=[tool],
        prompt=ALERT_PROMPT,
        bus=bus,
        run_id=run_id,
        asked_by="manager",
        request_kwargs=SCOUT_REQUEST,
        use_beta=True,
    )
    body = result.text.rstrip()
    if body.endswith(NOT_ADVICE):
        body = body[: -len(NOT_ADVICE)].rstrip()
    chart = dexscreener_url(alert.chain, alert.pool_address)
    links = f"Chart: {chart}\nContract: {alert.token_address}"
    text = with_disclaimer(f"{body}\n\n{links}")
    bus.emit("manager", "walking", "owner", "Bringing you the alert", run_id)
    bus.emit("manager", "talking", "owner", text.splitlines()[0], run_id)
    bus.emit("manager", "idle", None, "", run_id)
    return text


def ask_manager(
    client: Any,
    session_factory: Callable[[], Session],
    question: str,
    bus: EventBus = default_bus,
    run_id: str | None = None,
    scout_rules: Rules | None = None,
) -> AgentResult:
    """Answer one owner message through the Manager. Every step lands on ``bus``."""
    run_id = run_id or uuid.uuid4().hex[:12]

    def to_coach(args: dict) -> dict:
        bus.emit("manager", "walking", "health_coach", "Asking the Health Coach", run_id)
        result = ask_health_coach(client, session_factory, args["question"], bus, run_id)
        bus.emit("manager", "walking", "owner", "Back with the answer", run_id)
        return {"answer": result.text}

    def to_scout(args: dict) -> dict:
        bus.emit("manager", "walking", "market_scout", "Asking the Market Scout", run_id)
        result = ask_market_scout(
            client,
            session_factory,
            args["question"],
            bus,
            run_id,
            scout_rules or scout_settings.rules(),
        )
        bus.emit("manager", "walking", "owner", "Back with the answer", run_id)
        return {"answer": result.text}

    question_prop = {"question": {"type": "string", "description": "The question, in full."}}
    tools = [
        Tool(
            "ask_health_coach",
            "Ask the Health Coach a health, sleep, training or running "
            "question. Returns its answer.",
            question_prop,
            ["question"],
            to_coach,
            "Asking the Health Coach",
        ),
        Tool(
            "ask_market_scout",
            "Ask the Market Scout a crypto question: new-coin runners, the latest scan, "
            "rug tests on a coin's contract address, or the paper-trading results. "
            "Returns its answer.",
            question_prop,
            ["question"],
            to_scout,
            "Asking the Market Scout",
        ),
    ]
    bus.emit("manager", "thinking", "owner", question, run_id)
    result = run_agent(
        client=client,
        agent="manager",
        model=MANAGER_MODEL,
        system=MANAGER_SYSTEM,
        tools=tools,
        prompt=question,
        bus=bus,
        run_id=run_id,
        request_kwargs=MANAGER_REQUEST,
    )
    if "ask_market_scout" in result.tool_calls:  # the relayed answer keeps the disclaimer
        return AgentResult(with_disclaimer(result.text), result.tool_calls, result.stop_reason)
    return result
