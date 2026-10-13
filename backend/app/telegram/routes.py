"""POST /telegram: Telegram's webhook. Only the owner gets answers; everyone else is ignored.

Telegram expects a quick 200 and retries otherwise, while an agent answer takes several
seconds, so the route checks the request, answers 200 at once and lets the agents work in a
background task. Telegram's own secret header proves the request came from Telegram.
"""

import hmac
import logging
import threading
from collections import deque
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Header, Request
from fastapi.responses import JSONResponse

from app.agents.routes import anthropic_client
from app.agents.team import ask_manager
from app.config import get_settings, public_base_url
from app.db.session import SessionLocal
from app.telegram import morning
from app.telegram.bot import TelegramBot

log = logging.getLogger(__name__)
router = APIRouter()

HELP = (
    "Hi! I'm your Agent Office manager. Ask me anything about your recovery, sleep, training "
    'or races, e.g. "How recovered am I?", "What should I run today?" or "Predict my '
    "marathon\". /today sends this morning's summary again."
)
_seen: deque[int] = deque(maxlen=200)  # Telegram retries deliveries; answer each update once
_seen_lock = threading.Lock()


def bot() -> TelegramBot:
    return TelegramBot()


def answer(text: str) -> str:
    return ask_manager(anthropic_client(), SessionLocal, text[:2000]).text


def handle_message(chat_id: int, text: str) -> None:
    b = bot()
    try:
        if text.startswith("/start") or text.startswith("/help"):
            b.send(chat_id, HELP)
            return
        b.typing(chat_id)
        prompt = morning.PROMPT if text.startswith("/today") else text
        b.send(chat_id, answer(prompt))
    except Exception:  # noqa: BLE001
        log.exception("Telegram reply failed")
        try:
            b.send(chat_id, "Sorry, something went wrong on my side. Try again in a minute.")
        except Exception:  # noqa: BLE001
            log.exception("Telegram error reply failed too")


@router.post("/telegram")
async def telegram_webhook(
    request: Request,
    background: BackgroundTasks,
    secret: Annotated[str | None, Header(alias="X-Telegram-Bot-Api-Secret-Token")] = None,
) -> JSONResponse:
    settings = get_settings()
    expected = settings.telegram_webhook_secret
    if not expected or not secret or not hmac.compare_digest(secret, expected):
        return JSONResponse({"error": "bad secret"}, status_code=401)
    update = await request.json()
    message = update.get("message") or {}
    sender = (message.get("from") or {}).get("id")
    text = (message.get("text") or "").strip()
    with _seen_lock:
        duplicate = update.get("update_id") in _seen
        _seen.append(update.get("update_id"))
    # Everyone but the owner is ignored without a reply (CLAUDE.md).
    if duplicate or not text or sender != settings.telegram_owner_user_id:
        return JSONResponse({"ok": True})
    background.add_task(handle_message, message["chat"]["id"], text)
    return JSONResponse({"ok": True})


def register_webhook() -> None:
    """Point the bot at this app's /telegram (at startup; harmless to repeat)."""
    settings = get_settings()
    if not settings.telegram_bot_token or not settings.telegram_webhook_secret:
        log.info("Telegram not configured; skipping webhook registration")
        return
    base = public_base_url("")
    if not base.startswith("https://"):
        log.info("No public https URL; skipping webhook registration")
        return
    try:
        bot().set_webhook(f"{base}/telegram", settings.telegram_webhook_secret)
        log.info("Telegram webhook set to %s/telegram", base)
    except Exception:  # noqa: BLE001
        log.exception("Setting the Telegram webhook failed")


def send_morning_if_due() -> bool:
    return morning.maybe_send(SessionLocal, answer, lambda chat, text: bot().send(chat, text))
