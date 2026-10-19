"""Rug tests: can the people behind this coin take your money? Pure functions over the
security reports of GoPlus (EVM chains) and RugCheck (Solana).

Every test must pass for an alert, and a test without data fails: "we couldn't check" is
never treated as "safe".

EVM (Base, Ethereum), from GoPlus token security:

    verified      contract source is published
    sellable      not a honeypot, and holders can sell everything
    taxes         buy and sell tax ≤ 10%
    no_mint       nobody can mint more (not mintable, or the owner has renounced)
    no_owner_tricks  no hidden owner, no reclaiming ownership, no editing balances, no
                  self-destruct, not upgradeable; no blacklist or pause unless renounced
    lp_locked     ≥ 90% of the liquidity tokens locked or burned
    holders       top 10 holders own ≤ 30% (not counting the pool, locks and burn addresses)
    creator       creator holds ≤ 5%

Solana, from a RugCheck report:

    no_mint       mint authority revoked
    no_freeze     freeze authority revoked (else they can freeze your tokens)
    not_rugged    RugCheck hasn't flagged it as rugged
    lp_locked     ≥ 90% of the main pool's liquidity locked or burned (a coin still on its
                  pump.fun bonding curve has no LP that can be pulled, so it passes)
    holders       top 10 holders own ≤ 30% (not counting pools and other known accounts)
    transfer_fee  ≤ 10%
    no_danger     no "danger"-level risk in RugCheck's own list
"""

from collections.abc import Iterable

from app.metrics.common import Component, ScoreResult

MAX_TAX = 0.10
MIN_LP_LOCKED = 0.90
MAX_TOP10 = 0.30
MAX_CREATOR = 0.05
BURN = {
    "0x0000000000000000000000000000000000000000",
    "0x000000000000000000000000000000000000dead",
}
BONDING_CURVE_DEXES = {"pump-fun", "pumpfun"}


def _flag(value: object) -> bool | None:
    """GoPlus booleans are "1"/"0" strings; anything else is unknown."""
    if value in ("1", 1):
        return True
    if value in ("0", 0):
        return False
    return None


def _num(value: object) -> float | None:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _result(checks: list[tuple[str, bool | None, str]]) -> ScoreResult:
    components = [
        Component(name, 1.0 if ok else 0.0, note=("pass: " if ok else "FAIL: ") + why)
        for name, ok, why in checks
    ]
    failed = [n for n, ok, _ in checks if not ok]
    passed = len(checks) - len(failed)
    notes = [f"failed: {', '.join(failed)}"] if failed else []
    return ScoreResult(
        round(100 * passed / len(checks)), components, notes, "fail" if failed else "pass"
    )


def _pct(x: float) -> str:
    return f"{x * 100:.1f}%"


def evm_checks(sec: dict | None, pool_addresses: Iterable[str] = ()) -> ScoreResult:
    """``sec`` is GoPlus' result for one token; ``pool_addresses`` are its DEX pools."""
    if not sec:
        return _result([("report", None, "no security report available")])
    owner = (sec.get("owner_address") or "").lower()
    renounced = owner == "" or owner in BURN
    checks: list[tuple[str, bool | None, str]] = []

    verified = _flag(sec.get("is_open_source"))
    checks.append(("verified", verified, "source published" if verified else "source not verified"))

    honeypot, cannot_sell = _flag(sec.get("is_honeypot")), _flag(sec.get("cannot_sell_all"))
    sellable = honeypot is False and cannot_sell is not True
    checks.append(("sellable", sellable, "can be sold" if sellable else "honeypot or sell limits"))

    buy, sell = _num(sec.get("buy_tax")), _num(sec.get("sell_tax"))
    taxes_ok = buy is not None and sell is not None and buy <= MAX_TAX and sell <= MAX_TAX
    why = "tax unknown" if buy is None or sell is None else f"buy {_pct(buy)}, sell {_pct(sell)}"
    checks.append(("taxes", taxes_ok, why))

    mintable = _flag(sec.get("is_mintable"))
    no_mint = mintable is False or (mintable is True and renounced)
    checks.append(("no_mint", no_mint, "supply fixed" if no_mint else "owner can mint more"))

    tricks = [
        k
        for k in ("hidden_owner", "can_take_back_ownership", "owner_change_balance", "selfdestruct")
        if _flag(sec.get(k)) is not False
    ]
    if _flag(sec.get("is_proxy")) is not False:
        tricks.append("is_proxy")
    if not renounced:
        tricks += [k for k in ("is_blacklisted", "transfer_pausable") if _flag(sec.get(k))]
    checks.append(("no_owner_tricks", not tricks, ", ".join(tricks) or "none found"))

    lp = sec.get("lp_holders") or []
    locked = sum(
        _num(h.get("percent")) or 0
        for h in lp
        if h.get("is_locked") in (1, "1") or (h.get("address") or "").lower() in BURN
    )
    checks.append(
        (
            "lp_locked",
            bool(lp) and locked >= MIN_LP_LOCKED,
            f"{_pct(locked)} locked or burned" if lp else "no LP data",
        )
    )

    skip = BURN | {a.lower() for a in pool_addresses}
    holders = sec.get("holders") or []
    top = [
        _num(h.get("percent")) or 0
        for h in holders
        if (h.get("address") or "").lower() not in skip and h.get("is_locked") not in (1, "1")
    ][:10]
    top10 = sum(top)
    checks.append(
        (
            "holders",
            bool(holders) and top10 <= MAX_TOP10,
            f"top 10 own {_pct(top10)}" if holders else "no holder data",
        )
    )

    creator = _num(sec.get("creator_percent"))
    checks.append(
        (
            "creator",
            creator is not None and creator <= MAX_CREATOR,
            "creator share unknown" if creator is None else f"creator holds {_pct(creator)}",
        )
    )
    return _result(checks)


