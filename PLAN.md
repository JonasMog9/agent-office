# Agent Office build plan

Source of truth for what we're building and in what order. Tick boxes as phases land. This file is the only copy that's kept up to date: change the plan here, through a pull request. (An older copy in Claude Docs is no longer maintained.)

## Goal

Build a cloud-hosted team of three AI agents you control from Telegram, shown live as pixel characters in a 2D office. Then record a 60–90 second demo video and run it for about a month.

The finished demo: you text "How ready am I to train today?". The Manager character stands up, walks to the Health Coach's desk with a speech bubble, the coach types, and your phone buzzes with a readiness score and today's workout call. The Market Scout posts its daily brief in the same office.

The team:

- **Manager**: reads your Telegram message, decides who handles it, delegates, and replies to you.
- **Health Coach**: a Whoop/Garmin-style running coach. It tracks recovery, strain, sleep and training load, predicts your race times, and adapts your marathon plan daily. It computes every number in Python and uses Claude to explain them.
- **Market Scout** (optional third agent, see below): scans trending meme coins once a day, flags risk signals, and writes a short brief. It never trades.

Profit isn't the goal. The goal is a project a hiring manager can watch in 90 seconds and then dig into on GitHub.

## Architecture and stack

One Python backend on Railway runs all three agents. Your phone pushes daily health data through a free iOS Shortcut and chats over Telegram, Strava sends each run to the backend as soon as it syncs, and the pixel office is a separate web page that listens to agent events.

```
 iPhone                        Railway (one Python backend)                    Browser
 ┌──────────────────────┐      ┌─────────────────────────────────────────┐
 │ iOS Shortcut         │─POST▶│ FastAPI  /ingest/health                 │
 │ (on Instagram open)  │      │                                         │     ┌──────────────────┐
 │ Telegram app         │◀────▶│          /telegram (webhook)            │     │ Pixel office     │
 └──────────────────────┘      │          /ws/events ─────────────────────│────▶│ Phaser 3 + React │
 ┌──────────────────────┐      │                                         │     │ (Vercel)         │
 │ Strava               │─POST▶│          /strava/webhook                │     └──────────────────┘
 └──────────────────────┘      │                                         │
                               │ Manager ─▶ Health Coach / Market Scout  │
                               │ (Claude Agent SDK)   │ event bus        │
                               │ Postgres: health · tokens · events      │
                               └─────────────────────────────────────────┘
```

Every agent step is saved as an event, and the office replays those events as animations. That's why the video can show the Manager walking to the Coach at the exact moment the delegation happens.

| Layer | Choice | Why |
| --- | --- | --- |
| Agents | Claude Agent SDK (Python) | Native subagents and hooks, no extra framework to learn |
| API | FastAPI | Async, WebSockets built in, standard on resumes |
| Database | Postgres | Health history, token snapshots, event log |
| Chat | python-telegram-bot (webhook mode) | Doesn't need to poll, so it works on cheap hosting |
| Office | Phaser 3 + React (Vite) on Vercel | A real 2D game engine, free hosting |
| Hosting | Railway (Docker) | Simple deploys from GitHub, cron jobs, Postgres included |

## Should you add a meme coin / NFT scanner?

Yes, but only for meme coins, and only as a read-only scout that never trades. Add it as the third agent instead of the Etsy bot.

Why it beats Etsy for this goal:

- **It's a real data-engineering job.** A daily ingestion job against public market data, snapshots in Postgres, computed features (24h volume change, liquidity, token age, buy/sell ratio), and a score. Same skill set as the health pipeline, applied to a second domain.
- **It's free and needs no approvals.** DexScreener and CoinGecko both have free public APIs. Etsy needs approved API access, paid listings, and Printify setup.
- **It looks great on video.** The Scout walks to a wall of charts every morning, and the brief lands in Telegram.
- **One month of history is enough.** End with a short "what the Scout flagged vs. what happened" analysis, a strong closing slide for the README.

Rules for it:

- No wallet, no exchange keys, no buy/sell actions. It reports and nothing else.
- Score tokens with code (rules or a simple model), and let Claude write the summary.
- Put a "not financial advice" line on every brief.
- Skip NFTs. The NFT market has much thinner volume and worse data access, so meme coins give you more to work with.

