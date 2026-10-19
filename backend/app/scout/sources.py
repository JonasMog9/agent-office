"""Read-only market data: GeckoTerminal (CoinGecko's DEX data) for pools, GoPlus and RugCheck
for rug tests. Free public APIs, no keys, nothing that can trade (CLAUDE.md).

    GeckoTerminal  /networks/{net}/trending_pools   what's hot in the last hour
                   /networks/{net}/pools?sort=...   the day's biggest volume
                   /networks/{net}/tokens/{addr}/pools   one token's pools (for "check this")
    GoPlus         /api/v1/token_security/{chain_id}   EVM contract and holder report
    RugCheck       /v1/tokens/{mint}/report            Solana token report

GeckoTerminal allows about 30 calls a minute; a scan makes 3 per chain.
"""

from datetime import datetime

import httpx

from app.metrics.common import ScoreResult
from app.scout.rug import evm_checks, solana_checks
from app.scout.screen import Pool

GECKO = "https://api.geckoterminal.com/api/v2"
GOPLUS = "https://api.gopluslabs.io/api/v1"
RUGCHECK = "https://api.rugcheck.xyz/v1"
# Our chain names → GeckoTerminal network ids and GoPlus chain ids.
NETWORKS = {"solana": "solana", "base": "base", "eth": "eth"}
GOPLUS_CHAIN = {"base": "8453", "eth": "1"}
# Pools listed the other way round (the "base" token is SOL/ETH/a stablecoin) are skipped.
QUOTES = {"SOL", "WSOL", "ETH", "WETH", "USDC", "USDT", "USDS", "DAI", "CBBTC", "WBTC", "USD₮0"}


def _f(value: object) -> float | None:
    try:
        return None if value is None else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _i(value: object) -> int | None:
    f = _f(value)
    return None if f is None else int(f)


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def pools_from_gecko(payload: dict, chain: str) -> list[Pool]:
    """GeckoTerminal's JSON:API pool list → ``Pool``s (pure, so it's tested on saved data)."""
    tokens = {
        t["id"]: t.get("attributes") or {}
        for t in payload.get("included") or []
        if t.get("type") == "token"
    }
    out = []
    for item in payload.get("data") or []:
        a = item.get("attributes") or {}
        rel = item.get("relationships") or {}
        token_id = ((rel.get("base_token") or {}).get("data") or {}).get("id", "")
        token = tokens.get(token_id, {})
        address = token.get("address") or token_id.partition("_")[2]
        symbol = (token.get("symbol") or (a.get("name") or "?").split(" / ")[0]).strip()
        if not address or symbol.upper() in QUOTES:
            continue
        tx = (a.get("transactions") or {}).get("h24") or {}
        vol = a.get("volume_usd") or {}
        change = a.get("price_change_percentage") or {}
        out.append(
            Pool(
                chain=chain,
                pool_address=a.get("address") or item.get("id", "").partition("_")[2],
                token_address=address,
                symbol=symbol[:32],
                name=(token.get("name") or a.get("name") or symbol)[:80],
                dex=((rel.get("dex") or {}).get("data") or {}).get("id"),
                created_at=_time(a.get("pool_created_at")),
                price_usd=_f(a.get("base_token_price_usd")),
                fdv_usd=_f(a.get("fdv_usd")),
                market_cap_usd=_f(a.get("market_cap_usd")),
                liquidity_usd=_f(a.get("reserve_in_usd")),
                volume_usd={k: _f(vol.get(k)) for k in ("m5", "h1", "h6", "h24")},
                price_change_pct={k: _f(change.get(k)) for k in ("m5", "h1", "h6", "h24")},
                buys_h24=_i(tx.get("buys")),
                sells_h24=_i(tx.get("sells")),
                buyers_h24=_i(tx.get("buyers")),
                sellers_h24=_i(tx.get("sellers")),
            )
        )
    return out


class MarketData:
    def __init__(self, http: httpx.Client | None = None) -> None:
        self.http = http or httpx.Client(
            timeout=20, headers={"Accept": "application/json", "User-Agent": "agent-office-scout"}
        )

    def close(self) -> None:
        self.http.close()

    def _get(self, url: str, **params: str) -> dict:
        r = self.http.get(url, params=params or None)
        r.raise_for_status()
        return r.json()

    def scan_pools(self, chain: str) -> list[Pool]:
        """Pools worth screening on one chain: trending now, plus the day's top volume."""
        net = NETWORKS[chain]
        pools: list[Pool] = []
        for path, params in (
            (f"/networks/{net}/trending_pools", {"duration": "1h"}),
            (f"/networks/{net}/pools", {"sort": "h24_volume_usd_desc", "page": "1"}),
            (f"/networks/{net}/pools", {"sort": "h24_volume_usd_desc", "page": "2"}),
        ):
            data = self._get(GECKO + path, include="base_token", **params)
            pools += pools_from_gecko(data, chain)
        return pools

    def token_pools(self, chain: str, address: str) -> list[Pool]:
        net = NETWORKS[chain]
        data = self._get(f"{GECKO}/networks/{net}/tokens/{address}/pools", include="base_token")
        return [
            p for p in pools_from_gecko(data, chain) if p.token_address.lower() == address.lower()
        ]

    def pool_prices(self, chain: str, pool_addresses: list[str]) -> dict[str, Pool]:
        """Current numbers for up to 30 pools, keyed by pool address."""
        if not pool_addresses:
            return {}
        net = NETWORKS[chain]
        joined = ",".join(pool_addresses[:30])
        data = self._get(f"{GECKO}/networks/{net}/pools/multi/{joined}", include="base_token")
        return {p.pool_address: p for p in pools_from_gecko(data, chain)}

    def goplus(self, chain: str, address: str) -> dict | None:
        data = self._get(
            f"{GOPLUS}/token_security/{GOPLUS_CHAIN[chain]}", contract_addresses=address
        )
        result = data.get("result") or {}
        return result.get(address.lower()) or result.get(address)

    def rugcheck(self, mint: str) -> dict | None:
        return self._get(f"{RUGCHECK}/tokens/{mint}/report") or None

    def rug_test(self, pool: Pool) -> ScoreResult:
        if pool.chain == "solana":
            return solana_checks(self.rugcheck(pool.token_address), pool.pool_address, pool.dex)
        return evm_checks(self.goplus(pool.chain, pool.token_address), [pool.pool_address])


def main_pools(pools: list[Pool]) -> list[Pool]:
    """One pool per token: its deepest (a token can trade in several pools)."""
    best: dict[tuple[str, str], Pool] = {}
    for p in pools:
        key = (p.chain, p.token_address.lower())
        if key not in best or (p.liquidity_usd or 0) > (best[key].liquidity_usd or 0):
            best[key] = p
    return list(best.values())