def _authority(report: dict, key: str) -> tuple[bool, object]:
    """(found, value) from the report's top level or its ``token`` section."""
    if key in report:
        return True, report[key]
    token = report.get("token") or {}
    if key in token:
        return True, token[key]
    return False, None


def solana_checks(
    report: dict | None, pool_address: str | None = None, dex: str | None = None
) -> ScoreResult:
    """``report`` is RugCheck's full token report."""
    if not report:
        return _result([("report", None, "no RugCheck report available")])
    checks: list[tuple[str, bool | None, str]] = []
    for key, name, what in (
        ("mintAuthority", "no_mint", "mint"),
        ("freezeAuthority", "no_freeze", "freeze"),
    ):
        found, value = _authority(report, key)
        ok = found and value is None
        why = f"{what} authority " + ("unknown" if not found else "revoked" if ok else "still held")
        checks.append((name, ok, why))

    rugged = report.get("rugged")
    checks.append(
        (
            "not_rugged",
            rugged is False,
            "flagged as rugged" if rugged else "not flagged" if rugged is False else "unknown",
        )
    )

    markets = report.get("markets") or []
    main = next((m for m in markets if pool_address and m.get("pubkey") == pool_address), None)
    if main is None and markets:
        main = max(markets, key=lambda m: _num((m.get("lp") or {}).get("lpLockedUSD")) or 0)
    lp_pct = _num(((main or {}).get("lp") or {}).get("lpLockedPct"))
    if (dex or "").lower() in BONDING_CURVE_DEXES:
        checks.append(("lp_locked", True, "on the bonding curve: no LP to pull"))
    else:
        checks.append(
            (
                "lp_locked",
                lp_pct is not None and lp_pct / 100 >= MIN_LP_LOCKED,
                "no LP data" if lp_pct is None else f"{lp_pct:.1f}% locked or burned",
            )
        )

    known = set(report.get("knownAccounts") or {})
    if pool_address:
        known.add(pool_address)
    holders = report.get("topHolders") or []
    top = [
        (_num(h.get("pct")) or 0) / 100
        for h in holders
        if h.get("address") not in known and h.get("owner") not in known
    ][:10]
    top10 = sum(top)
    checks.append(
        (
            "holders",
            bool(holders) and top10 <= MAX_TOP10,
            f"top 10 own {_pct(top10)}" if holders else "no holder data",
        )
    )

    fee = _num((report.get("transferFee") or {}).get("pct")) or 0.0
    checks.append(("transfer_fee", fee <= MAX_TAX * 100, f"{fee:.1f}% transfer fee"))

    danger = [r.get("name", "?") for r in report.get("risks") or [] if r.get("level") == "danger"]
    checks.append(("no_danger", not danger, ", ".join(danger) or "none"))

    result = _result(checks)
    insiders = report.get("graphInsidersDetected")
    if insiders:
        result.notes.append(f"RugCheck sees {insiders} insider wallet groups")
    return result