## Health Coach: a Whoop/Garmin-style running coach

The Health Coach covers what Whoop and Garmin give you (recovery, strain, sleep, training load, race predictions), plus an adaptive marathon plan and a coach you can chat with. Every number is computed in Python from your own data, and Claude explains it and answers your questions. The scores are approximations of the commercial ones: Whoop's and Garmin's exact formulas aren't public.

| Feature | What you get | Data it uses (source) | How it's computed |
| --- | --- | --- | --- |
| Recovery (0–100%) | Green, yellow, or red each morning | HRV (SDNN), resting HR, respiratory rate, wrist temperature (Series 8 and later only), sleep (Shortcut). The score reweights over whichever inputs exist that day | z-scores vs. your 60-day baseline, weighted into one score |
| Strain (0–21) | How hard today was, all activity included | Workout heart rate streams (Strava), plus daily active energy (Shortcut) | Daily TRIMP, mapped onto a log 0–21 scale like Whoop's |
| Sleep coach | Sleep need tonight, sleep debt, consistency | Sleep stages, in-bed times (Shortcut) | Baseline need + extra for strain + debt from the last 7 nights |
| Training load and form | Fitness, fatigue and form trend, plus an overtraining flag | Workouts: duration, HR, distance (Strava) | CTL (42-day) and ATL (7-day) averages of TRIMP. Form = CTL − ATL. ACWR = 7-day / 28-day load |
| HR and pace zones | Your personal zones | Max HR, resting HR (Shortcut), recent runs (Strava) | Karvonen (heart-rate reserve) zones, and pace zones from your VDOT |
| Race time predictions | 5K, 10K, half and marathon estimates, with a range and a trend line | Best recent efforts and weekly mileage (Strava), VO2max estimate (Shortcut) | Daniels VDOT from your best efforts, Riegel scaling, and Apple's VO2max as a cross-check. Marathon adjusted down if your mileage is low |
| Adaptive training plan | A plan to a goal race and date that reshuffles daily | Everything above | Base, build, peak and taper blocks. Weekly mileage up ≤10%. Hard days swapped for easy ones when recovery is red |
| Running form | Trends and alerts on running form | Cadence and power streams (Strava); ground contact time, vertical oscillation, stride length (Shortcut) | Rolling averages per pace band. Flags sudden changes |
| Early warnings | "You might be getting sick" or "injury risk is up" | Resting HR, HRV, temperature, ACWR | Rules, e.g. RHR +5 bpm and HRV down 20% for 2 days, or ACWR above 1.5 |
| Weekly report | A Sunday summary in Telegram and on the stats page | All of it | Claude writes it from the computed metrics |

The two core formulas:

```math
T_2 = T_1 \times \left(\frac{D_2}{D_1}\right)^{1.06}
```

```math
\mathrm{CTL}_t = \mathrm{CTL}_{t-1} + \frac{\mathrm{TRIMP}_t - \mathrm{CTL}_{t-1}}{42}
```

The first is Riegel's race predictor: a time T1 over distance D1 predicts a time T2 over distance D2. ATL works the same way as CTL with 7 instead of 42.

Things to know about the data:

