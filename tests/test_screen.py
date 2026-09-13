"""Tests for conservative, provenance-aware opportunity screening."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
)
from poly_alpha.research import research_market
from poly_alpha.research.screen import (
    Opportunity,
    rank_opportunities,
    screen_markets,
    summarize,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
ASSET = AssetRef(symbol="TEST", asset_class="prediction")
DEEP_BOOK = (PriceLevel(0.85, 500.0), PriceLevel(0.80, 500.0))
HIGH_BOOK = (PriceLevel(0.90, 500.0), PriceLevel(0.85, 500.0))
LOW_EDGE_BOOK = (PriceLevel(0.80, 500.0), PriceLevel(0.75, 500.0))
NEGATIVE_BOOK = (PriceLevel(0.65, 100.0), PriceLevel(0.60, 100.0))


def make_snapshot(
    *,
    market_id: str = "m1",
    yes_price: float = 0.85,
    no_price: float = 0.15,
    liquidity: float = 500.0,
    kind: DataSourceKind = DataSourceKind.REAL,
    orderbook: tuple[PriceLevel, ...] = DEEP_BOOK,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        question="Will the test event resolve YES?",
        asset=ASSET,
        yes_price=yes_price,
        no_price=no_price,
