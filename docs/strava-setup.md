# Connecting Strava (Phase 2)

One-time setup. After it, every activity that syncs to Strava lands in the `workouts` table within a few seconds, with heart rate, pace, cadence, altitude and power streams.

## 1. Check the settings

Strava (strava.com/settings/api → My API Application):

- **Authorization Callback Domain**: `agent-office-production-d0e3.up.railway.app` (no `https://`, no path).

Railway (backend service → Variables) must have:

| Variable | Value |
| --- | --- |
| `STRAVA_CLIENT_ID` | from the Strava API page |
| `STRAVA_CLIENT_SECRET` | from the Strava API page |
| `STRAVA_ATHLETE_ID` | the number in your profile URL, `strava.com/athletes/<id>` |
| `STRAVA_WEBHOOK_VERIFY_TOKEN` | any long random string you made up |

`STRAVA_REFRESH_TOKEN` isn't needed: the connect step below gets one and the app keeps it current in the database (Strava rotates it).

## 2. Connect

Open **https://agent-office-production-d0e3.up.railway.app/strava/connect** in a browser where you're logged into Strava.

1. Strava asks you to authorize **Agent Office Coach** (or whatever you named the app). Leave **View data about your activities** ticked, including private activities, and click **Authorize**.
2. You land back on a page saying **Strava connected ✅** with a webhook subscription number.

That one click does three things:

- **Stores your tokens.** Access tokens last 6 hours and are refreshed automatically.
- **Registers the webhook,** so Strava notifies the app about new, edited and deleted activities. Strava allows one per app, so reconnecting reuses it.
- **Starts importing your last 365 days** of activities in the background.

## 3. Watch the import

Open **https://agent-office-production-d0e3.up.railway.app/strava/status**:

```json
{"connected": true, "webhook_subscription": 123456,
 "backfill": {"status": "running", "imported": 42, "error": null},
 "workouts": 42, "latest_workout_day": "2026-10-03"}
```

Each activity costs two API calls (details + streams) and Strava allows 100 reads per 15 minutes, so about 50 activities per 15 minutes. A year of training takes roughly an hour. When it says `"done"`, it's finished.

| Status | Meaning |
| --- | --- |
| `running` | Importing. `last_progress_at` shows the last time an activity landed |
| `waiting for Strava rate limit until HH:MM UTC` | Normal: pausing until the next 15-minute window, then it continues by itself |
| `done` | All activities in the window are imported |
| `paused: rate limit…` | Hit Strava's daily cap (1,000 reads). Open `/strava/connect` again after midnight UTC; it skips what's already imported |
| `failed` | The `error` field says why; paste it into the Claude Code chat |

If the app restarts or redeploys mid-import, it resumes the import by itself on startup.

## 4. Check the live webhook

Save any activity in Strava (or edit an old one's title). Within a few seconds `/strava/status` should show `workouts` go up (new) or the change stored (edit).

## Disconnecting

Strava → Settings → My Apps → revoke the app. Strava sends a deauthorization event and the app deletes its stored tokens.
