"""A small, explicit agent loop over the Anthropic Messages API, with an event at every step.

    thinking   before each model call
    working    while one of our tools runs (target = the tool's name)
    talking    the final answer (target = whoever asked)
    idle       done

Tools are plain Python functions with a JSON schema. They compute; the model only explains
(CLAUDE.md: "Deterministic math, LLM for language"). A tool that raises returns an error
result to the model instead of crashing the run.
"""

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.agents.events import EventBus

log = logging.getLogger(__name__)

MAX_TOKENS = 16000
MAX_TURNS = 8


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
) -> AgentResult:
    """Run one agent until it answers, emitting events. ``client`` is an ``anthropic.Anthropic``."""
    by_name = {t.name: t for t in tools}
    messages: list[dict] = [{"role": "user", "content": prompt}]
    calls: list[str] = []
    api = client.beta.messages if use_beta else client.messages
    response = None
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
            return _finish(bus, agent, asked_by, run_id, text, calls, response.stop_reason)

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
                results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": use.id,
                        "content": json.dumps(output, default=str),
                    }
                )
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
