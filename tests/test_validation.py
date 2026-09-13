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


def test_empty_question_reports_issue() -> None:
    issues = validate_snapshot(replace(_valid_snapshot(), question=""))
    assert any("question" in issue for issue in issues)


def test_probability_bounds_are_exclusive() -> None:
    for value in (0.0, 1.0):
        yes_issues = validate_snapshot(replace(_valid_snapshot(), yes_price=value))
        no_issues = validate_snapshot(replace(_valid_snapshot(), no_price=value))
        assert any("yes_price" in issue for issue in yes_issues)
        assert any("no_price" in issue for issue in no_issues)


def test_none_prices_are_allowed() -> None:
    assert validate_snapshot(replace(_valid_snapshot(), yes_price=None, no_price=None)) == ()


def test_negative_liquidity_reports_issue() -> None:
    issues = validate_snapshot(replace(_valid_snapshot(), liquidity=-1.0))
    assert any("liquidity" in issue for issue in issues)


def test_nan_volume_reports_issue() -> None:
    issues = validate_snapshot(replace(_valid_snapshot(), volume=math.nan))
    assert any("volume" in issue for issue in issues)


def test_naive_close_time_reports_issue() -> None:
    naive = datetime(2026, 6, 20)
    issues = validate_snapshot(replace(_valid_snapshot(), close_time=naive))
    assert any("close_time" in issue for issue in issues)


def test_none_close_time_is_allowed() -> None:
    assert validate_snapshot(replace(_valid_snapshot(), close_time=None)) == ()


def test_bad_orderbook_level_reports_issue() -> None:
    bad_price = replace(_valid_snapshot(), orderbook=(PriceLevel(price=0.0, size=1.0),))
    bad_size = replace(_valid_snapshot(), orderbook=(PriceLevel(price=0.5, size=-1.0),))
    assert any("orderbook" in issue for issue in validate_snapshot(bad_price))
    assert any("orderbook" in issue for issue in validate_snapshot(bad_size))


def test_empty_provenance_source_reports_issue() -> None:
    bad = replace(
