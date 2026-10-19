"""GET /stats: the numbers behind the stats page.

The last 30 days of recovery, strain and training load, and every Market Scout alert with how
its paper trade played out ("what the Scout flagged vs. what happened"). Health numbers are
private, so this needs OFFICE_VIEW_KEY in the ``X-Office-Key`` header, like the live office.
"""

import hmac
from datetime import UTC, date, datetime, timedelta
from typing import Annotated

from fastapi import APIRouter, Depends, Header
from fastapi.responses import JSONResponse
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.coach_tools import today
from app.config import get_settings
from app.db.models import DailyScore, PaperTrade, ScoutAlert, ScoutScan
from app.db.session import get_session
from app.scout import paper_book

router = APIRouter()
DAYS = 30


def _r(x: float | None, nd: int = 0) -> float | None:
    return None if x is None else round(x, nd) if nd else round(x)


def health(session: Session, end: date) -> list[dict]:
    start = end - timedelta(days=DAYS - 1)
    rows = {
        r.day: r
        for r in session.scalars(select(DailyScore).where(DailyScore.day.between(start, end)))
    }
    out = []
    for i in range(DAYS):
        d = start + timedelta(days=i)
        r = rows.get(d)
        out.append(
            {
                "day": d.isoformat(),
                "recovery": _r(r.recovery) if r else None,
                "label": r.recovery_label if r else None,
                "strain": _r(r.strain, 1) if r else None,
                "sleep_pct": _r(r.sleep_performance) if r else None,
                "fitness": _r(r.ctl, 1) if r else None,
                "fatigue": _r(r.atl, 1) if r else None,
            }
        )
    return out


def scout(session: Session, now: datetime) -> dict:
    trades = {t.alert_id: t for t in session.scalars(select(PaperTrade))}
    alerts = session.scalars(select(ScoutAlert).order_by(ScoutAlert.alerted_at.desc())).all()
    since = now - timedelta(days=DAYS)
    scans = session.scalar(select(func.count()).where(ScoutScan.ran_at >= since)) or 0
    rows = []
    for a in alerts:
        t = trades.get(a.id)
        price = None if t is None else (t.exit_price if t.closed_at else t.last_price)
        rows.append(
            {
                "symbol": a.symbol,
                "chain": a.chain,
                "alerted_at": a.alerted_at.isoformat(),
                "fdv_usd": a.fdv_usd,
                "volume_h24_usd": a.volume_h24_usd,
                "status": None if t is None else ("closed" if t.closed_at else "open"),
                "exit_reason": t.exit_reason if t else None,
                "now_x": None if not t or not price else round(price / t.entry_price, 2),
                "peak_x": None
                if not t or not t.peak_price
                else round(t.peak_price / t.entry_price, 2),
                "pnl_usd": t.pnl_usd if t and t.closed_at else None,
            }
        )
    return {"scans_30d": scans, "alerts": rows, "paper": paper_book.book(session)["summary"]}


@router.get("/stats")
def stats(
    session: Annotated[Session, Depends(get_session)],
    key: Annotated[str | None, Header(alias="X-Office-Key")] = None,
) -> JSONResponse:
    expected = get_settings().office_view_key
    if not expected or not key or not hmac.compare_digest(key.encode(), expected.encode()):
        return JSONResponse({"error": "bad key"}, status_code=401)
    return JSONResponse(
        {
            "generated_at": datetime.now(UTC).isoformat(),
            "health": health(session, today()),
            "scout": scout(session, datetime.now(UTC)),
        }
    )
