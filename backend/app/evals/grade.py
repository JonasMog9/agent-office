"""Grading an agent run: did the Manager pick the right specialist, did the specialist call
the right tools, and is every number in the answer backed by what the model was given?
The number check lives in ``app/agents/grounding.py``, shared with the live agent loop."""

from dataclasses import dataclass, field

from app.agents.grounding import numbers, ungrounded

__all__ = ["Case", "Trace", "grade", "numbers", "ungrounded"]


@dataclass(frozen=True)
class Case:
    id: str
    question: str
    route: str  # "health_coach", "market_scout", "both", or "none" (the Manager answers)
    tools_any: tuple[str, ...] = ()  # at least one of these must be called
    tools_all: tuple[str, ...] = ()  # all of these must be called
    tools_never: tuple[str, ...] = ("adjust_plan",)  # none of these may be called
    mutates: bool = False  # changes the world (runs last)
    note: str = ""


@dataclass
class Trace:
    """What happened in one run, from the recorded API calls."""

    answer: str
    specialists: list[str] = field(default_factory=list)  # who the Manager asked
    tools: list[str] = field(default_factory=list)  # the specialists' tool calls
    tool_results: list[str] = field(default_factory=list)
    instructions: list[str] = field(default_factory=list)  # system prompts, tool definitions
    error: str | None = None


NOT_ADVICE = "Not financial advice."
FAILED_ANSWERS = ("(no answer)", "ran out of steps", "I can't help with that one.")


def grade(case: Case, trace: Trace) -> dict:
    """Each check as True/False (None when it doesn't apply), and whether the case passed."""
    if trace.error:
        return {"passed": False, "error": trace.error, "checks": {}, "ungrounded": []}
    expected = {
        "none": [],
        "both": ["health_coach", "market_scout"],
    }.get(case.route, [case.route])
    called = set(trace.tools)
    bad_numbers = ungrounded(trace.answer, trace.tool_results, case.question, trace.instructions)
    checks = {
        "route": sorted(set(trace.specialists)) == expected,
        "tools": (not case.tools_any or bool(called & set(case.tools_any)))
        and set(case.tools_all) <= called
        and not (called & set(case.tools_never)),
        "grounded": not bad_numbers,
        "disclaimer": NOT_ADVICE in trace.answer if "market_scout" in expected else None,
        "answered": bool(trace.answer.strip())
        and not any(f in trace.answer for f in FAILED_ANSWERS),
    }
    return {
        "passed": all(v for v in checks.values() if v is not None),
        "checks": checks,
        "ungrounded": bad_numbers,
        "error": None,
    }
