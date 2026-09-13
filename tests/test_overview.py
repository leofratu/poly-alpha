"""Offline tests for the cross-market overview summary table."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from poly_alpha.adapters.registry import default_markets
from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
)
from poly_alpha.research.analyst import research_market
from poly_alpha.research.overview import build_overview, dimensions, overview_rows

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
ASSET = AssetRef(symbol="TEST", asset_class="prediction")
BOOK = (PriceLevel(0.55, 500.0), PriceLevel(0.50, 500.0))


def make_snapshot(
    *,
    market_id: str,
    yes_price: float = 0.60,
    no_price: float = 0.40,
    liquidity: float = 500.0,
    kind: DataSourceKind = DataSourceKind.REAL,
    asset_class: str = "prediction",
    orderbook: tuple[PriceLevel, ...] = BOOK,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        question=f"Will {market_id} resolve YES?",
        asset=AssetRef(symbol=market_id.upper(), asset_class=asset_class),
        yes_price=yes_price,
        no_price=no_price,
        liquidity=liquidity,
        volume=1000.0,
        provenance=Provenance(source="test-fixture", kind=kind, retrieved_at=NOW),
        orderbook=orderbook,
    )

