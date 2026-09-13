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


def test_model_vs_market_positive_for_yes_imbalance() -> None:
    note = research_market(make_snapshot(), now=NOW)
    edge = model_vs_market(note)
    assert edge is not None
    assert edge > 0.0
    assert edge == note.model_yes.estimate - note.market_implied_yes


def test_model_vs_market_negative_for_no_imbalance() -> None:
    note = research_market(
        make_snapshot(yes_price=0.40, no_price=0.60, orderbook=NO_BOOK), now=NOW
    )
    edge = model_vs_market(note)
    assert edge is not None
    assert edge < 0.0


def test_model_vs_market_none_without_market_price() -> None:
    note = research_market(make_snapshot(yes_price=None, no_price=None), now=NOW)
    assert note.market_implied_yes is None
    assert model_vs_market(note) is None


def test_shin_debiasing_used_without_orderbook() -> None:
    note = research_market(make_snapshot(orderbook=()), now=NOW)
    assert "shin" in note.model_yes.basis.lower()
    assert any("Shin" in claim.text for claim in note.claims)


def test_research_markets_preserves_order() -> None:
    notes = research_markets(
        [make_snapshot(market_id="a"), make_snapshot(market_id="b")], now=NOW
    )
    assert [note.market_id for note in notes] == ["a", "b"]
    assert all(isinstance(note, ResearchNote) for note in notes)


def test_generated_at_falls_back_to_retrieved_at_then_fixed() -> None:
    explicit = research_market(make_snapshot(), now=NOW)
    assert explicit.generated_at == NOW
    retrieved = research_market(make_snapshot())
    assert retrieved.generated_at == NOW
    no_time = replace(
        make_snapshot(),
        provenance=Provenance(source="test-fixture", kind=DataSourceKind.FIXTURE),
    )
    assert research_market(no_time).generated_at.year == 1970
