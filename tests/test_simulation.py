"""Tests for the deterministic paper-portfolio simulation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

import pytest

from poly_alpha.backtesting.comparison import ResolvedMarket
from poly_alpha.backtesting.simulation import (
    CAVEAT,
    SimulationResult,
    simulate_portfolio,
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

