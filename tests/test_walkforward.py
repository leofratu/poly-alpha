"""Tests for the deterministic walk-forward paper backtest."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import pytest

from poly_alpha.adapters.history import MarketHistory
from poly_alpha.backtesting.walkforward import (
    CAVEAT,
    WalkForwardResult,
    walk_forward,
)
from poly_alpha.contracts import AssetRef, DataSourceKind, MarketSnapshot, Provenance

PROVENANCE = Provenance(
    source="test",
    kind=DataSourceKind.FIXTURE,
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def make_snapshot(market_id: str, yes_price: float) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        question=f"Question {market_id}?",
        asset=AssetRef(symbol="TEST", asset_class="sports"),
        yes_price=yes_price,
        no_price=1.0 - yes_price,
        liquidity=1000.0,
        volume=500.0,
        provenance=PROVENANCE,
    )


def make_history(market_id: str, yes_prices: Sequence[float]) -> MarketHistory:
    snapshots = tuple(make_snapshot(market_id, yes_price) for yes_price in yes_prices)
    return MarketHistory(
        asset=snapshots[0].asset,
        snapshots=snapshots,
        provenance=PROVENANCE,
    )


