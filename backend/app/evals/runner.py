"""Run the eval cases under one or more model setups and summarise them.

Each setup gets a fresh eval world, then every case goes through the real Manager →
specialist → tools path (``team.ask_manager``) with a ``RecordingClient``, and is graded.
"""

import statistics
import time
from collections.abc import Callable, Iterable
from typing import Any

from app.agents.events import EventBus
from app.agents.team import ask_manager
from app.db.session import Base, SessionLocal, engine
from app.evals import world
from app.evals.grade import Case, Trace, grade
from app.evals.recorder import RecordingClient
from app.scout.screen import Rules

HAIKU, SONNET = "claude-haiku-5-5", "claude-sonnet-5-5"
SETUPS: dict[str, dict[str, str]] = {
    # What runs in production: Haiku routes, Sonnet answers.
    "production": {"manager": HAIKU, "health_coach": SONNET, "market_scout": SONNET},
    # The cheap option: Haiku for everything.
    "all-haiku": {"manager": HAIKU, "health_coach": HAIKU, "market_scout": HAIKU},
}
SPECIALIST = {"ask_health_coach": "health_coach", "ask_market_scout": "market_scout"}


def fresh_world() -> world.EvalMarket:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with SessionLocal() as session:
        return world.build(session)


def run_case(client: Any, case: Case, models: dict[str, str], market: Any) -> dict:
    rec = RecordingClient(client, models)
    start = time.monotonic()
    answer, error = "", None
    bus = EventBus()
    try:
        result = ask_manager(
            rec,
            SessionLocal,
            case.question,
            bus,
            scout_rules=Rules(),
            scout_src_factory=lambda: market,
        )
        answer = result.text
    except Exception as exc:  # noqa: BLE001  (one failed case doesn't stop the run)
        error = f"{type(exc).__name__}: {exc}"[:300]
    r = rec.recording
    trace = Trace(
        answer=answer,
        specialists=[SPECIALIST[t] for t in r.tools_by("manager") if t in SPECIALIST],
        tools=r.tools_by("health_coach") + r.tools_by("market_scout"),
        tool_results=r.results_for(("health_coach", "market_scout")),
        instructions=[t for texts in r.instructions.values() for t in texts],
        error=error,
    )
    return {
        "id": case.id,
        "question": case.question,
        "answer": answer,
        "specialists": trace.specialists,
        "tools": trace.tools,
        "seconds": round(time.monotonic() - start, 2),
        "rewrites": sum(1 for e in bus.recent() if e.target == "fact_check"),
        **{k: round(v, 6) if isinstance(v, float) else v for k, v in r.totals().items()},
        **grade(case, trace),
    }


def run_setup(
    client: Any,
    name: str,
    cases: Iterable[Case],
    log: Callable[[str], None] = print,
) -> dict:
    models = SETUPS[name]
    market = fresh_world()
    results = []
    for case in sorted(cases, key=lambda c: c.mutates):  # world-changing cases go last
        r = run_case(client, case, models, market)
        log(f"[{name}] {case.id}: {'pass' if r['passed'] else 'FAIL'} ({r['seconds']} s)")
        results.append(r)
    return {"setup": name, "models": models, "summary": summarise(results), "cases": results}


def summarise(results: list[dict]) -> dict:
    n = len(results)
    if not n:
        return {"cases": 0}
    checks: dict[str, list[bool]] = {}
    for r in results:
        for k, v in r["checks"].items():
            if v is not None:
                checks.setdefault(k, []).append(v)
    secs = sorted(r["seconds"] for r in results)
    return {
        "cases": n,
        "passed": sum(r["passed"] for r in results),
        "pass_rate_pct": round(100 * sum(r["passed"] for r in results) / n, 1),
        "check_pass_rate_pct": {k: round(100 * sum(v) / len(v), 1) for k, v in checks.items()},
        "errors": sum(1 for r in results if r["error"]),
        "total_cost_usd": round(sum(r.get("cost_usd", 0) for r in results), 4),
        "cost_per_answer_usd": round(sum(r.get("cost_usd", 0) for r in results) / n, 5),
        "median_seconds": round(statistics.median(secs), 1),
        "p90_seconds": round(secs[min(n - 1, int(0.9 * n))], 1),
        "mean_output_tokens": round(sum(r.get("output_tokens", 0) for r in results) / n),
        "guard_rewrites": sum(r.get("rewrites", 0) for r in results),
    }


def report(runs: list[dict], when: str) -> str:
    """The Markdown report: setups side by side, then every failure with its reasons."""
    lines = [
        "# Agent evals",
        "",
        f"Run {when}: {runs[0]['summary']['cases'] if runs else 0} questions against the "
        "made-up eval world (`app/evals/world.py`), graded automatically "
        "(`app/evals/grade.py`). See docs/evals.md.",
        "",
        "| Setup | Models (manager / coach / scout) | Passed | Route | Tools | Grounded | "
        "Disclaimer | Guard rewrites | Cost per answer | Median time | p90 time |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for run in runs:
        s, m, c = run["summary"], run["models"], run["summary"].get("check_pass_rate_pct", {})
        short = {k: v.replace("claude-", "").replace("-5-5", " 5.5") for k, v in m.items()}
        lines.append(
            f"| {run['setup']} | {short['manager']} / {short['health_coach']} / "
            f"{short['market_scout']} | {s['passed']}/{s['cases']} ({s['pass_rate_pct']}%) | "
            f"{c.get('route', '–')}% | {c.get('tools', '–')}% | {c.get('grounded', '–')}% | "
            f"{c.get('disclaimer', '–')}% | {s.get('guard_rewrites', 0)} | "
            f"{s['cost_per_answer_usd'] * 100:.2f}¢ | "
            f"{s['median_seconds']} s | {s['p90_seconds']} s |"
        )
    for run in runs:
        failed = [r for r in run["cases"] if not r["passed"]]
        lines += ["", f"## {run['setup']}: {len(failed)} failed", ""]
        for r in failed:
            why = r["error"] or ", ".join(k for k, v in r["checks"].items() if v is False)
            extra = f" Unbacked numbers: {', '.join(r['ungrounded'])}." if r["ungrounded"] else ""
            tools = ", ".join(r["tools"]) or "none"
            lines.append(
                f"- **{r['id']}** ({why}). Asked {', '.join(r['specialists']) or 'nobody'}, "
                f"tools: {tools}.{extra}"
            )
            snippet = " ".join(r["answer"].split())[:240]
            if snippet:
                lines.append(f"  > {snippet}")
    return "\n".join(lines) + "\n"
