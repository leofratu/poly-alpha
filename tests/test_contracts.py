"""Tests for the shared market and asset data contracts."""

from __future__ import annotations

import pytest

from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    Provenance,
    Uncertainty,
)


def _snapshot(yes: float | None, no: float | None) -> MarketSnapshot:
    return MarketSnapshot(
        market_id="m1",
        question="q?",
        asset=AssetRef(symbol="X", asset_class="crypto"),
        yes_price=yes,
        no_price=no,
        liquidity=100.0,
        volume=10.0,
        provenance=Provenance(source="t", kind=DataSourceKind.FIXTURE),
    )


def test_only_real_kind_is_real() -> None:
    assert DataSourceKind.REAL.is_real is True
    assert DataSourceKind.FIXTURE.is_real is False
    assert DataSourceKind.SIMULATED.is_real is False
    assert DataSourceKind.SYNTHETIC.is_real is False


def test_implied_yes_devigs_two_sided_price() -> None:
    market = _snapshot(0.6, 0.44)
    assert market.implied_yes() == pytest.approx(0.6 / 1.04)
    assert market.is_tradeable is True


def test_implied_yes_none_without_both_sides() -> None:
    assert _snapshot(None, 0.4).implied_yes() is None
    assert _snapshot(0.6, None).is_tradeable is False


def test_zero_total_probability_is_none() -> None:
    assert _snapshot(0.0, 0.0).implied_yes() is None


def test_uncertainty_bounds_and_membership() -> None:
    band = Uncertainty(estimate=0.5, low=0.4, high=0.6, basis="fixture", simulated=True)
    assert band.width == pytest.approx(0.2)
    assert band.contains(0.5) is True
    assert band.contains(0.7) is False
