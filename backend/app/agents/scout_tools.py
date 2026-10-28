"""The Market Scout's tools. Every number comes from the scan (``app.scout``); the Scout only
explains it (CLAUDE.md). Read-only: nothing here can trade, and there is no wallet.
"""

import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.agents.loop import Tool
from app.db.models import ScoutAlert, ScoutScan
from app.metrics.common import ScoreResult
from app.scout import paper_book
from app.scout.scan import result_from_dict
from app.scout.screen import Pool, Rules, age_hours, screen
from app.scout.sources import NETWORKS, MarketData, main_pools

CHAINS = list(NETWORKS)
EVM_ADDRESS = re.compile(r"^0x[0-9a-fA-F]{40}$")
SOLANA_ADDRESS = re.compile(r"^[1-9A-HJ-NP-Za-km-z]{32,44}$")


def usd(x: float | None) -> str | None:
    """Money as it's read: $3.2M, $412k, $950, $0.0042."""
    if x is None:
        return None
    a = abs(x)
    if a >= 1e9:
        return f"${x / 1e9:.1f}B"
    if a >= 1e6:
        return f"${x / 1e6:.1f}M"
    if a >= 1e3:
        return f"${x / 1e3:.0f}k"
    if a >= 1:
        return f"${x:.0f}"
    return f"${x:.2g}" if x else "$0"


def dexscreener_url(chain: str, pool_address: str) -> str:
    return f"https://dexscreener.com/{'ethereum' if chain == 'eth' else chain}/{pool_address}"


def market_view(pool: Pool, market: ScoreResult, now: datetime) -> dict:
    age = age_hours(pool, now)
    v = pool.volume_usd
    return {
        "symbol": pool.symbol,
        "name": pool.name,
        "chain": pool.chain,
        "token_address": pool.token_address,
        "age": None if age is None else (f"{age:.0f} h" if age >= 1 else f"{age * 60:.0f} min"),
        "volume_24h": usd(v.get("h24")),
        "volume_last_hour": usd(v.get("h1")),
        "liquidity": usd(pool.liquidity_usd),
        "fdv": usd(pool.fdv_usd),
        "price": usd(pool.price_usd),
        "buyers_24h": pool.buyers_h24,
        "sellers_24h": pool.sellers_h24,
        "price_change_1h_pct": pool.price_change_pct.get("h1"),
        "price_change_6h_pct": pool.price_change_pct.get("h6"),
        "runner_score_0_100": market.value,
        "market_screen": market.label,
        "market_rules": [
            {"rule": c.name, "value": c.value, "threshold": c.baseline, "result": c.note}
            for c in market.components
        ],
        "chart": dexscreener_url(pool.chain, pool.pool_address),
    }


def rug_view(rug: ScoreResult) -> dict:
    return {
        "rug_tests": rug.label,
        "tests": [{"test": c.name, "result": c.note} for c in rug.components],
        "notes": rug.notes,
    }


def latest_scan(session: Session, now: datetime) -> dict:
    last = session.scalar(select(ScoutScan).order_by(ScoutScan.ran_at.desc()))
    day = now - timedelta(days=1)
    scans_24h = session.scalar(select(func.count()).where(ScoutScan.ran_at >= day)) or 0
    alerts = session.scalars(
        select(ScoutAlert)
        .where(ScoutAlert.alerted_at >= now - timedelta(days=7))
        .order_by(ScoutAlert.alerted_at.desc())
    ).all()
    if last is None:
        return {"note": "No scan has run yet; the first one runs a minute after startup."}
    return {
        "last_scan": last.ran_at,
        "scans_last_24h": scans_24h,
        "pools_looked_at": last.pools_seen,
        "coins_under_48h": last.young,
        "passed_market_screen": last.screened,
        "near_misses": [
            m | {"volume_h24_usd": usd(m.get("volume_h24_usd"))} for m in last.near_misses
        ],
        "errors": last.errors,
        "alerts_last_7_days": [
            {
                "symbol": a.symbol,
                "chain": a.chain,
                "when": a.alerted_at,
                "fdv_then": usd(a.fdv_usd),
                "volume_24h_then": usd(a.volume_h24_usd),
            }
            for a in alerts
        ],
    }


def guess_chains(address: str, chain: str) -> list[str]:
    if chain in CHAINS:
        return [chain]
    if EVM_ADDRESS.match(address):
        return ["base", "eth"]
    if SOLANA_ADDRESS.match(address):
        return ["solana"]
    raise ValueError("That doesn't look like a Solana or EVM (0x…) token address.")


def check_token(src: MarketData, address: str, chain: str, now: datetime, rules: Rules) -> dict:
    address = address.strip()
    for c in guess_chains(address, chain):
        pools = main_pools(src.token_pools(c, address))
        if pools:
            pool = pools[0]
            market = screen(pool, now, rules)
            return market_view(pool, market, now) | rug_view(src.rug_test(pool))
    raise LookupError("No trading pool found for that token on Solana, Base or Ethereum.")


def scout_tools(
    session_factory: Callable[[], Session],
    src_factory: Callable[[], MarketData],
    rules: Rules,
    now: Callable[[], datetime] = lambda: datetime.now(UTC),
    on_books: Callable[[dict[str, dict]], None] | None = None,
) -> list[Tool]:
    """The Scout's tools. ``on_books`` hears the strategy totals whenever the paper trades
    are read, so the Paper Trader can bring them over in the office."""

    def scan_tool(args: dict) -> dict:
        with session_factory() as session:
            return latest_scan(session, now())

    def check_tool(args: dict) -> dict:
        src = src_factory()
        try:
            return check_token(src, args["address"], args["chain"], now(), rules)
        finally:
            close = getattr(src, "close", None)
            if close:
                close()

    def paper_tool(args: dict) -> dict:
        with session_factory() as session:
            if on_books:
                on_books(paper_book.summaries(session))
            return paper_book.book(session)

    return [
        Tool(
            "paper_trades",
            "The paper-trading book: three strategies (Quick 2×, Runner, Moon bag), each with "
            "a pretend $10 trade on every alert and its own fixed selling rules. Per strategy: "
            "its rules, win rate, total profit/loss, best and worst, open trades, recent closes.",
            {},
            [],
            paper_tool,
            "Checking paper trades",
        ),
        Tool(
            "latest_scan",
            "The latest market scan: how many coins it looked at, how many are under 48 h "
            "old, the closest near misses and the rules they failed, and the potential-runner "
            "alerts of the last 7 days.",
            {},
            [],
            scan_tool,
            "Checking the scanner",
        ),
        Tool(
            "check_token",
            "Run the market screen and the rug tests on one token the owner names by its "
            "contract address.",
            {
                "address": {"type": "string", "description": "Token contract / mint address."},
                "chain": {"type": "string", "enum": [*CHAINS, "auto"]},
            },
            ["address", "chain"],
            check_tool,
            "Running rug tests",
        ),
    ]


def alert_view(alert: ScoutAlert) -> dict:
    """An alert's stored numbers, laid out like ``check_token`` output."""
    d = alert.details
    fields = {k: v for k, v in d["pool"].items() if k in Pool.__dataclass_fields__}
    created = fields.get("created_at")
    fields["created_at"] = datetime.fromisoformat(created) if created else None
    when = alert.alerted_at if alert.alerted_at.tzinfo else alert.alerted_at.replace(tzinfo=UTC)
    return market_view(Pool(**fields), result_from_dict(d["market"]), when) | rug_view(
        result_from_dict(d["rug"])
    )
