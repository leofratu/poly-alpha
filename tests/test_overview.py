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


def test_one_row_per_snapshot() -> None:
    snapshots = default_markets()
    overviews = build_overview(snapshots, now=NOW)
    assert len(overviews) == len(snapshots)
    assert {row.market_id for row in overviews} == {snap.market_id for snap in snapshots}


def test_ordering_is_deterministic_with_market_id_tie_break() -> None:
    tie_a = make_snapshot(market_id="a")
    tie_b = make_snapshot(market_id="b")
    empty_prices = make_snapshot(market_id="c", yes_price=0.70, no_price=0.30)
    snapshots = [tie_b, empty_prices, tie_a]

    first = build_overview(snapshots, now=NOW)
    second = build_overview(snapshots, now=NOW)
    assert first == second

    edges = [row.edge for row in first]
    assert edges == sorted(edges, key=abs, reverse=True)
    tie_edges = {row.edge for row in first if row.market_id in {"a", "b"}}
    assert len(tie_edges) == 1
    ids = [row.market_id for row in first]
    assert ids.index("a") < ids.index("b")


def test_edge_equals_model_minus_implied() -> None:
    overviews = build_overview([make_snapshot(market_id="m1")], now=NOW)
    row = overviews[0]
    assert row.implied_yes is not None
    assert row.edge == pytest.approx(row.model_yes - row.implied_yes)


def test_uncertainty_width_equals_high_minus_low() -> None:
    snapshot = make_snapshot(market_id="m1")
    row = build_overview([snapshot], now=NOW)[0]
    note = research_market(snapshot, now=NOW)
    assert row.uncertainty_width == pytest.approx(note.model_yes.high - note.model_yes.low)
    assert row.uncertainty_width == pytest.approx(note.model_yes.width)


def test_simulated_true_for_fixture_and_synthetic() -> None:
    overviews = build_overview(default_markets(), now=NOW)
    assert overviews
    assert all(row.simulated for row in overviews)
    assert {row.source_kind for row in overviews} == {"fixture", "synthetic"}
