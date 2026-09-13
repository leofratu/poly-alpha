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

    filtered = rank_opportunities([real, fixture], require_real=True)
    assert [opportunity.note.market_id for opportunity in filtered] == ["real"]
    assert all(opportunity.is_real for opportunity in filtered)


def test_ordering_is_deterministic_with_market_id_tie_break() -> None:
    high = make_snapshot(market_id="c", yes_price=0.90, no_price=0.10, orderbook=HIGH_BOOK)
    tie_a = make_snapshot(market_id="a")
    tie_b = make_snapshot(market_id="b")
    low = make_snapshot(market_id="d", yes_price=0.80, no_price=0.20, orderbook=LOW_EDGE_BOOK)
    notes = [research_market(snapshot, now=NOW) for snapshot in (tie_b, low, tie_a, high)]

    ranked = rank_opportunities(notes)
    assert [opportunity.note.market_id for opportunity in ranked] == ["c", "a", "b", "d"]
    scores = [opportunity.score for opportunity in ranked]
    assert scores == sorted(scores, reverse=True)
    assert scores[1] == scores[2]


def test_screen_markets_matches_research_then_rank() -> None:
    snapshots = [make_snapshot(market_id="x"), make_snapshot(market_id="y", yes_price=0.80)]
    screened = screen_markets(snapshots, now=NOW)
    notes = [research_market(snapshot, now=NOW) for snapshot in snapshots]
    expected = rank_opportunities(notes)
    assert [opportunity.note.market_id for opportunity in screened] == [
        opportunity.note.market_id for opportunity in expected
    ]


def test_summarize_empty_returns_zeroes() -> None:
    assert summarize([]) == {
        "count": 0,
        "real_count": 0,
        "mean_edge_low": 0.0,
        "max_edge_low": 0.0,
    }


def test_summarize_counts_and_edge_statistics() -> None:
    real = research_market(make_snapshot(market_id="real"), now=NOW)
    fixture = research_market(
        make_snapshot(
            market_id="fixture",
            yes_price=0.90,
            no_price=0.10,
            orderbook=HIGH_BOOK,
            kind=DataSourceKind.FIXTURE,
        ),
        now=NOW,
    )
    opportunities = rank_opportunities([real, fixture])
    stats = summarize(opportunities)

    edge_lows = [opportunity.edge_low for opportunity in opportunities]
    assert stats["count"] == 2
    assert stats["real_count"] == 1
    assert stats["mean_edge_low"] == pytest.approx(sum(edge_lows) / len(edge_lows))
    assert stats["max_edge_low"] == pytest.approx(max(edge_lows))
