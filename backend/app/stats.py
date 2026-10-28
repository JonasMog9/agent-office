"""GET /stats: the numbers behind the stats page.

The last 30 days of recovery, strain and training load, and every Market Scout alert with how
each paper-trading strategy played out on it ("what the Scout flagged vs. what happened").
Health numbers are private, so this needs OFFICE_VIEW_KEY in the ``X-Office-Key`` header,
like the live office.
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
from app.scout.paper import STRATEGIES

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


def _trade(t: PaperTrade) -> dict:
    price = t.exit_price if t.closed_at else t.last_price
    return {
        "status": "closed" if t.closed_at else "open",
        "exit_reason": t.exit_reason,
        "now_x": None if not price or not t.entry_price else round(price / t.entry_price, 2),
        "sold_pct": round(100 * (1 - t.held)),
        "pnl_usd": t.pnl_usd if t.closed_at else None,
        "pnl_now_usd": None if t.closed_at else round(paper_book.as_trade(t).open_pnl, 2),
    }


def scout(session: Session, now: datetime) -> dict:
    trades: dict[int, dict[str, PaperTrade]] = {}
    for t in session.scalars(select(PaperTrade)):
        trades.setdefault(t.alert_id, {})[t.strategy] = t
    alerts = session.scalars(select(ScoutAlert).order_by(ScoutAlert.alerted_at.desc())).all()
    since = now - timedelta(days=DAYS)
    scans = session.scalar(select(func.count()).where(ScoutScan.ran_at >= since)) or 0
    rows = []
    for a in alerts:
        mine = trades.get(a.id, {})
        peaks = [t.peak_price / t.entry_price for t in mine.values() if t.peak_price]
        rows.append(
            {
                "symbol": a.symbol,
                "chain": a.chain,
                "alerted_at": a.alerted_at.isoformat(),
                "fdv_usd": a.fdv_usd,
                "volume_h24_usd": a.volume_h24_usd,
                "peak_x": round(max(peaks), 2) if peaks else None,
                "trades": {k: _trade(t) for k, t in mine.items()},
            }
        )
    totals = paper_book.summaries(session)
    strategies = []
    for s in STRATEGIES:
        done = sorted(
            (t for m in trades.values() if (t := m.get(s.key)) and t.closed_at),
            key=lambda t: t.closed_at,
        )
        curve, running = [], 0.0
        for t in done:
            running += t.pnl_usd or 0
            curve.append({"at": t.closed_at.isoformat(), "pnl_usd": round(running, 2)})
        strategies.append(
            {
                "key": s.key,
                "name": s.name,
                "blurb": s.blurb,
                "summary": totals[s.key],
                "curve": curve,
            }
        )
    # "paper" is Quick 2×'s summary, for a page loaded before strategies existed.
    return {"scans_30d": scans, "alerts": rows, "strategies": strategies, "paper": totals["quick"]}


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
