"""A stand-in for ``MarketData``: scripted pools and rug results, no network."""

from app.metrics.common import Component, ScoreResult
from app.scout.screen import Pool


def rug(passed: bool) -> ScoreResult:
    c = Component(
        "lp_locked",
        1.0 if passed else 0.0,
        note="pass: 100.0% locked or burned" if passed else "FAIL: no LP data",
    )
    return ScoreResult(
        100 if passed else 0,
        [c],
        [] if passed else ["failed: lp_locked"],
        "pass" if passed else "fail",
    )


class FakeMarket:
    def __init__(
        self, pools: dict[str, list[Pool]], rug_pass: dict[str, bool] | None = None
    ) -> None:
        self.pools = pools
        self.rug_pass = rug_pass or {}
        self.rug_calls: list[str] = []
        self.down: set[str] = set()

    def scan_pools(self, chain: str) -> list[Pool]:
        if chain in self.down:
            raise ConnectionError("down")
        return self.pools.get(chain, [])

    def token_pools(self, chain: str, address: str) -> list[Pool]:
        return [p for p in self.pools.get(chain, []) if p.token_address == address]

    def rug_test(self, pool: Pool) -> ScoreResult:
        self.rug_calls.append(pool.symbol)
        return rug(self.rug_pass.get(pool.symbol, True))
