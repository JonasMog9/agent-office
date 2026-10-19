from app.scout.rug import evm_checks, solana_checks

POOL = "0xpool"


def safe_evm(**kw) -> dict:
    sec = {
        "is_open_source": "1",
        "is_honeypot": "0",
        "cannot_sell_all": "0",
        "buy_tax": "0",
        "sell_tax": "0.02",
        "is_mintable": "0",
        "owner_address": "0x0000000000000000000000000000000000000000",
        "hidden_owner": "0",
        "can_take_back_ownership": "0",
        "owner_change_balance": "0",
        "selfdestruct": "0",
        "is_proxy": "0",
        "is_blacklisted": "0",
        "transfer_pausable": "0",
        "creator_percent": "0.01",
        "lp_holders": [
            {
                "address": "0x000000000000000000000000000000000000dead",
                "percent": "0.97",
                "is_locked": 0,
            },
            {"address": "0xabc", "percent": "0.03", "is_locked": 0},
        ],
        "holders": [
            {"address": POOL, "percent": "0.20", "is_locked": 0},  # the pool itself
            {"address": "0x1", "percent": "0.05", "is_locked": 0},
            {"address": "0x2", "percent": "0.04", "is_locked": 0},
            {"address": "0x3", "percent": "0.03", "is_locked": 0},
        ],
    }
    return sec | kw


def failed(r):
    return {c.name for c in r.components if c.value == 0}


def test_a_clean_evm_token_passes():
    r = evm_checks(safe_evm(), [POOL])
    assert r.label == "pass", r.notes
    assert "12.0%" in next(c.note for c in r.components if c.name == "holders")


def test_honeypot_fails():
    assert "sellable" in failed(evm_checks(safe_evm(is_honeypot="1"), [POOL]))


def test_high_sell_tax_fails():
    assert "taxes" in failed(evm_checks(safe_evm(sell_tax="0.25"), [POOL]))


def test_mintable_with_an_owner_fails_but_renounced_passes():
    owned = safe_evm(is_mintable="1", owner_address="0xowner")
    assert "no_mint" in failed(evm_checks(owned, [POOL]))
    assert "no_mint" not in failed(evm_checks(safe_evm(is_mintable="1"), [POOL]))


def test_blacklist_only_matters_while_someone_owns_it():
    assert "no_owner_tricks" in failed(
        evm_checks(safe_evm(is_blacklisted="1", owner_address="0xowner"), [POOL])
    )
    assert "no_owner_tricks" not in failed(evm_checks(safe_evm(is_blacklisted="1"), [POOL]))


def test_unlocked_liquidity_fails():
    lp = [{"address": "0xdev", "percent": "1.0", "is_locked": 0}]
    assert "lp_locked" in failed(evm_checks(safe_evm(lp_holders=lp), [POOL]))


def test_whales_fail_but_the_pool_and_locks_do_not_count():
    holders = [
        {"address": POOL, "percent": "0.50", "is_locked": 0},
        {"address": "0xlock", "percent": "0.30", "is_locked": 1},
        {"address": "0xwhale", "percent": "0.35", "is_locked": 0},
    ]
    assert "holders" in failed(evm_checks(safe_evm(holders=holders), [POOL]))
    holders[2]["percent"] = "0.10"
    assert "holders" not in failed(evm_checks(safe_evm(holders=holders), [POOL]))


def test_missing_fields_fail_never_pass():
    r = evm_checks({"is_honeypot": "0"}, [POOL])
    assert r.label == "fail"
    assert {"verified", "taxes", "lp_locked", "holders", "creator", "no_owner_tricks"} <= failed(r)
    assert evm_checks(None).label == "fail"


def safe_sol(**kw) -> dict:
    report = {
        "mintAuthority": None,
        "freezeAuthority": None,
        "rugged": False,
        "markets": [{"pubkey": "POOL", "lp": {"lpLockedPct": 100, "lpLockedUSD": 300_000}}],
        "knownAccounts": {"VAULT": {"name": "Raydium", "type": "AMM"}},
        "topHolders": [
            {"address": "VAULT", "owner": "VAULT", "pct": 25.0},
            {"address": "h1", "owner": "w1", "pct": 4.0},
            {"address": "h2", "owner": "w2", "pct": 3.5},
        ],
        "transferFee": {"pct": 0},
        "risks": [{"name": "Low amount of LP Providers", "level": "warn"}],
    }
    return report | kw


def test_a_clean_solana_token_passes():
    r = solana_checks(safe_sol(), "POOL", "raydium")
    assert r.label == "pass", r.notes


def test_mint_or_freeze_authority_still_held_fails():
    assert "no_mint" in failed(solana_checks(safe_sol(mintAuthority="DevKey"), "POOL"))
    assert "no_freeze" in failed(solana_checks(safe_sol(freezeAuthority="DevKey"), "POOL"))


def test_authorities_can_sit_under_token():
    report = safe_sol()
    del report["mintAuthority"], report["freezeAuthority"]
    report["token"] = {"mintAuthority": None, "freezeAuthority": None}
    assert solana_checks(report, "POOL").label == "pass"
    del report["token"]
    assert {"no_mint", "no_freeze"} <= failed(solana_checks(report, "POOL"))


def test_unlocked_lp_fails_except_on_the_bonding_curve():
    report = safe_sol(markets=[{"pubkey": "POOL", "lp": {"lpLockedPct": 10}}])
    assert "lp_locked" in failed(solana_checks(report, "POOL", "raydium"))
    assert "lp_locked" not in failed(solana_checks(report, "POOL", "pump-fun"))


def test_concentrated_holders_fail():
    holders = [{"address": f"h{i}", "owner": f"w{i}", "pct": 6.0} for i in range(8)]
    assert "holders" in failed(solana_checks(safe_sol(topHolders=holders), "POOL"))


def test_danger_risks_and_rug_flags_fail():
    danger = [{"name": "Freeze Authority still enabled", "level": "danger"}]
    assert "no_danger" in failed(solana_checks(safe_sol(risks=danger), "POOL"))
    assert "not_rugged" in failed(solana_checks(safe_sol(rugged=True), "POOL"))


def test_missing_solana_report_fails():
    assert solana_checks(None).label == "fail"
    assert solana_checks({}).label == "fail"
