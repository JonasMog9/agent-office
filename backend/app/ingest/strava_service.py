"""Strava token lifecycle, activity import, webhook events and history backfill."""

import logging
import threading
from collections.abc import Callable
from datetime import UTC, datetime

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import StravaToken, Workout
from app.db.upsert import insert_for
from app.ingest.strava import RateLimited, StravaClient, StravaError, workout_from_activity

log = logging.getLogger(__name__)
_refresh_lock = threading.Lock()
_backfill_lock = threading.Lock()  # one import at a time per process


class NotConnected(StravaError):
    pass


def save_token(session: Session, payload: dict, athlete_id: int) -> StravaToken:
    row = session.get(StravaToken, athlete_id) or StravaToken(athlete_id=athlete_id)
    row.access_token = payload["access_token"]
    row.refresh_token = payload["refresh_token"]  # Strava may rotate it on every refresh
    row.expires_at = int(payload["expires_at"])
    if "scope" in payload:
        row.scope = payload["scope"]
    session.add(row)
    session.commit()
    return row


def owner_token(session: Session) -> StravaToken | None:
    return session.get(StravaToken, get_settings().strava_athlete_id)


def access_token(session: Session, client: StravaClient) -> str:
    """A valid access token for the owner, refreshing (and saving the rotated token) as needed."""
    with _refresh_lock:
        row = owner_token(session)
        if row is None:
            env_refresh = get_settings().strava_refresh_token
            if not env_refresh:
                raise NotConnected("Strava isn't connected yet: open /strava/connect")
            row = save_token(session, client.refresh(env_refresh), get_settings().strava_athlete_id)
        elif row.expires_at - 120 <= client.now():
            row = save_token(session, client.refresh(row.refresh_token), row.athlete_id)
        return row.access_token


def import_activity(session: Session, client: StravaClient, activity_id: int) -> bool:
    """Fetch one activity + streams and upsert it. False if Strava no longer has it."""
    token = access_token(session, client)
    activity = client.get_activity(token, activity_id)
    if activity is None:
        return False
    if activity.get("athlete", {}).get("id") not in (None, get_settings().strava_athlete_id):
        return False
    values = workout_from_activity(activity, client.get_streams(token, activity_id))
    stmt = insert_for(session, Workout).values(**values)
    update = {k: v for k, v in values.items() if k != "id"} | {"updated_at": func.now()}
    session.execute(stmt.on_conflict_do_update(index_elements=["id"], set_=update))
    session.commit()
    return True


def handle_event(session: Session, client: StravaClient, event: dict) -> str:
    """Apply one webhook event. Events are unsigned, so every change is confirmed via the API."""
    if event.get("owner_id") != get_settings().strava_athlete_id:
        return "ignored: not the owner"
    kind, aspect = event.get("object_type"), event.get("aspect_type")
    if kind == "athlete":
        if str(event.get("updates", {}).get("authorized")).lower() == "false":
            if row := owner_token(session):
                session.delete(row)
                session.commit()
            return "deauthorized"
        return "ignored"
    if kind != "activity":
        return "ignored"
    activity_id = int(event["object_id"])
    if aspect in ("create", "update"):
        return "imported" if import_activity(session, client, activity_id) else "gone"
    if aspect == "delete":
        # Only delete once Strava confirms the activity is gone, so a forged event can't.
        token = access_token(session, client)
        if client.get_activity(token, activity_id) is None:
            if workout := session.get(Workout, activity_id):
                session.delete(workout)
                session.commit()
            return "deleted"
        return "ignored: still exists"
    return "ignored"


def _set_backfill(session: Session, status: str, imported: int, error: str | None = None) -> None:
    if row := owner_token(session):
        row.backfill_status, row.backfill_imported, row.backfill_error = status, imported, error
        session.commit()


def backfill(
    session_factory: Callable[[], Session], client: StravaClient, days: int | None = None
) -> int:
    """Import the last ``days`` of activities, skipping ones already stored with streams.

    Safe to rerun: it resumes where it stopped (after a restart or the daily rate limit).
    Returns -1 without doing anything if an import is already running in this process.
    """
    if not _backfill_lock.acquire(blocking=False):
        return -1
    try:
        return _backfill(session_factory, client, days)
    finally:
        client.on_wait = None
        _backfill_lock.release()


def _backfill(
    session_factory: Callable[[], Session], client: StravaClient, days: int | None
) -> int:
    days = days or get_settings().strava_backfill_days
    after = int(client.now()) - days * 86400
    imported = 0
    with session_factory() as session:

        def waiting(until: float) -> None:
            at = datetime.fromtimestamp(until, UTC).strftime("%H:%M UTC")
            _set_backfill(session, f"waiting for Strava rate limit until {at}", imported)

        client.on_wait = waiting
        try:
            _set_backfill(session, "running", 0)
            page = 1
            while batch := client.list_activities(access_token(session, client), after, page):
                for summary in batch:
                    existing = session.get(Workout, summary["id"])
                    if existing is not None and existing.streams is not None:
                        continue
                    if import_activity(session, client, summary["id"]):
                        imported += 1
                        _set_backfill(session, "running", imported)
                page += 1
            _set_backfill(session, "done", imported)
        except RateLimited as err:
            _set_backfill(
                session,
                "paused: daily rate limit, resumes on the next restart or reconnect",
                imported,
                str(err),
            )
        except Exception as err:  # noqa: BLE001  (record any failure; the thread must not die silently)
            log.exception("Strava backfill failed")
            session.rollback()
            _set_backfill(session, "failed", imported, f"{type(err).__name__}: {err}"[:500])
    return imported


def ensure_subscription(session: Session, client: StravaClient, callback_url: str) -> int:
    """Create the app's single webhook subscription if it doesn't exist yet; return its id."""
    existing = client.list_subscriptions()
    if existing:
        sub_id = int(existing[0]["id"])
    else:
        created = client.create_subscription(
            callback_url, get_settings().strava_webhook_verify_token
        )
        sub_id = int(created["id"])
    if row := owner_token(session):
        row.subscription_id = sub_id
        session.commit()
    return sub_id


UNFINISHED = ("running", "waiting", "paused")


def has_unfinished_backfill(session: Session) -> bool:
    row = owner_token(session)
    return row is not None and row.backfill_status.startswith(UNFINISHED)
