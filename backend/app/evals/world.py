"""The eval world: a made-up owner with 70 days of Apple Watch data and runs, pushed through
the real scoring pipeline, plus a few market scans, two alerts and their paper trades.

Everything is anchored on today, so "today", "last night" and "the last 7 days" mean the same
thing to the agents as they would in production. Nothing here is the owner's real data.
"""

import math
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.orm import Session

from app.agents.coach_tools import today as coach_today
from app.coach import plan_service
from app.db.models import DailyMetric, Workout
from app.metrics.common import Component, ScoreResult
from app.metrics.daily import invalidate_hr_max, recompute_scores
from app.scout import paper_book
from app.scout.scan import run_scan
from app.scout.screen import Pool, Rules

DAYS = 70
RUN_MINT = "7GCihgDB8fe6KNjn2MYtkzZcRjQy3t9GHdC8uHYmW2hr"
DUD_MINT = "9xQeWvG816bUx9EPjHmaT23yvVM2ZWbrrpZb9PusVFin"
RUG_MINT = "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3"
MEH_MINT = "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB"


def _pool(symbol: str, mint: str, created: datetime, **kw) -> Pool:
    """A young coin doing $3M on $400k liquidity with 2,500 buyers (passes the screen)."""
    base = Pool(
        chain="solana",
        pool_address=f"{symbol}POOL",
        token_address=mint,
        symbol=symbol,
        name=symbol.title(),
        created_at=created,
        price_usd=0.004,
        fdv_usd=4_000_000,
        liquidity_usd=400_000,
        volume_usd={"m5": 40_000, "h1": 350_000, "h6": 1_800_000, "h24": 3_000_000},
        price_change_pct={"h1": 8, "h6": 60, "h24": 900},
        buys_h24=9_000,
        sells_h24=6_000,
        buyers_h24=2_500,
        sellers_h24=1_400,
        dex="raydium",
    )
    return replace(base, **kw)


def _rug(passed: bool) -> ScoreResult:
    checks = [
        ("mint_authority", "revoked"),
        ("freeze_authority", "revoked"),
        ("lp_locked", "100.0% locked or burned"),
        ("top_holders", "top 10 hold 18%"),
    ]
    comps = [Component(n, 1.0, note=f"pass: {why}") for n, why in checks]
    if not passed:
        comps[2] = Component("lp_locked", 0.0, note="FAIL: 3.0% locked, the rest can be pulled")
    return ScoreResult(
        100 if passed else 75,
        comps,
        [] if passed else ["failed: lp_locked"],
        "pass" if passed else "fail",
    )


class EvalMarket:
    """Stand-in for ``MarketData``: scripted pools and rug tests, no network."""

    def __init__(self, now: datetime) -> None:
        self.now = now
        self.scan_pools_by_time: list[Pool] = []
        self.prices: dict[str, Pool] = {}
        self.pools = {
            RUN_MINT: _pool("RUN", RUN_MINT, now - timedelta(hours=58)),
            DUD_MINT: _pool("DUD", DUD_MINT, now - timedelta(hours=32), price_usd=0.0016),
            RUG_MINT: _pool("RUGME", RUG_MINT, now - timedelta(hours=6), price_usd=0.02),
            MEH_MINT: _pool(
                "MEH",
                MEH_MINT,
                now - timedelta(hours=20),
                volume_usd={"m5": 900, "h1": 9_000, "h6": 60_000, "h24": 210_000},
                buyers_h24=310,
            ),
        }

    def scan_pools(self, chain: str) -> list[Pool]:
        return self.scan_pools_by_time

    def token_pools(self, chain: str, address: str) -> list[Pool]:
        pool = self.pools.get(address)
        return [pool] if pool and chain == pool.chain else []

    def pool_prices(self, chain: str, addresses: list[str]) -> dict[str, Pool]:
        return {a: self.prices[a] for a in addresses if a in self.prices}

    def rug_test(self, pool: Pool) -> ScoreResult:
        return _rug(pool.token_address != RUG_MINT)

    def price_history(self, chain: str, pool_address: str, since: datetime) -> list:
        return []

    def close(self) -> None:
        pass


