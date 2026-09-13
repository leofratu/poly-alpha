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
        note=note,
        edge_low=note.edge.low,
        edge_high=note.edge.high,
        score=note.edge.low,
        requires_real_data=False,
    )


def test_empty_opportunities_yields_full_cash() -> None:
    plan = allocate([], {})
    assert isinstance(plan, AllocationPlan)
    assert plan.bankroll == 1000.0
    assert plan.total_fraction == 0.0
    assert plan.total_stake == 0.0
    assert plan.cash == 1000.0
    assert plan.allocations == ()
    assert "in-sample" in plan.caveat
    assert "not investment advice" in plan.caveat


def test_max_positions_zero_yields_no_allocations() -> None:
    opportunities = [make_opportunity("m1"), make_opportunity("m2")]
    plan = allocate(opportunities, {"m1": 0.85, "m2": 0.85}, max_positions=0)
    assert plan.allocations == ()
    assert plan.total_fraction == 0.0
    assert plan.cash == 1000.0


def test_max_positions_respected() -> None:
    opportunities = [make_opportunity(f"m{i}") for i in range(5)]
    prices = {f"m{i}": 0.85 for i in range(5)}
    plan = allocate(opportunities, prices, max_positions=2)
    assert len(plan.allocations) == 2
    assert plan.total_fraction == pytest.approx(0.10)


def test_max_deploy_clamps_last_allocation() -> None:
    opportunities = [make_opportunity(f"m{i}") for i in range(3)]
    prices = {f"m{i}": 0.85 for i in range(3)}
    plan = allocate(opportunities, prices, cap=0.05, max_deploy=0.12)
    assert len(plan.allocations) == 3
    assert plan.allocations[0].fraction == pytest.approx(0.05)
    assert plan.allocations[1].fraction == pytest.approx(0.05)
    assert plan.allocations[2].fraction == pytest.approx(0.02)
    assert plan.total_fraction == pytest.approx(0.12)
    assert plan.total_fraction <= 0.12 + 1e-9
