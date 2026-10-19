"""One Market Scout scan, every few minutes:

    1. pull trending and top-volume pools on each chain (GeckoTerminal)
    2. keep coins at most 48 h old and run the market screen on them (``screen.py``)
    3. rug-test the ones that pass (``rug.py``), at most every 6 h per coin
    4. a coin that passes both, and was never alerted before, becomes an alert, up to
       MAX_ALERTS_PER_DAY (the owner wants potential runners, not a feed)
    5. record the scan, with the closest near misses, so "anything up?" has an answer

The scan computes everything; ``notify`` (the Scout agent + Telegram) only words the alert.
"""

import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import ScoutAlert, ScoutCheck, ScoutScan
from app.metrics.common import Component, ScoreResult
from app.scout.screen import Pool, Rules, age_hours, screen
from app.scout.sources import MarketData, main_pools

log = logging.getLogger(__name__)
RECHECK_AFTER = timedelta(hours=6)
NEAR_MISSES = 5
_lock = threading.Lock()


def failed_rules(result: ScoreResult) -> list[str]:
    return [c.name for c in result.components if not c.note.startswith("pass")]


def pool_summary(pool: Pool, now: datetime) -> dict:
    d = asdict(pool)
    d["created_at"] = pool.created_at.isoformat() if pool.created_at else None
    d["age_hours"] = None if (a := age_hours(pool, now)) is None else round(a, 1)
    return d


def result_from_dict(d: dict) -> ScoreResult:
    return ScoreResult(
        d.get("value"),
        [Component(**c) for c in d.get("components", [])],
        list(d.get("notes", [])),
        d.get("label"),
    )


def cached_rug_test(session: Session, src: MarketData, pool: Pool, now: datetime) -> ScoreResult:
    row = session.scalar(
        select(ScoutCheck).where(
            ScoutCheck.chain == pool.chain, ScoutCheck.token_address == pool.token_address
        )
    )
    checked = row and row.checked_at
    if checked and checked.tzinfo is None:  # SQLite hands back naive datetimes
        checked = checked.replace(tzinfo=now.tzinfo)
    if row and checked and now - checked < RECHECK_AFTER:
        return result_from_dict(row.details)
    result = src.rug_test(pool)
    if row is None:
        row = ScoutCheck(chain=pool.chain, token_address=pool.token_address)
        session.add(row)
    row.checked_at, row.passed, row.details = now, result.label == "pass", result.as_dict()
    session.commit()
    return result


def alerts_since(session: Session, since: datetime) -> int:
    return session.scalar(select(func.count()).where(ScoutAlert.alerted_at >= since)) or 0


def already_alerted(session: Session, pool: Pool) -> bool:
    return (
        session.scalar(
            select(ScoutAlert.id).where(
                ScoutAlert.chain == pool.chain, ScoutAlert.token_address == pool.token_address
            )
        )
        is not None
    )


def run_scan(
    session: Session,
    src: MarketData,
    now: datetime,
    chains: list[str],
    rules: Rules,
    max_alerts_per_day: int,
    notify: Callable[[ScoutAlert], None] | None = None,
) -> ScoutScan:
    errors: list[str] = []
    pools: list[Pool] = []
    for chain in chains:
        try:
            pools += src.scan_pools(chain)
        except Exception as exc:  # noqa: BLE001  (one chain down shouldn't stop the others)
            log.warning("Scout: %s pools failed: %s", chain, exc)
            errors.append(f"{chain}: {type(exc).__name__}")
    pools = main_pools(pools)
    young = [p for p in pools if (a := age_hours(p, now)) is not None and a <= rules.max_age_h]
    screened = sorted(
        ((p, screen(p, now, rules)) for p in young), key=lambda pr: pr[1].value or 0, reverse=True
    )

    near: list[dict] = []
    new_alerts: list[ScoutAlert] = []
    for pool, market in screened:
        if market.label != "pass":
            if len(near) < NEAR_MISSES:
                near.append(_miss(pool, market, now, failed_rules(market)))
            continue
        if already_alerted(session, pool):
            continue
        try:
            rug = cached_rug_test(session, src, pool, now)
        except Exception as exc:  # noqa: BLE001
            log.warning("Scout: rug test for %s failed: %s", pool.symbol, exc)
            errors.append(f"rug test {pool.symbol}: {type(exc).__name__}")
            continue
        if rug.label != "pass":
            if len(near) < NEAR_MISSES:
                near.append(_miss(pool, market, now, ["rug: " + r for r in failed_rules(rug)]))
            continue
        if alerts_since(session, now - timedelta(days=1)) >= max_alerts_per_day:
            near.append(_miss(pool, market, now, ["daily alert limit reached"]))
            continue
        alert = ScoutAlert(
            chain=pool.chain,
            token_address=pool.token_address,
            pool_address=pool.pool_address,
            symbol=pool.symbol,
            alerted_at=now,
            price_usd=pool.price_usd,
            fdv_usd=pool.fdv_usd,
            liquidity_usd=pool.liquidity_usd,
            volume_h24_usd=pool.volume_usd.get("h24"),
            details={
                "pool": pool_summary(pool, now),
                "market": market.as_dict(),
                "rug": rug.as_dict(),
            },
            message="",
        )
        session.add(alert)
        session.commit()  # claimed before notifying: a crash mid-send never alerts twice
        new_alerts.append(alert)

    scan = ScoutScan(
        ran_at=now,
        pools_seen=len(pools),
        young=len(young),
        screened=sum(1 for _, m in screened if m.label == "pass"),
        alerts=len(new_alerts),
        near_misses=near,
        errors=errors,
    )
    session.add(scan)
    session.commit()
    for alert in new_alerts:
        if notify is None:
            continue
        try:
            notify(alert)
        except Exception:  # noqa: BLE001  (the alert stays recorded; logged, not retried)
            log.exception("Scout: sending the alert for %s failed", alert.symbol)
    return scan


def _miss(pool: Pool, market: ScoreResult, now: datetime, failed: list[str]) -> dict:
    return {
        "symbol": pool.symbol,
        "chain": pool.chain,
        "token_address": pool.token_address,
        "age_hours": round(age_hours(pool, now) or 0, 1),
        "volume_h24_usd": pool.volume_usd.get("h24"),
        "runner_score": market.value,
        "failed": failed,
    }


def run_locked(fn: Callable[[], object]) -> object | None:
    """Run one scan at a time; skip if one is still going."""
    if not _lock.acquire(blocking=False):
        return None
    try:
        return fn()
    finally:
        _lock.release()


def run_loop(scan: Callable[[], object], every_s: float, stop: threading.Event) -> None:
    wait = 60.0  # first scan a minute after startup, then every ``every_s``
    while not stop.wait(wait):
        wait = every_s
        try:
            run_locked(scan)
        except Exception:  # noqa: BLE001
            log.exception("Scout scan failed")


def start_thread(scan: Callable[[], object], every_s: float) -> threading.Event:
    stop = threading.Event()
    threading.Thread(target=run_loop, args=(scan, every_s, stop), daemon=True).start()
    return stop
