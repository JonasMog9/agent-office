# Importing your Apple Health history (Phase 2 backfill)

One-off. It loads the last 400 days of HRV, resting heart rate, respiratory rate, sleep stages, active energy, VO2 max and running form, so the recovery score has its 60-day baseline from day one. It's safe to repeat: readings the Shortcut already sent aren't stored twice.

## 1. Export from the iPhone

Health app → tap your **profile picture** (top right) → **Export All Health Data** → **Export**. This takes a minute or two. Then **Save to Files** (e.g. iCloud Drive or On My iPhone). You get `export.zip`, often 100 MB to 1 GB.

## 2. Upload it

On the same iPhone, open in Safari:

**https://agent-office-production-d0e3.up.railway.app/ingest/apple-export**

1. **Ingest secret**: the `INGEST_SECRET` value from Railway (the same one the Shortcut uses).
2. **Choose File** → Browse → pick `export.zip`.
3. **Upload**, and keep Safari open until it says **Upload received ✅**. A large file can take a few minutes on Wi-Fi.

## 3. Watch it finish

**https://agent-office-production-d0e3.up.railway.app/ingest/apple-export/status**

| Status | Meaning |
| --- | --- |
| `queued` / `parsing` | Reading the export; `records_seen` climbs (often into the millions; everything that isn't one of our metrics is skipped quickly) |
| `computing days` | Rebuilding each day's numbers; `days_done` counts up to `days` |
| `done` | Finished. `by_metric` shows how many readings were stored per metric, `first_day` / `last_day` the range |
| `failed` | The `error` says why; paste it into the Claude Code chat |

The progress page lives in memory, so if the app restarts mid-import it shows `idle`. Just upload again: anything already stored is skipped.

## Notes

- Active energy is stored as one total per day. iPhone and Watch both record it, and adding both would double count, so the larger of the two devices' totals is kept. That matches what the Health app shows.
- Workouts in the export are ignored; Strava is the source for workouts.
