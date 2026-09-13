"""Tests for the deterministic strategy comparison harness."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import pytest

from poly_alpha.backtesting.comparison import (
    MIN_EDGE,
    ResolvedMarket,
    compare_strategies,
)
from poly_alpha.contracts import AssetRef, DataSourceKind, MarketSnapshot, Provenance

PROVENANCE = Provenance(
    source="test",
    kind=DataSourceKind.FIXTURE,
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def make_market(market_id: str, yes_price: float, resolved_yes: bool) -> ResolvedMarket:
    snapshot = MarketSnapshot(
        market_id=market_id,
        question=f"Question {market_id}?",
        asset=AssetRef(symbol="TEST", asset_class="sports"),
        yes_price=yes_price,
        no_price=1.0 - yes_price,
        liquidity=1000.0,
        volume=500.0,
        provenance=PROVENANCE,
    )
    return ResolvedMarket(snapshot=snapshot, resolved_yes=resolved_yes)


MARKETS = [
    make_market("m1", 0.10, resolved_yes=False),
    make_market("m2", 0.08, resolved_yes=False),
    make_market("m3", 0.80, resolved_yes=True),
]

RESOLUTIONS = {"m1": False, "m2": False, "m3": True}


def oracle(resolutions: dict[str, bool]) -> Callable[[MarketSnapshot], float | None]:
    def strategy(snapshot: MarketSnapshot) -> float | None:
        return 1.0 if resolutions[snapshot.market_id] else 0.0

    return strategy


def constant_half(snapshot: MarketSnapshot) -> float | None:
    return 0.5


def always_skip(snapshot: MarketSnapshot) -> float | None:
    return None


def test_min_edge_constant() -> None:
    assert MIN_EDGE == 0.01


def test_oracle_profits_and_ranks_first() -> None:
    results = compare_strategies(
        MARKETS,
        {"oracle": oracle(RESOLUTIONS), "constant": constant_half},
    )
    assert [metrics.name for metrics in results] == ["oracle", "constant"]
    oracle_metrics = results[0]
    constant_metrics = results[1]
    assert oracle_metrics.trades == 2
    assert oracle_metrics.hit_rate == pytest.approx(1.0)
    assert oracle_metrics.total_pnl > 0.0
    assert oracle_metrics.roi > 0.0
    assert constant_metrics.trades == 1
    assert constant_metrics.hit_rate == pytest.approx(0.0)
    assert constant_metrics.total_pnl < 0.0
    assert constant_metrics.roi < 0.0


def test_trades_and_drawdown_bounds() -> None:
    results = compare_strategies(
        MARKETS,
        {"oracle": oracle(RESOLUTIONS), "constant": constant_half},
    )
    for metrics in results:
        assert 0.0 <= metrics.max_drawdown <= 1.0
        assert metrics.total_stake >= 0.0

