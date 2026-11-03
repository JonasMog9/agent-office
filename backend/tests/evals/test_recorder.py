from types import SimpleNamespace

import pytest

from app.agents import team
from app.evals.recorder import RecordingClient, agent_of, cost_usd


def usage(i=1000, o=200, read=0, write=0):
    return SimpleNamespace(
        input_tokens=i,
        output_tokens=o,
        cache_read_input_tokens=read,
        cache_creation_input_tokens=write,
    )


class Api:
    def __init__(self) -> None:
        self.sent: list[dict] = []

    def create(self, **kw):
        self.sent.append(kw)
        content = [SimpleNamespace(type="tool_use", name="get_recovery")]
        return SimpleNamespace(content=content, usage=usage(), stop_reason="tool_use")


class Client:
    def __init__(self) -> None:
        self.messages = Api()
        self.beta = SimpleNamespace(messages=Api())


def test_agents_are_told_apart_by_their_system_prompt():
    assert agent_of(team.MANAGER_SYSTEM) == "manager"
    assert agent_of(team.COACH_SYSTEM + "\n\nToday is 2026-11-03.") == "health_coach"
    assert agent_of(team.SCOUT_SYSTEM) == "market_scout"
    assert agent_of("something else") == "other"


def test_cost_uses_each_models_price_and_cache_rates():
    assert cost_usd("claude-sonnet-5-5", usage(1_000_000, 100_000)) == pytest.approx(3.0)
    assert cost_usd("claude-haiku-5-5", usage(1_000_000, 100_000)) == pytest.approx(0.15)
    cached = usage(0, 0, read=1_000_000, write=1_000_000)
    assert cost_usd("claude-sonnet-5-5", cached) == pytest.approx(0.2 + 2.5)


def test_swapping_the_coach_to_haiku_drops_the_fallback_beta_and_records_the_call():
    inner = Client()
    rec = RecordingClient(
        inner, {"health_coach": "claude-haiku-5-5"}, clock=iter([0, 1.5]).__next__
    )
    rec.beta.messages.create(
        model="claude-sonnet-5-5",
        system=team.COACH_SYSTEM,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[
            {"role": "user", "content": "How recovered am I?"},
            {"role": "user", "content": [{"type": "tool_result", "content": '{"recovery": 8}'}]},
        ],
    )
    [sent] = inner.beta.messages.sent
    assert sent["model"] == "claude-haiku-5-5"
    assert "fallbacks" not in sent and "betas" not in sent
    [call] = rec.recording.calls
    assert (call.agent, call.model, call.seconds, call.tool_uses) == (
        "health_coach",
        "claude-haiku-5-5",
        1.5,
        ["get_recovery"],
    )
    assert rec.recording.results_for(("health_coach",)) == ['{"recovery": 8}']
    assert rec.recording.results_for(("manager",)) == []


def test_without_a_swap_the_request_goes_out_unchanged():
    inner = Client()
    rec = RecordingClient(inner)
    rec.messages.create(model="claude-haiku-5-5", system=team.MANAGER_SYSTEM, messages=[])
    assert inner.messages.sent[0]["model"] == "claude-haiku-5-5"
    assert rec.recording.totals()["calls"] == 1
