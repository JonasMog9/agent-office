# CLAUDE.md

Guidance for Claude Code (and humans) working in this repo.

## What this is

Agent Office: a cloud-hosted team of three AI agents (Manager, Health Coach, Market Scout) controlled from Telegram and shown live as pixel characters in a 2D office. **Read [PLAN.md](PLAN.md) first.** It holds the goal, the architecture, the Health Coach formulas, and the build phases with their checklists. Work one phase at a time, in order, and tick the PLAN.md boxes when a phase's "done when" condition is met.

## Stack

| Layer | Choice |
| --- | --- |
| Agents | Claude Agent SDK (Python). Haiku for the Manager, Sonnet for the Health Coach and Market Scout |
| API | FastAPI (async, WebSockets) on Python 3.12 |
| Database | Postgres via SQLAlchemy 2.x, migrations with Alembic |
| Chat | python-telegram-bot in webhook mode, mounted on the FastAPI app |
| Office | Phaser 3 + React + TypeScript (Vite), deployed to Vercel |
| Hosting | Railway (Docker) for backend, Postgres and cron jobs |
| Tooling | ruff (lint + format), pytest, GitHub Actions CI |

## Folder layout

Target layout (created in Phase 0's scaffold; keep to it as the code grows):

```
backend/
  app/
    main.py          FastAPI app, routes (/health, /ingest/health, /strava/webhook, /telegram, /ws/events)
    db/              SQLAlchemy models, session, Alembic migrations
    ingest/          iOS Shortcut payloads + Apple Health export.xml → daily_metrics; Strava → workouts
    metrics/         recovery, strain, sleep scores (pure functions)
    coach/           training load, zones, race predictor, plan generator (pure functions)
      ml/            scikit-learn race-time and fitness models: training script, saved model + metrics
    scout/           DexScreener / CoinGecko ingestion and token scoring
    agents/          Manager, Health Coach, Market Scout (Claude Agent SDK) + event bus
    telegram/        bot webhook handler and scheduled pushes
  tests/             pytest, mirrors app/
  Dockerfile
  railway.json     Railway build/deploy config (healthcheck on /health; migrations run at container start)
  alembic.ini
  pyproject.toml
frontend/            Vite + React + TS + Phaser office
docs/                how-tos: Railway setup, the iOS health-sync Shortcut, connecting Strava, Apple Health import
.github/workflows/   CI: ruff + pytest
.env.example         every env var the app reads, with placeholder values
PLAN.md
```

## Rules

- **Never commit secrets.** API keys, bot tokens, the ingest header secret, Strava client secret and refresh token, database URLs and Telegram IDs live in environment variables (Railway / Vercel settings, local `.env`). `.env` is gitignored; `.env.example` lists names with placeholder values only. If a secret is ever committed, rotate it, don't just delete the line.
- **Deterministic math, LLM for language.** Every score, prediction and plan adjustment is computed in Python. Agents call tools that return numbers and explain them; they never invent or estimate a number themselves.
- **Write tests for scoring code.** Everything in `metrics/`, `coach/` and `scout/` scoring gets pytest coverage with hand-made data, including missing days, outliers and short histories. Check race prediction against known VDOT tables.
- **Scoring functions are pure** and return the value plus a component breakdown (the "reasons"), so agents can explain them.
- **Market Scout is read-only.** No wallet, no exchange keys, no buy/sell actions. Every brief ends with a "not financial advice" line.
- **Telegram bot answers only the owner's user ID** (from an env var); reject everyone else. Likewise the Strava webhook only processes events for the owner's athlete ID.
- **Ingestion is idempotent.** The Shortcut resends the last 3 days every time, so `/ingest/health` upserts by date. Strava is the source of truth for workouts; Apple Health data covers daily wellness only, so nothing is double counted.
- **Every agent step emits an event** `{agent, status: idle|thinking|walking|working|talking, target, text}` to the event bus; the office animates from these.
- **Keep CI green.** Run `ruff check`, `ruff format --check` and `pytest` before pushing.
- Compare HRV only against the user's own baseline (Apple Watch reports SDNN, not RMSSD).
- **ML is evaluated, not assumed.** Any learned model ships with a reproducible training script, cross-validated metrics, and a comparison against the simple baseline it replaces. If it doesn't beat the baseline, say so and keep the baseline.
- **Keep the challenges log current.** When a real problem comes up (a bug in production, a wrong assumption, a tool or platform limitation, a design pivot), add a row to the Challenges log in PLAN.md in the same PR that fixes it: date, problem, how it was found, fix, lesson. Newest first. Only real events, never invented ones.