def _health(session: Session, end: date) -> None:
    for i in range(DAYS):
        d = end - timedelta(days=DAYS - 1 - i)
        late = i >= DAYS - 3  # the last three days: run down, a cold coming on
        w = math.sin(i * 0.9)
        session.add(
            DailyMetric(
                day=d,
                hrv_sdnn_ms=50 - (i - (DAYS - 3)) if late else 56 + 5 * w,
                resting_hr_bpm=52.5 if late else 51 + 1.2 * w,
                respiratory_rate_bpm=15.7 if late else 15.4 + 0.3 * w,
                sleep_asleep_min=(405 + 9 * (i % 2)) if late else 452 + 25 * w,
                sleep_start=datetime(d.year, d.month, d.day, 0, 10 + int(10 * w), tzinfo=UTC),
                vo2max=51.5 + i * 0.01,
            )
        )
    # Runs: easy runs most days, a weekly long run, and a hard 10K effort three weeks ago.
    wid = 1
    for i in range(DAYS):
        d = end - timedelta(days=DAYS - 1 - i)
        if d.weekday() in (0, 4) or i >= DAYS - 2:
            continue  # rest days, and nothing while unwell
        long_run = d.weekday() == 6
        race = i == DAYS - 22
        km = 21.0 if long_run else 10.0 if race else 8.0 + (i % 3)
        pace = 4.6 if race else 5.75 if long_run else 5.3  # min/km
        secs = int(km * pace * 60)
        ts = list(range(0, secs, 5))  # a sample every 5 s keeps the world quick to build
        hr = [int((172 if race else 148) + 6 * math.sin(t / 300)) for t in ts]
        session.add(
            Workout(
                id=wid,
                sport_type="Run",
                name="10K effort" if race else "Long run" if long_run else "Easy run",
                start_at=datetime(d.year, d.month, d.day, 7, tzinfo=UTC),
                day=d,
                elapsed_s=secs + 60,
                moving_s=secs,
                distance_m=km * 1000,
                avg_hr=sum(hr) / len(hr),
                max_hr=max(hr),
                avg_speed_mps=1000 / (pace * 60),
                summary={},
                streams={
                    "time": ts,
                    "heartrate": hr,
                    "distance": [t * 1000 / (pace * 60) for t in ts],
                },
            )
        )
        wid += 1
    session.commit()
    invalidate_hr_max()
    recompute_scores(session, [end - timedelta(days=DAYS - 1 - i) for i in range(DAYS)])
    plan_service.create_plan(
        session, end, race_distance="half marathon", race_date=end + timedelta(days=70)
    )
    session.commit()


def _market(session: Session, market: EvalMarket, now: datetime) -> None:
    rules = Rules()
    run = market.pools[RUN_MINT]
    dud = market.pools[DUD_MINT]
    # Two days ago RUN was flagged, yesterday DUD; the latest scan found only a near miss.
    for at, pools in (
        (now - timedelta(days=2), [replace(run, created_at=now - timedelta(days=2, hours=10))]),
        (now - timedelta(days=1), [replace(dud, created_at=now - timedelta(days=1, hours=8))]),
        (now - timedelta(minutes=5), [market.pools[MEH_MINT]]),
    ):
        market.scan_pools_by_time = pools
        run_scan(session, market, at, ["solana"], rules, 3)
        paper_book.open_missing(session)
        if pools[0].symbol == "RUN":
            for hours, x in ((1, 2.3), (5, 6.0), (10, 3.9)):
                market.prices = {run.pool_address: replace(run, price_usd=0.004 * x)}
                paper_book.update(session, market, at + timedelta(hours=hours))
        if pools[0].symbol == "DUD":
            market.prices = {
                run.pool_address: replace(run, price_usd=0.004 * 3.5),
                dud.pool_address: replace(dud, price_usd=dud.price_usd * 0.4),
            }
            paper_book.update(session, market, at + timedelta(hours=2))
    market.prices = {run.pool_address: replace(run, price_usd=0.004 * 3.4)}
    paper_book.update(session, market, now - timedelta(hours=1))


def build(session: Session, now: datetime | None = None) -> EvalMarket:
    """Fill an empty database with the eval world. Returns the market stand-in."""
    now = now or datetime.now(UTC)
    market = EvalMarket(now)
    _health(session, coach_today())
    _market(session, market, now)
    return market
