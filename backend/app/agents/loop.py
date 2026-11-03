"""A small, explicit agent loop over the Anthropic Messages API, with an event at every step.

    thinking   before each model call
    working    while one of our tools runs (target = the tool's name)
    talking    the final answer (target = whoever asked)
    idle       done

Tools are plain Python functions with a JSON schema. They compute; the model only explains
(CLAUDE.md: "Deterministic math, LLM for language"). A tool that raises returns an error
result to the model instead of crashing the run.

With ``guard`` on, the final answer is checked for numbers that no tool result (or the
instructions, or the question) backs up (``grounding.py``). The model gets one chance to
rewrite it; if a number still can't be traced, the answer says so instead of passing it off
as data.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agents.events import EventBus
from app.agents.grounding import ungrounded

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
MAX_TURNS = 8
MAX_FIXES = 1
FIX_PROMPT = (
    "These numbers in your answer don't appear in any tool result: {numbers}. Every "
    "number must come from a tool result. Rewrite the whole answer using only numbers "
    "from the tool results; where one isn't available, say so instead of estimating."
)


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    properties: dict
    required: list[str]
    handler: Callable[[dict], Any]
    label: str = ""  # what the office shows while it runs, e.g. "Checking recovery"

    def param(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.properties,
                "required": self.required,
                "additionalProperties": False,
            },
            "strict": True,
        }


@dataclass(frozen=True)
class AgentResult:
    text: str
    tool_calls: list[str]
    stop_reason: str | None
    unverified: tuple[str, ...] = ()  # numbers the guard couldn't trace, even after a rewrite
    fixes: int = 0  # rewrites the guard asked for


def _text_of(content: list) -> str:
    return "\n".join(b.text for b in content if getattr(b, "type", None) == "text").strip()


def run_agent(
    *,
    client: Any,
    agent: str,
    model: str,
    system: str,
    tools: list[Tool],
    prompt: str,
    bus: EventBus,
    run_id: str,
    asked_by: str = "owner",
    request_kwargs: dict | None = None,
    use_beta: bool = False,
    guard: bool = False,
) -> AgentResult:
    """Run one agent until it answers, emitting events. ``client`` is an ``anthropic.Anthropic``."""
    by_name = {t.name: t for t in tools}
    messages: list[dict] = [{"role": "user", "content": prompt}]
    calls: list[str] = []
    api = client.beta.messages if use_beta else client.messages
    response = None
    given = [system, json.dumps([t.param() for t in tools])]  # numbers the model was told
    seen: list[str] = []  # tool results so far
    fixes = 0
    for _ in range(MAX_TURNS):
        bus.emit(agent, "thinking", asked_by, "Thinking…", run_id)
        response = api.create(
            model=model,
            max_tokens=MAX_TOKENS,
            system=system,
            tools=[t.param() for t in tools],
            messages=messages,
            **(request_kwargs or {}),
        )
        if response.stop_reason == "refusal":
            text = "I can't help with that one."
            return _finish(bus, agent, asked_by, run_id, text, calls, response.stop_reason)
        uses = [b for b in response.content if getattr(b, "type", None) == "tool_use"]
        if response.stop_reason != "tool_use" or not uses:
            text = _text_of(response.content) or "(no answer)"
            bad = ungrounded(text, seen, prompt, given) if guard else []
            if bad and fixes < MAX_FIXES:
                fixes += 1
                log.warning("%s: unbacked numbers %s, asking for a rewrite", agent, bad)
                bus.emit(agent, "working", "fact_check", "Double-checking the numbers", run_id)
                messages.append({"role": "assistant", "content": response.content})
                messages.append(
                    {"role": "user", "content": FIX_PROMPT.format(numbers=", ".join(bad))}
                )
                continue
            if bad:
                log.warning("%s: still unbacked after a rewrite: %s", agent, bad)
                text += f"\n\n(Couldn't verify: {', '.join(bad)}.)"
            result = _finish(bus, agent, asked_by, run_id, text, calls, response.stop_reason)
            return AgentResult(result.text, calls, response.stop_reason, tuple(bad), fixes)

        messages.append({"role": "assistant", "content": response.content})
        results = []
        for use in uses:
            tool = by_name.get(use.name)
            calls.append(use.name)
            bus.emit(agent, "working", use.name, tool.label if tool else use.name, run_id)
            try:
                if tool is None:
                    raise ValueError(f"unknown tool {use.name}")
                output = tool.handler(dict(use.input or {}))
                content = json.dumps(output, default=str)
                seen.append(content)
                results.append({"type": "tool_result", "tool_use_id": use.id, "content": content})
            except Exception as exc:  # noqa: BLE001  (the model gets the error, the run goes on)
                log.exception("Tool %s failed", use.name)
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": use.id,
                        "content": f"Error: {exc}",
                        "is_error": True,
                    }
                )
        messages.append({"role": "user", "content": results})

    text = "I ran out of steps before finishing; please ask again more specifically."
    return _finish(bus, agent, asked_by, run_id, text, calls, response and response.stop_reason)


def _finish(
    bus: EventBus,
    agent: str,
    asked_by: str,
    run_id: str,
    text: str,
    calls: list[str],
    stop_reason: str | None,
) -> AgentResult:
    bus.emit(agent, "talking", asked_by, text, run_id)
    bus.emit(agent, "idle", None, "", run_id)
    return AgentResult(text, calls, stop_reason)
