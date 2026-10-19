"""Is this young coin a potential runner? A pure screen over one pool's market numbers.

The owner only wants to hear about a coin that is at most two days old and already trading
huge, real volume, and still going. Every rule must pass (a missing number fails its rule):

    rule          number                                      default
    young         hours since the pool was created            ≤ 48 h
    volume        24 h volume (USD)                           ≥ $1M
    liquidity     pool liquidity (USD)                        ≥ $75k
    buyers        distinct buying wallets in 24 h             ≥ 500
    turnover      24 h volume / liquidity                     ≥ 3×
    trade size    average USD per transaction                 ≤ $3,000  (wash-trading guard)
    still going   last hour's volume vs. the average hourly   ≥ 0.5×
                  volume since launch
    not dumping   price change over 1 h / 6 h                 ≥ −25% / ≥ −40%
    buy side      buyers / sellers                            ≥ 0.8
    still early   fully diluted value (USD)                   ≤ $30M

Passing the screen is not enough for an alert: the rug tests (``rug.py``) must pass too.
The ``value`` is a 0–100 runner score for ranking near misses: the mean of volume, buyers,
turnover and liquidity as multiples of their thresholds, capped at 3× (all exactly at the
threshold is 33, all at 3× or more is 100).
"""

from dataclasses import dataclass, field
from datetime import datetime

from app.metrics.common import Component, ScoreResult


@dataclass(frozen=True)
class Pool:
    """One DEX pool's market numbers, normalised from the data source."""

    chain: str  # "solana" | "base" | "eth"
    pool_address: str
    token_address: str
    symbol: str
    name: str
    dex: str | None = None
    created_at: datetime | None = None
    price_usd: float | None = None
    fdv_usd: float | None = None
    market_cap_usd: float | None = None
    liquidity_usd: float | None = None
    volume_usd: dict[str, float | None] = field(default_factory=dict)  # m5, h1, h6, h24
    price_change_pct: dict[str, float | None] = field(default_factory=dict)
    buys_h24: int | None = None
    sells_h24: int | None = None
    buyers_h24: int | None = None
    sellers_h24: int | None = None


@dataclass(frozen=True)
class Rules:
    max_age_h: float = 48
    min_volume_h24: float = 1_000_000
    min_liquidity: float = 75_000
    min_buyers_h24: int = 500
    min_turnover: float = 3.0
    max_avg_trade: float = 3_000
    min_pace: float = 0.5
    min_change_h1: float = -25
    min_change_h6: float = -40
    min_buyer_ratio: float = 0.8
    max_fdv: float = 30_000_000


DEFAULT_RULES = Rules()


def age_hours(pool: Pool, now: datetime) -> float | None:
    if pool.created_at is None:
        return None
    return max(0.0, (now - pool.created_at).total_seconds() / 3600)


def _ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or b <= 0:
        return None
    return a / b


def screen(pool: Pool, now: datetime, rules: Rules = DEFAULT_RULES) -> ScoreResult:
    vol = pool.volume_usd.get("h24")
    age = age_hours(pool, now)
    trades = (pool.buys_h24 or 0) + (pool.sells_h24 or 0)
    hours = None if age is None else min(max(age, 1 / 60), 24)  # hours the 24 h volume covers
    pace = _ratio(pool.volume_usd.get("h1"), None if vol is None or hours is None else vol / hours)
    if pace is not None and hours is not None and hours < 1:
        pace = 1.0  # younger than an hour: the last hour is its whole life

    # (name, value, threshold, passes)
    checks: list[tuple[str, float | None, float, bool | None]] = [
        ("young", age, rules.max_age_h, None if age is None else age <= rules.max_age_h),
        ("volume", vol, rules.min_volume_h24, None if vol is None else vol >= rules.min_volume_h24),
        (
            "liquidity",
            pool.liquidity_usd,
            rules.min_liquidity,
            None if pool.liquidity_usd is None else pool.liquidity_usd >= rules.min_liquidity,
        ),
        (
            "buyers",
            pool.buyers_h24,
            rules.min_buyers_h24,
            None if pool.buyers_h24 is None else pool.buyers_h24 >= rules.min_buyers_h24,
        ),
    ]
    turnover = _ratio(vol, pool.liquidity_usd)
    avg_trade = _ratio(vol, trades or None)
    buyer_ratio = _ratio(pool.buyers_h24, pool.sellers_h24)
    ch1, ch6 = pool.price_change_pct.get("h1"), pool.price_change_pct.get("h6")
    ok6 = _ge(ch6, rules.min_change_h6)
    if ch6 is None and age is not None and age < 6:
        ok6 = True  # too young for a 6 h change: judged on the 1 h change alone
    checks += [
        ("turnover", turnover, rules.min_turnover, _ge(turnover, rules.min_turnover)),
        ("trade_size", avg_trade, rules.max_avg_trade, _le(avg_trade, rules.max_avg_trade)),
        ("still_going", pace, rules.min_pace, _ge(pace, rules.min_pace)),
        ("change_1h", ch1, rules.min_change_h1, _ge(ch1, rules.min_change_h1)),
        ("change_6h", ch6, rules.min_change_h6, ok6),
        ("buy_side", buyer_ratio, rules.min_buyer_ratio, _ge(buyer_ratio, rules.min_buyer_ratio)),
        ("still_early", pool.fdv_usd, rules.max_fdv, _le(pool.fdv_usd, rules.max_fdv)),
    ]
    components = [
        Component(
            name,
            None if value is None else round(value, 2),
            baseline=threshold,
            note="pass" if ok else ("no data" if ok is None else "fail"),
        )
        for name, value, threshold, ok in checks
    ]
    failed = [c.name for c in components if c.note != "pass"]
    multiples = [
        _ratio(vol, rules.min_volume_h24),
        _ratio(pool.buyers_h24, rules.min_buyers_h24),
        _ratio(turnover, rules.min_turnover),
        _ratio(pool.liquidity_usd, rules.min_liquidity),
    ]
    score = 100 * sum(min(m or 0, 3) / 3 for m in multiples) / len(multiples)
    notes = [f"failed: {', '.join(failed)}"] if failed else []
    return ScoreResult(round(score), components, notes, "pass" if not failed else "fail")


def _ge(x: float | None, threshold: float) -> bool | None:
    return None if x is None else x >= threshold


def _le(x: float | None, threshold: float) -> bool | None:
    return None if x is None else x <= threshold
