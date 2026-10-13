"""A private test page for the agents: ask the Manager a question and see the event log.

Telegram (Phase 4) becomes the real front door; this exists to check the agents end to end
from a phone. Protected by the ingest secret, like the Apple Health upload page.
"""

import hmac
import logging
import uuid
from html import escape
from typing import Annotated

from fastapi import APIRouter, Form
from fastapi.responses import HTMLResponse

from app.agents.events import bus
from app.agents.team import ask_manager
from app.config import get_settings
from app.db.session import SessionLocal

log = logging.getLogger(__name__)
router = APIRouter(prefix="/agents")

FORM = """<!doctype html><meta name=viewport content='width=device-width'>
<title>Ask the Manager</title><h2>Ask the Manager</h2>
<form method=post>
<p><label>Ingest secret<br><input name=secret type=password required></label></p>
<p><label>Question<br><textarea name=question rows=3 cols=34 required>How recovered am I today?\
</textarea></label></p>
<p><button>Ask</button></p></form>"""


def _page(body: str, status: int = 200) -> HTMLResponse:
    return HTMLResponse(
        f"<!doctype html><meta name=viewport content='width=device-width'>{body}",
        status_code=status,
    )


def anthropic_client():  # noqa: ANN201
    import anthropic

    return anthropic.Anthropic(api_key=get_settings().anthropic_api_key or None)


@router.get("/ask", response_class=HTMLResponse)
def ask_form() -> HTMLResponse:
    return _page(FORM)


@router.post("/ask", response_class=HTMLResponse)
def ask(secret: Annotated[str, Form()], question: Annotated[str, Form()]) -> HTMLResponse:
    expected = get_settings().ingest_secret
    if not expected or not hmac.compare_digest(secret.encode(), expected.encode()):
        return _page("<h2>Wrong secret</h2>", 401)
    if not get_settings().anthropic_api_key:
        return _page("<h2>ANTHROPIC_API_KEY is not set in Railway</h2>", 500)
    run = uuid.uuid4().hex[:12]
    try:
        result = ask_manager(anthropic_client(), SessionLocal, question[:2000], run_id=run)
    except Exception as err:  # noqa: BLE001  (show the owner what broke instead of a bare 500)
        log.exception("Agent run failed")
        detail = escape(f"{type(err).__name__}: {str(err)[:600]}")
        return _page(
            f"<h2>The agents hit an error</h2><p><code>{detail}</code></p>"
            f"{_log_table(run)}<p><a href=/agents/ask>Try again</a></p>",
            500,
        )
    answer = escape(result.text).replace("\n", "<br>")
    return _page(
        f"<h2>Answer</h2><p>{answer}</p>{_log_table(run)}<p><a href=/agents/ask>Ask another</a></p>"
    )


def _log_table(run: str) -> str:
    rows = "".join(
        f"<tr><td>{e.id}</td><td>{escape(e.agent)}</td><td>{escape(e.status)}</td>"
        f"<td>{escape(e.target or '')}</td><td>{escape(e.text)}</td></tr>"
        for e in bus.recent(run)
    )
    return (
        f"<h3>Event log</h3><table border=1 cellpadding=4><tr><th>#</th><th>agent</th>"
        f"<th>status</th><th>target</th><th>text</th></tr>{rows}</table>"
    )
