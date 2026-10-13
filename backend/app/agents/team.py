"""The Manager and the Health Coach, and how a question flows between them.

    owner ──► Manager (Haiku 5.5) ──ask_health_coach──► Health Coach (Sonnet 5.5) ──► coach tools
                                  └─ask_market_scout──► (Phase 6; says it's not built yet)

The Manager routes and relays, it never answers health questions itself. The Health Coach
explains numbers its tools return and never invents one (CLAUDE.md).
"""

import uuid
from collections.abc import Callable
from typing import Any

from sqlalchemy.orm import Session

from app.agents.coach_tools import coach_tools, today
from app.agents.events import EventBus
from app.agents.events import bus as default_bus
from app.agents.loop import AgentResult, Tool, run_agent

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

Style: plain language, short. Lead with the answer. A few lines, no headings; this is read \
on a phone in Telegram."""

MANAGER_SYSTEM = """You are the Manager of the owner's "Agent Office". You don't answer \
questions yourself: you route them to the right specialist and pass the answer back.

- Health, sleep, recovery, training, running, races, plans → ask_health_coach. Pass the \
owner's question on in full, with any context they gave.
- Crypto or market questions → ask_market_scout.
- Greetings or questions about what you can do: answer briefly yourself.
- Relay the specialist's answer faithfully. Keep every number exactly as given; you may \
shorten wording, never change or add numbers."""


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
        system=COACH_SYSTEM + f"\n\nToday is {today().isoformat()}.",
        tools=coach_tools(session_factory),
        prompt=question,
        bus=bus,
        run_id=run_id,
        asked_by=asked_by,
        request_kwargs=COACH_REQUEST,
        use_beta=True,
    )


def ask_manager(
    client: Any,
    session_factory: Callable[[], Session],
    question: str,
    bus: EventBus = default_bus,
    run_id: str | None = None,
) -> AgentResult:
    """Answer one owner message through the Manager. Every step lands on ``bus``."""
    run_id = run_id or uuid.uuid4().hex[:12]

    def to_coach(args: dict) -> dict:
        bus.emit("manager", "walking", "health_coach", "Asking the Health Coach", run_id)
        result = ask_health_coach(client, session_factory, args["question"], bus, run_id)
        bus.emit("manager", "walking", "owner", "Back with the answer", run_id)
        return {"answer": result.text}

    def to_scout(args: dict) -> dict:
        bus.emit("manager", "walking", "market_scout", "Checking with the Market Scout", run_id)
        bus.emit("market_scout", "talking", "manager", "I'm not set up yet (Phase 6).", run_id)
        bus.emit("market_scout", "idle", None, "", run_id)
        return {"answer": "The Market Scout isn't built yet; it arrives in a later phase."}

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
            "Ask the Market Scout a crypto/market question.",
            question_prop,
            ["question"],
            to_scout,
            "Asking the Market Scout",
        ),
    ]
    bus.emit("manager", "thinking", "owner", question, run_id)
    return run_agent(
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
