"""Tests for the named-strategy library used by the comparison harness."""

from __future__ import annotations

from datetime import UTC, datetime

from poly_alpha.adapters.fixtures import fixture_adapter
from poly_alpha.backtesting.comparison import ResolvedMarket, compare_strategies
from poly_alpha.backtesting.strategies import (
    constant_half,
    default_strategies,
    describe,
    market_implied,
    shin_debiased,
    uncertainty_gated,
)
from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
STRATEGY_NAMES = {
    "market_implied",
    "shin_debiased",
    "constant_half",
    "uncertainty_gated",
}


def make_snapshot(
    *,
    market_id: str = "m1",
    question: str = "Will the test event resolve YES?",
    yes_price: float | None = 0.60,
    no_price: float | None = 0.40,
    liquidity: float = 1000.0,
    category_hint: str = "prediction",
    orderbook: tuple[PriceLevel, ...] = (),
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        question=question,
