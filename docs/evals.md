# Agent evals

How do I know the agents actually work, and whether the cheap model would do? The evals answer
that with numbers: about 50 questions the owner might text, run through the real
Manager → specialist → tools path, and graded automatically. (The live bot uses the same number check as a guard; see below.)

## What runs

- **A made-up world** (`backend/app/evals/world.py`): 70 days of Apple Watch data and runs
  pushed through the real scoring pipeline (today is a run-down red day, with a half-marathon
  plan), plus three market scans, two alerted coins (RUN and DUD) and their paper trades. The
  owner's real data is never used, and the evals have their own throwaway database.
- **The questions** (`backend/app/evals/cases.py`): recovery, sleep, load, race predictions,
  zones, the plan, pain and illness, the Market Scout's scans, rug checks and paper trades,
  greetings, and tricky ones (a day with no data, a metric no tool has, a question for both
  specialists).
- **Two setups**, run on the same questions:
  - `production`: Haiku 5.5 routes, Sonnet 5.5 answers (what's deployed).
  - `all-haiku`: Haiku 5.5 everywhere (about 20× cheaper per token).

## How it's graded (`backend/app/evals/grade.py`)

| Check | Passes when |
| --- | --- |
| Route | the Manager asked the right specialist (or nobody, for "hey") |
| Tools | the specialist called the tools the question needs, and didn't rewrite the plan unasked |
| Grounded | every number in the final answer appears in a specialist's tool results (or the question), allowing for rounding. Small counts (0–10), dates and race names are skipped |
| Disclaimer | Market Scout answers end with "Not financial advice." |
| Answered | there is an answer, not an error or "ran out of steps" |

A case passes when every check that applies passes. The Manager's relay doesn't count as
evidence: if the Coach invents a number and the Manager repeats it, it's caught.

Each call is also recorded (`backend/app/evals/recorder.py`): model, tokens, cost at list
price, and seconds, so the report shows cost per answer and response times.

## The live guard

The grounded check also runs in production, on every agent's answer (`app/agents/grounding.py`,
called from the agent loop). If an answer has a number that no tool result, instruction or
the question backs up, the agent is sent back once to rewrite it with real numbers only. If
it still can't, the answer goes out with "(Couldn't verify: …)" rather than a silent made-up
number. The eval report counts these rewrites per setup ("Guard rewrites").

## Running it

It calls the real Claude API, so it costs money: roughly $1–2 for `production` over every
question, a few cents for `all-haiku`.

**From GitHub (nothing to install):**

1. Repository **Settings → Secrets and variables → Actions → New repository secret**:
   name `ANTHROPIC_API_KEY`, value your key (the same one Railway uses).
2. **Actions → Agent evals → Run workflow**. Keep the defaults, or name setups and cases.
3. When it finishes (about 20–30 minutes for both setups), the run's summary page shows the
   report; the `eval-results` artifact has `REPORT.md` and every answer in `results.json`.

**Locally:** `cd backend && ANTHROPIC_API_KEY=… python -m app.evals.run`
(`--setups production --cases recovery-today,paper` for a quick check).

## Limits, honestly

- Answers vary run to run, so a single run's pass rate moves by a few points. Compare setups
  on the same run, and rerun before trusting a small difference.
- The grounding check is a heuristic. It can miss a made-up number that happens to equal
  some other number in the tool results, and it skips small whole numbers.
- "Tools" checks what was called, not how well it was explained. Tone and helpfulness aren't
  scored.
