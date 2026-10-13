"""The daily morning summary on Telegram, sent once a day when it can say something true.

Today's numbers only exist after the iOS Shortcut has sent last night's data (it runs when
you open Gmail), so a fixed 7am push would often report yesterday. Instead:

    after an ingest   if today's recovery is now scored and it's past EARLIEST → send
    fallback          a background check every 5 minutes; at FALLBACK hour → send anyway
                      (the coach then says today's data hasn't arrived)

The send is recorded in ``app_state`` before going out, so a restart or a second trigger
never sends twice; at most once a day, even if Telegram is down (better a missed summary
than a stream of duplicates).
"""

import logging
import threading
from collections.abc import Callable
from datetime import date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import AppState, DailyScore

log = logging.getLogger(__name__)
KEY = "morning_push_last_date"
CHECK_EVERY_S = 300
PROMPT = (
    "Morning summary for today, for a Telegram message: recovery and why, last night's sleep "
    "and tonight's need, training load (fitness, fatigue, form), today's workout from the plan "
    "if there is one, and any warnings. Five short lines at most."
)
_lock = threading.Lock()


def _now() -> datetime:
    return datetime.now(ZoneInfo(get_settings().timezone))


def _claim(session: Session, today: date) -> bool:
    """Mark today's summary as sent; False if it already was."""
    row = session.get(AppState, KEY)
    if row and row.value == today.isoformat():
        return False
    if row:
        row.value = today.isoformat()
    else:
        session.add(AppState(key=KEY, value=today.isoformat()))
    session.commit()
    return True


def maybe_send(
    session_factory: Callable[[], Session],
    ask: Callable[[str], str],
    send: Callable[[int, str], object],
    now: datetime | None = None,
) -> bool:
    """Send today's summary if it's due. ``ask`` answers a prompt via the agents."""
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_owner_user_id:
        return False
    now = now or _now()
    today = now.date()
    if now.hour < settings.morning_push_earliest_hour:
        return False
    with _lock, session_factory() as session:
        score = session.get(DailyScore, today)
        data_ready = score is not None and score.recovery is not None
        if not data_ready and now.hour < settings.morning_push_fallback_hour:
            return False
        if not _claim(session, today):
            return False
    prompt = PROMPT if data_ready else PROMPT + " Today's data hasn't arrived yet; say so."
    try:
        send(settings.telegram_owner_user_id, ask(prompt))
    except Exception:  # noqa: BLE001  (logged; today's claim stays, so no retry storm)
        log.exception("Morning summary failed")
        return False
    return True


def run_fallback_loop(check: Callable[[], object], stop: threading.Event) -> None:
    while not stop.is_set():
        try:
            check()
        except Exception:  # noqa: BLE001
            log.exception("Morning summary check failed")
        stop.wait(CHECK_EVERY_S)


def start_fallback_thread(check: Callable[[], object]) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=run_fallback_loop, args=(check, stop), daemon=True).start()
    return stop
