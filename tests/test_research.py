"""Tests for the offline, deterministic research engine."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
)
from poly_alpha.research import (
    ResearchNote,
    model_vs_market,
    research_market,
    research_markets,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
ASSET = AssetRef(symbol="TEST", asset_class="prediction")
YES_BOOK = (PriceLevel(0.65, 100.0), PriceLevel(0.60, 100.0))
NO_BOOK = (PriceLevel(0.40, 100.0), PriceLevel(0.35, 100.0))


def make_snapshot(
    *,
    market_id: str = "m1",
    yes_price: float | None = 0.60,
    no_price: float | None = 0.40,
    liquidity: float = 1000.0,
    kind: DataSourceKind = DataSourceKind.REAL,
    orderbook: tuple[PriceLevel, ...] = YES_BOOK,
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


def test_research_market_is_deterministic() -> None:
    first = research_market(make_snapshot(), now=NOW)
    second = research_market(make_snapshot(), now=NOW)
    assert first.model_yes.estimate == second.model_yes.estimate
    assert first.model_yes.basis == second.model_yes.basis
    assert first.summary == second.summary


def test_uncertainty_brackets_estimate() -> None:
    note = research_market(make_snapshot(), now=NOW)
    assert note.model_yes.low <= note.model_yes.estimate <= note.model_yes.high
    assert note.model_yes.contains(note.model_yes.estimate)


def test_uncertainty_widens_when_liquidity_drops() -> None:
    rich = research_market(make_snapshot(liquidity=2000.0), now=NOW)
    poor = research_market(make_snapshot(liquidity=20.0), now=NOW)
    assert poor.model_yes.width > rich.model_yes.width


def test_uncertainty_widens_when_book_is_thin() -> None:
    deep = research_market(make_snapshot(orderbook=(PriceLevel(0.6, 200.0),)), now=NOW)
    thin = research_market(make_snapshot(orderbook=(PriceLevel(0.6, 1.0),)), now=NOW)
    assert thin.model_yes.width > deep.model_yes.width


def test_claim_sources_are_non_empty() -> None:
    note = research_market(make_snapshot(), now=NOW)
    assert note.claims
    assert all(claim.sources for claim in note.claims)


def test_is_simulated_for_fixture_provenance() -> None:
    note = research_market(make_snapshot(kind=DataSourceKind.FIXTURE), now=NOW)
    assert note.is_simulated() is True
    assert DataSourceKind.FIXTURE in note.source_kinds()


def test_caveats_mention_non_real_data_and_advice() -> None:
    note = research_market(make_snapshot(kind=DataSourceKind.SIMULATED), now=NOW)
    assert any("simulat" in caveat.lower() for caveat in note.caveats)
    assert any("not investment advice" in caveat.lower() for caveat in note.caveats)

