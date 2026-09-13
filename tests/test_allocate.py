"""Offline, deterministic tests for budgeted portfolio allocation."""

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
from poly_alpha.portfolio.allocate import Allocation, AllocationPlan, allocate
from poly_alpha.portfolio.sizing import kelly_fraction
from poly_alpha.research import research_market
from poly_alpha.research.screen import Opportunity

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
ASSET = AssetRef(symbol="TEST", asset_class="prediction")
DEEP_BOOK = (PriceLevel(0.85, 500.0), PriceLevel(0.80, 500.0))


def make_opportunity(
    market_id: str,
    *,
    yes_price: float = 0.85,
    no_price: float = 0.15,
    liquidity: float = 500.0,
    orderbook: tuple[PriceLevel, ...] = DEEP_BOOK,
) -> Opportunity:
    snapshot = MarketSnapshot(
        market_id=market_id,
        question="Will the test event resolve YES?",
        asset=ASSET,
        yes_price=yes_price,
        no_price=no_price,
        liquidity=liquidity,
        volume=5000.0,
        provenance=Provenance(source="test-fixture", kind=DataSourceKind.REAL, retrieved_at=NOW),
        orderbook=orderbook,
    )
    note = research_market(snapshot, now=NOW)
    return Opportunity(
