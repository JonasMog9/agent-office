"""Strava routes: one-time connect, OAuth callback, webhook, and a status page."""

import hashlib
import hmac
import logging
import threading
import time
from html import escape
from typing import Annotated
from urllib.parse import urlencode

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_settings, public_base_url
from app.db.models import Workout
from app.db.session import SessionLocal, get_session
from app.ingest.strava import BASE, SCOPES, StravaClient, StravaError
from app.ingest.strava_service import (
    backfill,
    ensure_subscription,
    handle_event,
    has_unfinished_backfill,
    owner_token,
    save_token,
)

log = logging.getLogger(__name__)
router = APIRouter(prefix="/strava")


def get_client() -> StravaClient:
    return StravaClient()


Client = Annotated[StravaClient, Depends(get_client)]
DB = Annotated[Session, Depends(get_session)]


def _sign(value: str) -> str:
    key = get_settings().strava_client_secret.encode()
    return hmac.new(key, value.encode(), hashlib.sha256).hexdigest()[:32]


def _state() -> str:
    ts = str(int(time.time()))
    return f"{ts}.{_sign(ts)}"


def _state_ok(state: str, max_age_s: int = 600) -> bool:
    ts, _, sig = state.partition(".")
    if not ts.isdigit() or not hmac.compare_digest(sig, _sign(ts)):
        return False
    return 0 <= time.time() - int(ts) <= max_age_s


def start_backfill(client: StravaClient) -> None:
    """Run the history import in a background thread: it can take an hour at Strava's limits."""
    threading.Thread(target=backfill, args=(SessionLocal, client), daemon=True).start()


def resume_unfinished_backfill() -> bool:
    """On startup, continue an import a restart cut short. Never fails startup."""
    try:
        with SessionLocal() as session:
            if not has_unfinished_backfill(session):
                return False
        start_backfill(get_client())
        log.info("Resuming unfinished Strava backfill")
        return True
    except Exception:  # noqa: BLE001  (no database or table yet: nothing to resume)
        log.exception("Could not check for an unfinished Strava backfill")
        return False


def _page(title: str, body: str, status: int = 200) -> HTMLResponse:
    html = f"<!doctype html><meta name=viewport content='width=device-width'><h2>{title}</h2>{body}"
    return HTMLResponse(html, status_code=status)


@router.get("/connect")
def connect(request: Request) -> RedirectResponse:
    s = get_settings()
    if not (s.strava_client_id and s.strava_client_secret and s.strava_athlete_id):
        raise HTTPException(
            503, "STRAVA_CLIENT_ID, STRAVA_CLIENT_SECRET and STRAVA_ATHLETE_ID must be set"
        )
    params = {
        "client_id": s.strava_client_id,
        "redirect_uri": f"{public_base_url(str(request.base_url))}/strava/callback",
        "response_type": "code",
        "approval_prompt": "auto",
        "scope": SCOPES,
        "state": _state(),
    }
    return RedirectResponse(f"{BASE}/oauth/authorize?{urlencode(params)}")


@router.get("/callback")
def callback(
    request: Request,
    session: DB,
    client: Client,
    state: str = "",
    code: str = "",
    scope: str = "",
    error: str = "",
) -> HTMLResponse:
    if error:
        return _page("Strava not connected", f"<p>Strava said: {escape(error)}</p>", 400)
    if not _state_ok(state):
        return _page(
            "Link expired", "<p>Open <a href='/strava/connect'>/strava/connect</a> again.</p>", 400
        )
    if "activity:read" not in scope:
        return _page(
            "Missing permission",
            "<p>Tick <b>View data about your activities</b> (including private ones) on Strava's"
            " page, then <a href='/strava/connect'>try again</a>.</p>",
            400,
        )
    try:
        payload = client.exchange_code(code)
    except StravaError as err:
        return _page("Strava login failed", f"<p>{escape(str(err))}</p>", 502)
    athlete_id = int(payload.get("athlete", {}).get("id", 0))
    if athlete_id != get_settings().strava_athlete_id:
        return _page(
            "Wrong account", "<p>This app only connects its owner's Strava account.</p>", 403
        )
    save_token(session, payload | {"scope": scope}, athlete_id)  # scope arrives on the URL

    try:
        callback_url = f"{public_base_url(str(request.base_url))}/strava/webhook"
        webhook = f"webhook subscription {ensure_subscription(session, client, callback_url)}"
    except StravaError as err:
        log.warning("Strava webhook subscription failed: %s", err)
        webhook = f"webhook not set up yet ({escape(str(err))})"
    start_backfill(client)
    return _page(
        "Strava connected ✅",
        f"<p>Athlete {athlete_id}, {webhook}.</p>"
        "<p>Importing your activity history in the background. Strava's rate limits make this"
        " take up to about an hour. Progress: <a href='/strava/status'>/strava/status</a>.</p>",
    )


@router.get("/webhook")
def webhook_verify(
    mode: Annotated[str, Query(alias="hub.mode")] = "",
    challenge: Annotated[str, Query(alias="hub.challenge")] = "",
    verify_token: Annotated[str, Query(alias="hub.verify_token")] = "",
) -> dict:
    expected = get_settings().strava_webhook_verify_token
    if mode != "subscribe" or not expected or not hmac.compare_digest(verify_token, expected):
        raise HTTPException(403, "bad verify token")
    return {"hub.challenge": challenge}


def _process_event(event: dict, client: StravaClient) -> None:
    with SessionLocal() as session:
        try:
            result = handle_event(session, client, event)
            log.info(
                "Strava event %s/%s: %s", event.get("object_type"), event.get("object_id"), result
            )
        except Exception:  # noqa: BLE001  (log and move on; Strava doesn't need to know)
            log.exception("Strava event failed: %s", event)


@router.post("/webhook")
def webhook_event(event: Annotated[dict, Body()], tasks: BackgroundTasks, client: Client) -> dict:
    # Strava wants a 200 within 2 seconds, so the API calls happen after the response.
    tasks.add_task(_process_event, event, client)
    return {"ok": True}


@router.get("/status")
def status(session: DB) -> dict:
    row = owner_token(session)
    count, latest = session.execute(select(func.count(Workout.id), func.max(Workout.day))).one()
    return {
        "connected": row is not None,
        "scope": row.scope if row else None,
        "webhook_subscription": row.subscription_id if row else None,
        "backfill": {
            "status": row.backfill_status if row else "not started",
            "imported": row.backfill_imported if row else 0,
            "error": row.backfill_error if row else None,
            "last_progress_at": row.updated_at.isoformat() if row and row.updated_at else None,
        },
        "workouts": count,
        "latest_workout_day": latest.isoformat() if latest else None,
    }
