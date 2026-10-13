"""A thin Telegram Bot API client (sendMessage, typing, setWebhook) over httpx.

The bot only needs four Bot API methods, so it calls them directly rather than through a
framework; that keeps the webhook a plain FastAPI route and easy to test.
"""

import html
import logging
import re

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)
API = "https://api.telegram.org"
MAX_LEN = 4096


def to_telegram_html(text: str) -> str:
    """The agents write light Markdown; Telegram's HTML mode is the safe subset to send it in.

    Escapes everything, then turns **bold** into <b>bold</b> and leading "- " into "• ".
    """
    out = html.escape(text, quote=False)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"(?m)^\s*[-*] ", "• ", out)
    if len(out) > MAX_LEN:
        out = out[: MAX_LEN - 1] + "…"
    return out


class TelegramBot:
    def __init__(self, token: str | None = None, http: httpx.Client | None = None) -> None:
        self.token = token if token is not None else get_settings().telegram_bot_token
        self.http = http or httpx.Client(timeout=20)

    def _call(self, method: str, **payload) -> dict:  # noqa: ANN003
        r = self.http.post(f"{API}/bot{self.token}/{method}", json=payload)
        data = r.json()
        if not data.get("ok"):
            # Never log the URL: it contains the bot token.
            raise RuntimeError(f"Telegram {method} failed: {data.get('description')}")
        return data

    def send(self, chat_id: int, text: str) -> dict:
        return self._call(
            "sendMessage", chat_id=chat_id, text=to_telegram_html(text), parse_mode="HTML"
        )

    def typing(self, chat_id: int) -> None:
        try:
            self._call("sendChatAction", chat_id=chat_id, action="typing")
        except Exception:  # noqa: BLE001  (cosmetic; never block a reply on it)
            log.warning("sendChatAction failed")

    def set_webhook(self, url: str, secret: str) -> dict:
        return self._call(
            "setWebhook",
            url=url,
            secret_token=secret,
            allowed_updates=["message"],
            drop_pending_updates=True,
        )
