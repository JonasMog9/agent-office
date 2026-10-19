from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.scout.screen import Pool, Rules, screen

NOW = datetime(2026, 10, 19, 12, tzinfo=UTC)


def runner(**kw) -> Pool:
    """A 10-hour-old coin doing $3M on $400k liquidity, 2,500 buyers, still climbing."""
    base = Pool(
        chain="solana",
        pool_address="POOL",
        token_address="MINT",
        symbol="RUN",
        name="Runner",
        created_at=NOW - timedelta(hours=10),
        price_usd=0.004,
        fdv_usd=4_000_000,
        liquidity_usd=400_000,
        volume_usd={"m5": 40_000, "h1": 350_000, "h6": 1_800_000, "h24": 3_000_000},
        price_change_pct={"h1": 8, "h6": 60, "h24": 900},
        buys_h24=9_000,
        sells_h24=6_000,
        buyers_h24=2_500,
        sellers_h24=1_400,
    )
    return replace(base, **kw)


def comp(result, name):
    return next(c for c in result.components if c.name == name)


def test_a_young_coin_with_huge_real_volume_passes():
    r = screen(runner(), NOW)
    assert r.label == "pass", r.notes
    assert comp(r, "turnover").value == 7.5
    assert comp(r, "trade_size").value == 200  # $3M over 15,000 trades
    assert 70 <= r.value <= 100


def test_too_old_fails_even_with_volume():
    r = screen(runner(created_at=NOW - timedelta(hours=60)), NOW)
    assert r.label == "fail" and "young" in r.notes[0]


def test_low_volume_fails():
    r = screen(runner(volume_usd={"h1": 30_000, "h24": 400_000}), NOW)
    assert comp(r, "volume").note == "fail"


def test_wash_trading_big_average_trades_fail():
    # $3M from only 300 trades and 120 buyers: a few wallets churning
    r = screen(runner(buys_h24=150, sells_h24=150, buyers_h24=120, sellers_h24=100), NOW)
    assert comp(r, "trade_size").note == "fail"
    assert comp(r, "buyers").note == "fail"


def test_dead_coin_whose_volume_was_all_at_launch_fails():
    vol = {"h1": 20_000, "h6": 200_000, "h24": 3_000_000}
    r = screen(runner(volume_usd=vol), NOW)
    assert comp(r, "still_going").note == "fail"


def test_dumping_fails():
    r = screen(runner(price_change_pct={"h1": -35, "h6": -10}), NOW)
    assert comp(r, "change_1h").note == "fail"


def test_sellers_outnumbering_buyers_fails():
    r = screen(runner(buyers_h24=600, sellers_h24=1_200), NOW)
    assert comp(r, "buy_side").note == "fail"


def test_too_big_already_fails():
    assert comp(screen(runner(fdv_usd=90_000_000), NOW), "still_early").note == "fail"


def test_missing_numbers_fail_their_rule():
    r = screen(runner(buyers_h24=None, created_at=None), NOW)
    assert comp(r, "buyers").note == "no data"
    assert comp(r, "young").note == "no data"
    assert r.label == "fail"


def test_a_coin_under_six_hours_old_is_judged_on_its_one_hour_change():
    young = runner(
        created_at=NOW - timedelta(hours=3),
        price_change_pct={"h1": 15, "h6": None},
        volume_usd={"h1": 500_000, "h24": 1_200_000},
    )
    r = screen(young, NOW)
    assert comp(r, "change_6h").note == "pass"
    assert comp(r, "still_going").value == 1.25  # 500k last hour vs 400k/h average


def test_a_coin_under_an_hour_old_counts_as_still_going():
    r = screen(runner(created_at=NOW - timedelta(minutes=40), price_change_pct={"h1": 5}), NOW)
    assert comp(r, "still_going").note == "pass"


def test_rules_are_adjustable():
    strict = Rules(min_volume_h24=5_000_000)
    assert screen(runner(), NOW, strict).label == "fail"


def test_score_ranks_near_misses():
    hot = screen(runner(), NOW).value
    lukewarm = screen(runner(volume_usd={"h1": 60_000, "h24": 900_000}, buyers_h24=400), NOW).value
    assert hot > lukewarm > 0
