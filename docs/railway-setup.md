# Deploying the backend on Railway (Phase 1)

One-time setup in the Railway dashboard. After this, every merge to `main` redeploys automatically.

What the repo already does for you:

- `backend/Dockerfile` builds the app and listens on Railway's `$PORT`.
- `backend/railway.json` runs `alembic upgrade head` before each deploy (database migrations) and only switches traffic once `/health` answers.
- `DATABASE_URL` from Railway's Postgres works as is; the app adds the driver name itself.

## 1. Create the project and database

1. In Railway, click **New Project → Deploy from GitHub repo** and pick `JonasMog9/agent-office`. If Railway can't see the repo, click **Configure GitHub App** and give it access.
2. The first build will fail, because the code lives in `backend/`, not the repo root. That's expected; the next step fixes it.
3. In the same project, click **Create → Database → PostgreSQL**. Railway names it `Postgres`.

## 2. Point the service at `backend/`

Open the backend service (the one named after the repo) → **Settings**:

| Setting | Value |
| --- | --- |
| Source → Root Directory | `/backend` |
| Config-as-code → Railway Config File | `/backend/railway.json` (the full path from the repo root, not relative to the root directory) |
| Source → Branch | `main` |

## 3. Add the variables

Backend service → **Variables** → **Raw Editor**, paste this, then replace the placeholders with your real values. Type secrets only into Railway, never into a chat or a file in the repo.

```
DATABASE_URL=${{Postgres.DATABASE_URL}}
PORT=8000
ANTHROPIC_API_KEY=
TELEGRAM_BOT_TOKEN=
TELEGRAM_OWNER_USER_ID=
TELEGRAM_WEBHOOK_SECRET=
INGEST_SECRET=
STRAVA_CLIENT_ID=
STRAVA_CLIENT_SECRET=
STRAVA_ATHLETE_ID=
STRAVA_WEBHOOK_VERIFY_TOKEN=
```

- `${{Postgres.DATABASE_URL}}` is typed literally: Railway swaps in the database's private URL.
- `PORT=8000` pins the port the app listens on, so the domain in step 4 knows where to send traffic.
- `TELEGRAM_OWNER_USER_ID`: message [@userinfobot](https://t.me/userinfobot) on Telegram; it replies with your numeric ID.
- `TELEGRAM_WEBHOOK_SECRET`, `INGEST_SECRET`, `STRAVA_WEBHOOK_VERIFY_TOKEN`: make up long random strings, e.g. from a password manager. Each one is a password that only the backend and the sender know.
- `STRAVA_ATHLETE_ID`: the number in your Strava profile URL (`strava.com/athletes/<id>`).
- `STRAVA_REFRESH_TOKEN` is left out on purpose. Phase 2 adds a one-time login that gets it, and stores later rotations in the database, because Strava issues a new refresh token from time to time.
- Nothing in Phase 1 uses the Anthropic, Telegram or Strava values yet, so you can leave any you don't have handy empty for now and fill them in before their phase.

Click **Deploy** (or **Update Variables**) to apply.

## 4. Give it a public URL

Backend service → **Settings → Networking → Generate Domain**. When it asks which port, enter `8000`.

## 5. Check it

Open `https://<your-domain>/health`. You should see:

```json
{"status": "ok", "database": "ok"}
```

If you see `"database": "unreachable"` (HTTP 503), the `DATABASE_URL` variable is missing or wrong. If the page doesn't load at all, open the deployment's **Deploy Logs** and paste the error into the Claude Code chat (logs don't contain your secrets, but check before pasting).

That's Phase 1's "done when". Tick the boxes in `PLAN.md`, or ask Claude Code to.
