"""Tests for the dependency-free contract validation helpers."""

from __future__ import annotations

import math
from dataclasses import replace
from datetime import UTC, datetime

from poly_alpha.adapters.fixtures import FixtureMarketAdapter
from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
    Uncertainty,
)
from poly_alpha.validation import is_valid, validate_snapshot, validate_uncertainty


def _valid_snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="m1",
        question="Will it happen?",
        asset=AssetRef(symbol="X", asset_class="crypto"),
        yes_price=0.6,
        no_price=0.4,
        liquidity=1000.0,
        volume=5000.0,
        provenance=Provenance(source="test", kind=DataSourceKind.FIXTURE),
        close_time=datetime(2026, 6, 20, tzinfo=UTC),
        orderbook=(PriceLevel(price=0.59, size=100.0),),
    )


def test_fixture_markets_validate_clean() -> None:
    for market in FixtureMarketAdapter().list_markets():
        assert validate_snapshot(market) == ()
        assert is_valid(market) is True


def test_empty_market_id_reports_issue() -> None:
    issues = validate_snapshot(replace(_valid_snapshot(), market_id="  "))
    assert any("market_id" in issue for issue in issues)


