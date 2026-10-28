from datetime import UTC, datetime

import httpx

from app.scout.sources import MarketData, history_from_gecko, pools_from_gecko


def gecko_pool(base_id: str, name: str, **attrs) -> dict:
    a = {
        "address": "POOL1",
        "name": name,
        "pool_created_at": "2026-10-19T02:00:00Z",
        "base_token_price_usd": "0.0042",
        "fdv_usd": "4200000",
        "market_cap_usd": None,
        "reserve_in_usd": "410000.5",
        "volume_usd": {"m5": "40000", "h1": "350000", "h6": "1800000", "h24": "3000000"},
        "price_change_percentage": {"m5": "1.1", "h1": "8.2", "h6": "60", "h24": "900"},
        "transactions": {"h24": {"buys": 9000, "sells": 6000, "buyers": 2500, "sellers": 1400}},
    } | attrs
    return {
        "id": "solana_POOL1",
        "type": "pool",
        "attributes": a,
        "relationships": {
            "base_token": {"data": {"id": base_id, "type": "token"}},
            "dex": {"data": {"id": "raydium", "type": "dex"}},
        },
    }


def test_parses_a_geckoterminal_pool_with_its_token():
    payload = {
        "data": [gecko_pool("solana_MINT1", "RUN / SOL")],
        "included": [
            {
                "id": "solana_MINT1",
                "type": "token",
                "attributes": {"address": "MINT1", "symbol": "RUN", "name": "Runner"},
            }
        ],
    }
    [p] = pools_from_gecko(payload, "solana")
    assert (p.token_address, p.symbol, p.name, p.dex) == ("MINT1", "RUN", "Runner", "raydium")
    assert p.created_at == datetime(2026, 10, 19, 2, tzinfo=UTC)
    assert p.liquidity_usd == 410000.5 and p.volume_usd["h24"] == 3_000_000
    assert p.price_change_pct["h1"] == 8.2 and p.market_cap_usd is None
    assert (p.buys_h24, p.buyers_h24, p.sellers_h24) == (9000, 2500, 1400)


def test_falls_back_to_the_relationship_id_and_pool_name():
    [p] = pools_from_gecko({"data": [gecko_pool("solana_MINT2", "PEPE2 / SOL")]}, "solana")
    assert (p.token_address, p.symbol) == ("MINT2", "PEPE2")


def test_skips_pools_listed_with_sol_or_a_stablecoin_as_the_base():
    payload = {"data": [gecko_pool("solana_So111", "SOL / USDC")]}
    assert pools_from_gecko(payload, "solana") == []


def test_bad_numbers_become_none():
    item = gecko_pool("solana_M", "X / SOL", reserve_in_usd="n/a", pool_created_at=None)
    [p] = pools_from_gecko({"data": [item]}, "solana")
    assert p.liquidity_usd is None and p.created_at is None


def ohlcv(*rows) -> dict:
    return {"data": {"type": "ohlcv_request_response", "attributes": {"ohlcv_list": list(rows)}}}


T = int(datetime(2026, 10, 19, 12, tzinfo=UTC).timestamp())


def test_candles_become_closes_at_the_end_of_each_candle_oldest_first():
    payload = ohlcv(
        [T + 900, 1.0, 9.0, 0.1, 1.2, 500],  # newest first; the 9.0 wick is ignored
        [T, 0.9, 1.1, 0.8, 1.0, 400],
        [T - 900, 0.9, 1.0, 0.8, None, 10],  # no close: skipped
        [T - 1800, 0.9],  # malformed: skipped
    )
    assert history_from_gecko(payload) == [
        (datetime(2026, 10, 19, 12, 15, tzinfo=UTC), 1.0),
        (datetime(2026, 10, 19, 12, 30, tzinfo=UTC), 1.2),
    ]
    assert history_from_gecko({}) == []


def test_price_history_pages_back_to_the_alert():
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(dict(request.url.params))
        before = request.url.params.get("before_timestamp")
        if before is None:
            return httpx.Response(
                200, json=ohlcv([T + 1800, 0, 0, 0, 3.0, 1], [T + 900, 0, 0, 0, 2.0, 1])
            )
        return httpx.Response(200, json=ohlcv([T, 0, 0, 0, 1.5, 1], [T - 900, 0, 0, 0, 1.1, 1]))

    src = MarketData(httpx.Client(transport=httpx.MockTransport(handler)))
    since = datetime.fromtimestamp(T, UTC)  # the alert
    got = src.price_history("solana", "POOL", since)
    assert [p for _, p in got] == [1.5, 2.0, 3.0]  # the candle that closed at the alert is out
    assert calls[0]["aggregate"] == "15" and calls[1]["before_timestamp"] == str(T + 900)
    assert len(calls) == 2  # the second page reached back past the alert
