"""The scheduled scan: run it, send any new alert to the owner on Telegram, then update the
paper-trading book (and say when a paper trade closes)."""

import logging
from datetime import UTC, datetime

from app.agents.routes import anthropic_client
from app.agents.team import write_alert
from app.config import get_settings
from app.db.models import ScoutAlert, ScoutScan
from app.db.session import SessionLocal
from app.scout import paper_book
from app.scout import settings as scout_settings
from app.scout.scan import run_scan
from app.scout.sources import MarketData
from app.telegram.bot import TelegramBot

log = logging.getLogger(__name__)


def send(text: str) -> None:
    settings = get_settings()
    if settings.telegram_bot_token and settings.telegram_owner_user_id:
        TelegramBot().send(settings.telegram_owner_user_id, text)


def notify(alert: ScoutAlert) -> None:
    text = write_alert(anthropic_client(), alert)
    with SessionLocal() as session:
        row = session.get(ScoutAlert, alert.id)
        if row is not None:
            row.message = text
            session.commit()
    send(text)


def scan_now() -> ScoutScan:
    src = MarketData()
    try:
        with SessionLocal() as session:
            scan = run_scan(
                session,
                src,
                datetime.now(UTC),
                scout_settings.chains(),
                scout_settings.rules(),
                get_settings().scout_max_alerts_per_day,
                notify,
            )
            update_paper_trades(session, src)
    finally:
        src.close()
    log.info(
        "Scout scan: %s pools, %s young, %s screened, %s alerts",
        scan.pools_seen,
        scan.young,
        scan.screened,
        scan.alerts,
    )
    return scan


def update_paper_trades(session, src: MarketData) -> None:  # noqa: ANN001
    """Open trades for new alerts, re-price the open ones, report any that closed."""
    try:
        paper_book.open_missing(session)
        closed = paper_book.update(session, src, datetime.now(UTC))
    except Exception:  # noqa: BLE001  (paper trading never stops the scanner)
        log.exception("Paper trade update failed")
        return
    if closed:
        totals = paper_book.book(session)["summary"]
        for t in closed:
            try:
                send(paper_book.closed_message(t, totals))
            except Exception:  # noqa: BLE001
                log.exception("Sending the paper trade close for %s failed", t.symbol)
