"""Run the agent evals against the real Claude API.

    python -m app.evals.run                       # both setups, every case
    python -m app.evals.run --setups production --cases recovery-today,paper

It always uses its own throwaway SQLite database (never the app's), needs ANTHROPIC_API_KEY,
and costs real money: about $1–2 for the production setup over every case, a few cents for
all-haiku. Writes results.json and REPORT.md to --out.
"""

import argparse
import json
import os
import sys
import tempfile
from datetime import UTC, datetime
from pathlib import Path


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--setups", default="production,all-haiku")
    p.add_argument("--cases", default="all", help="comma-separated case ids, or 'all'")
    p.add_argument("--out", default="eval-results")
    args = p.parse_args(argv)

    # Before any app import: the evals get their own database, and no background scans.
    tmp = tempfile.mkdtemp(prefix="agent-office-evals-")
    os.environ["DATABASE_URL"] = f"sqlite:///{tmp}/evals.db"
    os.environ["SCOUT_ENABLED"] = "false"

    import anthropic

    from app.evals.cases import CASES
    from app.evals.runner import SETUPS, report, run_setup

    setups = [s.strip() for s in args.setups.split(",") if s.strip()]
    unknown = [s for s in setups if s not in SETUPS]
    if unknown:
        p.error(f"unknown setup(s) {unknown}; choose from {sorted(SETUPS)}")
    ids = None if args.cases == "all" else {c.strip() for c in args.cases.split(",")}
    cases = [c for c in CASES if ids is None or c.id in ids]
    if not cases:
        p.error("no cases match --cases")

    client = anthropic.Anthropic(max_retries=5)
    runs = [run_setup(client, s, cases, lambda line: print(line, flush=True)) for s in setups]
    when = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps({"run_at": when, "runs": runs}, indent=2))
    md = report(runs, when)
    (out / "REPORT.md").write_text(md)
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(summary, "a") as f:
            f.write(md)
    print(md)
    return 0


if __name__ == "__main__":
    sys.exit(main())
