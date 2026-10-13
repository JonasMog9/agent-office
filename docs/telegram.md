# Telegram bot (Phase 4)

The bot is the front door: text it and the Manager answers; every morning it sends a summary.

## What's already set

From Phase 0, Railway (backend service → Variables) holds:

- `TELEGRAM_BOT_TOKEN`: from @BotFather.
- `TELEGRAM_OWNER_USER_ID`: your numeric Telegram ID (from @userinfobot). Only this ID gets answers; anyone else is silently ignored.
- `TELEGRAM_WEBHOOK_SECRET`: any random string of **letters, digits, `_` and `-` only** (Telegram rejects other characters), 20+ long.

On startup the app registers its webhook with Telegram (`https://<your Railway domain>/telegram`), so there's nothing to click.

## Using it

- Open your bot in Telegram, send `/start`.
- Ask anything: "How recovered am I?", "What should I run today?", "Predict my marathon", "Make me a plan, I'm coming back from a hip injury".
- `/today` sends the morning summary on demand.

## The morning summary

Sent once a day, as soon as today's health data has arrived (the iOS Shortcut runs when you open Gmail) and it's after `MORNING_PUSH_EARLIEST_HOUR` (default 6). If no data has arrived by `MORNING_PUSH_FALLBACK_HOUR` (default 10), it's sent anyway and says the data is missing. Times are in `TIMEZONE`.

## If the bot doesn't answer

- Railway logs show `Telegram webhook set to …` after a deploy. A `Setting the Telegram webhook failed` line names the reason (usually a bad token or a secret with forbidden characters).
- The ID in `TELEGRAM_OWNER_USER_ID` must be yours exactly; messages from any other ID get no reply by design.