- Apple Watch records HRV as SDNN, while Whoop uses RMSSD. Compare against your own baseline only, never against Whoop's numbers.
- Two free sources, each owning different data:
  - **iOS Shortcut** → `POST /ingest/health`: daily wellness (HRV, resting HR, respiratory rate, wrist temperature, sleep, active energy, VO2max, Apple's running-form metrics). A personal automation runs it **when you open Instagram**, because iOS locks Health data while the phone is locked and an app opening means it's unlocked. The shortcut sends only once a day and always sends the **last 3 days**, so a missed day fills itself in. The backend upserts by date, so repeats never duplicate.
  - **Strava API** → `/strava/webhook`: every run (and other HR workouts) with second-by-second heart rate, pace, cadence and splits. Strava calls the backend when an activity syncs from the watch, so no phone step is needed. It's the source of truth for workouts; the Shortcut doesn't send them, which avoids double counting.
- **Backfill on day one.** Recovery needs a 60-day baseline. Instead of waiting weeks, import Apple Health's full export once (Health app → profile → Export All Health Data → `export.xml`) and pull past activities from the Strava API.
- **Keep the phone passcode on.** It's what encrypts Health data on the device; the Instagram trigger already solves the locked-phone problem.
- Strava's API terms (tightened in late 2024) limit how Strava data can be shown to others and used with AI. Using your own data for your own coach is the normal case, but re-read the terms before putting Strava-derived charts in the public demo or stats page.
- Race predictions need at least one hard effort (a race or time trial) in the last 6–8 weeks to be useful. Before there is one, the coach falls back to the VO2max estimate and says it's less certain.
- Show how good the predictions are: log every prediction and compare it with real race results. That's a great chart for the README.

What to say to it in Telegram: "How recovered am I?", "What should I run today?", "Predict my marathon", "Build me a plan for a sub-3:30 on April 12", "Why was my strain so high yesterday?".

## Build phases

There are seven phases, and each ends with something working in the cloud. Do them in order: every phase builds on the one before.

### Phase 0: Accounts and repo

- [x] Create a public GitHub repo called `agent-office`.
- [x] Sign up for Railway (or Fly.io), get an Anthropic API key, and create a Telegram bot with @BotFather.
- [x] Install the Strava app, connect it to Apple Health so watch workouts sync to Strava automatically, and create a Strava API application (free) at strava.com/settings/api.
- [x] Make sure the Shortcuts app is on your iPhone (built in, free). The health-sync shortcut itself is built in Phase 2, once the endpoint exists.
- [x] Write `CLAUDE.md`: the stack, the folder layout, "never commit secrets", and "write tests for scoring code".

Claude Code prompt: `Scaffold a monorepo with backend/ (Python 3.12, FastAPI, SQLAlchemy, pytest) and frontend/ (Vite + React + TypeScript). Add a Dockerfile for the backend, a .env.example, and a GitHub Actions workflow that runs ruff and pytest.`

Done when CI is green on GitHub.

### Phase 1: Cloud skeleton

- [x] Deploy the FastAPI backend and a Postgres database on Railway, following [docs/railway-setup.md](docs/railway-setup.md).
- [x] Add a `/health` endpoint (checks the database too) and set the secrets as environment variables.

Claude Code prompt: `Add a railway.json and wire DATABASE_URL into SQLAlchemy with Alembic migrations. Add a /health endpoint.`

Done when the live URL returns OK. ✅ Live at https://agent-office-production-d0e3.up.railway.app/health

### Phase 2: Health data pipeline (the resume core)

- [x] Add a `POST /ingest/health` endpoint protected by a secret header (`X-Ingest-Secret`). It accepts our own simple JSON format (one text field per metric, one `start|end|value|unit` line per sample), stores each sample once in `health_samples` and rebuilds the affected `daily_metrics` days, so resending the last 3 days is safe.
- [ ] Build the iOS Shortcut that sends the last 3 days of HRV, resting HR, respiratory rate, wrist temperature, sleep, active energy, VO2max and running-form metrics to the endpoint. Add a personal automation: **When Instagram is opened → run it, with "Ask Before Running" off**, and skip if it already sent today. Step-by-step build: [docs/health-shortcut.md](docs/health-shortcut.md).
- [ ] Add Strava: OAuth for your account (refresh token stored as a secret), a `/strava/webhook` route (subscription check plus activity events, accepting only your athlete ID), access tokens refreshed as they expire (every 6 hours), and each new refresh token Strava rotates in saved to the database, since the env var only holds the first one, and fetching each new activity's summary and HR, pace and cadence streams into `workouts`.
- [ ] Backfill: a one-off script that imports Apple Health's `export.xml` into `daily_metrics`, and one that pulls your past Strava activities, so the 60-day baselines exist from day one.
- [ ] Store raw payloads, then parse them into a clean `daily_metrics` table (HRV, resting heart rate, respiratory rate, temperature, sleep, active energy, VO2max) and a `workouts` table (from Strava).
- [ ] Write the recovery, strain and sleep scores as plain Python functions (see the Health Coach section). Each one returns a number plus the reasons behind it.
- [ ] Unit-test every score with hand-made data, including missing days and outliers.

Claude Code prompt: `/plan Build the health ingestion endpoint (our own JSON format from an iOS Shortcut, upsert by date), Strava OAuth plus a webhook that pulls new activities and their HR streams, and backfill scripts for Apple Health's export.xml and past Strava activities. Add a metrics package. Store raw JSON, normalize into daily_metrics and workouts tables, and implement recovery (z-scores vs. 60-day baselines), strain (TRIMP mapped to 0-21) and sleep need and debt, each returning a score with a component breakdown. Include pytest cases for missing days and outliers.`

Done when the Instagram-triggered shortcut and Strava both land real data every day for a week, the backfill fills the last 60+ days, and the recovery, strain and sleep numbers look sane.

### Phase 2b: Running coach engine

- [ ] Training load: daily TRIMP, CTL/ATL/form, and ACWR, with overtraining and injury-risk flags.
- [ ] HR zones (Karvonen) and pace zones from VDOT.
- [ ] Race predictor: VDOT from best recent efforts, Riegel scaling, the VO2max cross-check, and a mileage adjustment for the marathon. Log every prediction to a `predictions` table.
- [ ] ML race predictor (scikit-learn), next to the formula one:
  - Train a regression model (start with ridge and gradient boosting) on a public dataset of many runners' training features (weekly mileage, long runs, recent race times) and marathon results. Your own handful of races is far too little to train on.
  - Evaluate it with k-fold cross-validation against the Riegel and VDOT baselines on the same folds, and report the error (MAE in minutes). If the model doesn't beat the formulas, keep the formulas and say so: an honest negative result is still a result.
  - Give a range, not a point, using quantile regression or the cross-validation error spread.
  - Apply it to your own features and show it beside the formula estimate. Every prediction goes into the `predictions` table, so it can be compared with real races later.
  - Lives in `coach/ml/` with a notebook-free, reproducible training script, and the model file and its metrics saved. Tests cover feature building on hand-made data.
- [ ] Personal fitness model: a regression of pace on heart rate (plus grade and temperature when available) over your Strava run segments, refit over a rolling window. The trend of "pace at HR 150" is your aerobic fitness curve: hundreds of data points from your own runs, so ML on your own data is meaningful here.
- [ ] Plan generator: goal race + date → base, build, peak and taper weeks. Each morning it adjusts the day's workout using recovery and ACWR.
- [ ] Running form trends and early-warning rules (possible illness, injury risk).

Claude Code prompt: `/plan Add a coach package: TRIMP-based CTL/ATL/TSB and ACWR, Karvonen HR zones, a race predictor combining Daniels VDOT, Riegel and the Apple VO2max estimate with a low-mileage marathon adjustment, and a periodized plan generator that adapts the next workout to recovery. Pure functions with pytest tests against known VDOT tables. Then add a scikit-learn race predictor trained on a public runners dataset, cross-validated against the Riegel/VDOT baselines, plus a pace-vs-HR fitness model fit on my Strava segments.`

Done when "Predict my marathon" gives a sensible range (formula and ML side by side, with the ML model's cross-validated error against the baselines written up), and a 12-week plan generates and adapts to a red recovery day.

### Phase 3: Agents (Claude Agent SDK)

- [ ] Health Coach agent with tools `get_recovery, get_strain, get_sleep, get_training_load, predict_race, get_plan` and `adjust_plan`. It explains the numbers, prescribes today's run, and answers coaching questions, but it never invents a number.
- [ ] Manager agent with one tool per worker (`ask_health_coach`, `ask_market_scout`). Use Haiku for the Manager and Sonnet for the Coach.
- [ ] Every agent step writes an event: `{agent, status: idle|thinking|walking|working|talking, target, text}`.

Claude Code prompt: `Using the Claude Agent SDK, create a Manager agent that delegates to a Health Coach subagent via tools. Emit an event to an in-process event bus on every agent start, tool call, handoff and finish.`

Done when a test script asks the Manager a question and gets a correct answer plus a clean event log.

### Phase 4: Telegram manager

- [ ] Use python-telegram-bot in webhook mode on the same FastAPI app. Only answer your own Telegram user ID.
- [ ] Add a 7am scheduled push of the readiness summary (Railway cron or APScheduler).

Claude Code prompt: `Add a Telegram webhook route using python-telegram-bot. Messages from my chat ID go to the Manager agent; the reply goes back to Telegram. Reject all other users.`

Done when you text the bot from your phone and get your score back.

### Phase 5: The pixel office

- [ ] Stream the event bus to the browser over a WebSocket (`/ws/events`).
- [ ] Build the office: either adapt pixel-agents (its core is agent-agnostic) or build a small Phaser 3 scene with a free tileset and three characters. Start with Phaser: you control everything and it's easier to explain in interviews.
- [ ] Map each event to an animation: walk to a desk, type, show a speech bubble with the message text, go idle.
- [ ] Deploy the frontend to Vercel.

Claude Code prompt: `Build a Phaser 3 scene in frontend/ with an office tilemap and three characters (Manager, Health Coach, Market Scout). Subscribe to /ws/events and drive walk, type, talk and idle animations from the event status. Show speech bubbles with the event text.`

Done when a Telegram message visibly plays out on the office page.

### Phase 6: Market Scout

- [ ] Run a daily job that pulls trending tokens from DexScreener and CoinGecko, snapshots them to Postgres, and computes risk and momentum features.
- [ ] The Scout agent turns the top flags into a 5-line brief. The Manager posts it to Telegram and the office shows the Scout at the chart wall.

Done when a week of daily briefs has landed.

### Phase 7: Polish and ship

- [ ] Write a README with a GIF, an architecture diagram, how the readiness score works, and costs.
- [ ] Add a simple stats page: a 30-day readiness chart, plus the Scout's flags vs. what happened.
- [ ] Record the demo video (script below), and post it on LinkedIn with the repo link.

## Challenges log

Problems hit while building this, how they were found, and what fixed them, newest first. This is the "tell me about a problem you ran into" list for interviews. Claude Code adds a row whenever a real problem comes up; see CLAUDE.md.

| Date | Problem | How it showed up / was found | Fix | Lesson |
| --- | --- | --- | --- | --- |
| 2026-10-08 | Database tables never created in production | The first real Shortcut upload got a bare `Internal Server Error`. There was no way to see why from the phone, and logs were in another tool. | First made failures visible: the endpoint now returns the error type and message to the authenticated caller, and `/health` reports the database's migration version. That showed `UndefinedTable` and `"migration": "none"`: Railway had silently never run the pre-deploy migration step. Moved migrations into the container's start command, which is safe to repeat. | Make failures observable before guessing. Don't depend on a platform feature you can't see running; verify deploy steps from the outside. |
| 2026-10-08 | `daily_metrics.updated_at` never changed after the first upload | Reading the production table after several Shortcut runs: every row's `updated_at` was the time of the first successful upload, although values had been recomputed since. | SQLAlchemy's `onupdate` default only fires for ORM/Core UPDATEs, not for `INSERT ... ON CONFLICT DO UPDATE`. Set `updated_at = now()` explicitly in the upsert, with a test that backdates a row and re-posts. | Upserts bypass ORM conveniences; test the bookkeeping columns, not just the values. |
| 2026-10-08 | Dates came out in the wrong format from the second Shortcut block | The resting-HR upload came back with every line skipped (`expected start\|end\|value[\|unit], got 1 fields`). The skipped-lines report showed dates like `2026-10-05, 12:00 PM`, several per line. | A new Format Date action defaults to "Short", which overrides the date token's own ISO 8601 setting; with the whole sample as input it also printed several dates. Dropped Format Date and set ISO 8601 on the date tokens inside the Text action. The server rejected the bad lines instead of storing wrong dates, and named them in its reply, which made the cause visible from the phone. | Validate input strictly and echo back what was rejected; the client's defaults are not your defaults. |
| 2026-10-08 | Building the iOS Shortcut | Actions renamed between iOS versions ("Show Result" became "Show Content"). Copied actions stayed linked to the original block's variables, and a variable picked as the whole sample instead of its value. | Chose a payload format a Shortcut can build with plain text (`start\|end\|value\|unit` lines per metric, not nested JSON). Built and tested one metric end to end before copying the block. Rewrote the guide from real screenshots. | Design the API around the client's limits, and test one path end to end before scaling it out. |
| 2026-10-08 | Two AI chats editing the same plan | A second chat opened a PR from an outdated view of the plan; it was declined. | Made `PLAN.md` in the repo the single source of truth, changed only through pull requests from one working session. | One source of truth, changes through review. |
| 2026-10-08 | Messy health data | Designing ingestion surfaced several hazards: the iPhone and Watch both record the same night of sleep; temperatures arrive in °F or °C and lengths in ft or m; UTC dates put late-evening readings on the wrong day; and the Shortcut's rolling 3-day window cuts the oldest day in half. | Sleep is merged as a union of time intervals. Units are normalized, and an unknown unit is rejected rather than stored wrong. Each reading uses the phone's local date, with sleep counted toward the morning it ends. Every raw sample is stored once, and each day is recomputed from all samples, so a partial resend can't overwrite fuller data. Each case has a test. | Store raw facts and derive summaries; never let the latest upload overwrite history. |
| 2026-10-08 | The data source needed a paid app | The plan relied on Health Auto Export's paid tier for automatic uploads. | Replaced it with a free iOS Shortcut (daily wellness data) plus the Strava API (workouts). The Shortcut runs when Instagram opens, because iOS only allows Health reads while the phone is unlocked, and resends 3 days so missed days fill themselves in. | Constraints drive design: a free path existed but needed idempotent ingestion to be reliable. |
| 2026-10-08 | Deploying a monorepo on Railway | The backend lives in `backend/`, but Railway builds from the repo root, and Railway's docs and forum answers disagreed on whether the config-file path is relative to the root directory. | Set the service's root directory and the config-file path; wrote it up step by step in `docs/railway-setup.md`. | Write down the setup the moment it works. |

## Demo video script (about 75 seconds)

Record a split screen: your phone (screen recording) on the left and the office in the browser on the right.

1. **0–5s, hook.** The office is idle. Caption: "My AI team runs in the cloud. I manage it from Telegram."
2. **5–25s, the ask.** You text "How ready am I to train today?". The Manager stands up and walks to the Health Coach with a speech bubble.
3. **25–40s, the work.** The Coach types. The bubble shows "HRV 12% below baseline, 6h10m sleep". Your phone buzzes: "Recovery 58% (yellow). Swapping today's intervals for an easy 40 min in Zone 2. Marathon estimate: 3:28–3:36."
4. **40–55s, the second agent.** Cut to the morning: the Scout walks to the chart wall and the daily meme coin brief lands in Telegram.
5. **55–75s, under the hood.** Show the architecture diagram, the 30-day readiness chart, and the GitHub repo. Caption the stack: "FastAPI · Postgres · Claude Agent SDK · Telegram · Phaser · Railway".

Tips: record with real data, keep captions on screen (most people watch muted), and end on the repo URL.

## Costs, timeline and resume framing

Expect roughly $7–10 for the month. These are approximate figures, so check current pricing when signing up.

| Item | Approx. cost / month | Notes |
| --- | --- | --- |
| Railway Hobby (backend + Postgres) | ~$5 | Fly.io is similar |
| Claude API | ~$2–5 | Haiku for routing, Sonnet for the Coach, a few calls a day |
| Vercel (frontend) | $0 | Free hobby tier |
| iOS Shortcuts, Strava API | $0 | Shortcuts is built into iOS; Strava's API is free for personal use |
| Telegram, DexScreener, CoinGecko | $0 | Free APIs |

**Timeline.** Part-time, plan on about 4–6 weeks to build, then the month of running and recording. Phases 2 and 5 are the biggest. Start collecting health data in Phase 2 as early as possible, because the baselines need a few weeks of history.

**Resume bullets (once it's built):**

- Built a cloud-hosted multi-agent system (Claude Agent SDK, FastAPI, Postgres on Railway) controlled through a Telegram bot, with a real-time Phaser visualizer streaming agent state over WebSockets.
- Designed a daily Apple Watch + Strava data pipeline (iOS Shortcut push, Strava webhooks and OAuth, historical backfill, normalization, rolling 7/28-day baselines) plus tested recovery, strain, training-load and race-prediction models that drive an adaptive marathon plan.
- Trained and cross-validated a scikit-learn marathon-time model on a public multi-runner dataset against Riegel and Daniels VDOT baselines (MAE reported honestly), and fit a personal pace-vs-heart-rate fitness model on Strava run segments.
- Built a market-data ingestion job and risk-scoring model for trending tokens. Evaluated 30 days of flags against outcomes.

Interviewers will ask why the LLM doesn't compute the score. "Deterministic math, LLM for language" is the answer that lands.
