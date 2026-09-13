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
        liquidity=liquidity,
        volume=5000.0,
        provenance=Provenance(source="test-fixture", kind=kind, retrieved_at=NOW),
        orderbook=orderbook,
    )


def test_opportunity_is_real_tracks_provenance() -> None:
    real = rank_opportunities([research_market(make_snapshot(), now=NOW)])[0]
    fixture = rank_opportunities(
        [research_market(make_snapshot(kind=DataSourceKind.FIXTURE), now=NOW)]
    )[0]
    assert isinstance(real, Opportunity)
    assert real.is_real is True
    assert real.requires_real_data is False
    assert fixture.is_real is False
    assert fixture.requires_real_data is True


def test_negative_lower_bound_is_excluded() -> None:
    note = research_market(
        make_snapshot(
            yes_price=0.60,
            no_price=0.40,
            liquidity=1000.0,
            orderbook=NEGATIVE_BOOK,
        ),
        now=NOW,
    )
    assert note.edge.low <= 0.0
    assert rank_opportunities([note]) == []


def test_min_edge_low_threshold_is_strict() -> None:
    note = research_market(make_snapshot(), now=NOW)
    assert rank_opportunities([note], min_edge_low=note.edge.low) == []
    assert len(rank_opportunities([note], min_edge_low=note.edge.low - 0.001)) == 1


def test_require_real_filters_fixture_out() -> None:
    real = research_market(make_snapshot(market_id="real"), now=NOW)
    fixture = research_market(
        make_snapshot(market_id="fixture", kind=DataSourceKind.FIXTURE), now=NOW
    )
    both = rank_opportunities([real, fixture])
    assert {opportunity.note.market_id for opportunity in both} == {"real", "fixture"}
