"""The scheduled scan: run it, and send any new alert to the owner on Telegram."""

import logging
from datetime import UTC, datetime

from app.agents.routes import anthropic_client
from app.agents.team import write_alert
from app.config import get_settings
from app.db.models import ScoutAlert, ScoutScan
from app.db.session import SessionLocal
from app.scout import settings as scout_settings
from app.scout.scan import run_scan
from app.scout.sources import MarketData
from app.telegram.bot import TelegramBot

log = logging.getLogger(__name__)


def notify(alert: ScoutAlert) -> None:
    text = write_alert(anthropic_client(), alert)
    with SessionLocal() as session:
        row = session.get(ScoutAlert, alert.id)
        if row is not None:
            row.message = text
            session.commit()
    settings = get_settings()
    if settings.telegram_bot_token and settings.telegram_owner_user_id:
        TelegramBot().send(settings.telegram_owner_user_id, text)
    else:
        log.info("Telegram not configured; alert for %s stored only", alert.symbol)


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
