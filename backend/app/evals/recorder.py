"""A wrapper around the Anthropic client that records every call (which agent, model,
tokens, cost, seconds, tool calls, tool results) and can swap the model per agent, so the
same app code runs under different model choices.

The agent is recognised by its system prompt (``team.MANAGER_SYSTEM`` etc.), so nothing in
the app needs to know it's being evaluated.
"""

import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from app.agents import team

# $ per million tokens: input, output. Cache reads cost 0.1× input, cache writes 1.25×.
# Haiku's rate is for prompts up to 100K tokens; ours are far smaller.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
}
FALLBACK_BETA = "server-side-fallback-2026-07-01"
NO_FALLBACKS = {"claude-haiku-5-5"}  # Haiku 5.5 has no server-side refusal fallback


def agent_of(system: str) -> str:
    for name, prompt in (
        ("manager", team.MANAGER_SYSTEM),
        ("health_coach", team.COACH_SYSTEM),
        ("market_scout", team.SCOUT_SYSTEM),
    ):
        if system.startswith(prompt[:200]):
            return name
    return "other"


def cost_usd(model: str, usage: Any) -> float:
    price_in, price_out = PRICES.get(model, (0.0, 0.0))
    fresh = getattr(usage, "input_tokens", 0) or 0
    read = getattr(usage, "cache_read_input_tokens", 0) or 0
    write = getattr(usage, "cache_creation_input_tokens", 0) or 0
    out = getattr(usage, "output_tokens", 0) or 0
    return (fresh * price_in + read * price_in * 0.1 + write * price_in * 1.25) / 1e6 + (
        out * price_out / 1e6
    )


@dataclass
class Call:
    agent: str
    model: str
    seconds: float
    input_tokens: int
    output_tokens: int
    cost_usd: float
    tool_uses: list[str]


@dataclass
class Recording:
    calls: list[Call] = field(default_factory=list)
    tool_results: dict[str, list[str]] = field(default_factory=dict)  # by the agent that asked
    instructions: dict[str, list[str]] = field(default_factory=dict)  # system + tool defs

    def results_for(self, agents: tuple[str, ...]) -> list[str]:
        return [r for a in agents for r in self.tool_results.get(a, [])]

    def tools_by(self, agent: str) -> list[str]:
        return [t for c in self.calls if c.agent == agent for t in c.tool_uses]

    def totals(self) -> dict:
        return {
            "calls": len(self.calls),
            "input_tokens": sum(c.input_tokens for c in self.calls),
            "output_tokens": sum(c.output_tokens for c in self.calls),
            "cost_usd": sum(c.cost_usd for c in self.calls),
            "model_seconds": sum(c.seconds for c in self.calls),
        }


class _Messages:
    def __init__(self, owner: "RecordingClient", api: Any) -> None:
        self.owner, self.api = owner, api

    def create(self, **kwargs: Any) -> Any:
        return self.owner._create(self.api, kwargs)


class _Beta:
    def __init__(self, owner: "RecordingClient", beta: Any) -> None:
        self.messages = _Messages(owner, beta.messages)


class RecordingClient:
    """Use in place of ``anthropic.Anthropic()``; ``models`` maps agent → model to use."""

    def __init__(
        self,
        client: Any,
        models: dict[str, str] | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.client, self.models, self.clock = client, models or {}, clock
        self.recording = Recording()
        self.messages = _Messages(self, client.messages)
        self.beta = _Beta(self, client.beta)

    def _create(self, api: Any, kwargs: dict) -> Any:
        agent = agent_of(kwargs.get("system", ""))
        model = self.models.get(agent, kwargs["model"])
        kwargs = {**kwargs, "model": model}
        if model in NO_FALLBACKS:
            kwargs.pop("fallbacks", None)
            betas = [b for b in kwargs.pop("betas", []) if b != FALLBACK_BETA]
            if betas:
                kwargs["betas"] = betas
        for m in kwargs.get("messages", []):
            content = m.get("content") if isinstance(m, dict) else None
            if m.get("role") == "user" and isinstance(content, list):
                for block in content:
                    if isinstance(block, dict) and block.get("type") == "tool_result":
                        seen = self.recording.tool_results.setdefault(agent, [])
                        if block["content"] not in seen:
                            seen.append(block["content"])
        given = self.recording.instructions.setdefault(agent, [])
        for text in (kwargs.get("system", ""), json.dumps(kwargs.get("tools", []))):
            if text and text not in given:
                given.append(text)
        start = self.clock()
        response = api.create(**kwargs)
        usage = response.usage if hasattr(response, "usage") else None
        self.recording.calls.append(
            Call(
                agent=agent,
                model=model,
                seconds=self.clock() - start,
                input_tokens=(getattr(usage, "input_tokens", 0) or 0)
                + (getattr(usage, "cache_read_input_tokens", 0) or 0)
                + (getattr(usage, "cache_creation_input_tokens", 0) or 0),
                output_tokens=getattr(usage, "output_tokens", 0) or 0,
                cost_usd=cost_usd(model, usage),
                tool_uses=[
                    b.name for b in response.content if getattr(b, "type", None) == "tool_use"
                ],
            )
        )
        return response
