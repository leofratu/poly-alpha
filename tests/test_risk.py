"""Tests for portfolio concentration and historical risk analysis."""

from __future__ import annotations

import math
from datetime import UTC, datetime

import pytest

from poly_alpha.contracts import DataSourceKind, Provenance
from poly_alpha.portfolio.risk import Position, analyze_portfolio, portfolio_value

PROVENANCE = Provenance(
    source="test",
    kind=DataSourceKind.FIXTURE,
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def make_position(
    market_id: str,
    asset_class: str,
    stake: float,
    yes_probability: float = 0.4,
) -> Position:
    return Position(
        market_id=market_id,
        asset_class=asset_class,
        stake=stake,
        yes_probability=yes_probability,
        provenance=PROVENANCE,
    )


def test_single_position_hhi_is_one() -> None:
    report = analyze_portfolio([make_position("m1", "sports", 100.0)])
    assert report.n_positions == 1
    assert report.hhi == pytest.approx(1.0)
    assert report.max_position_fraction == pytest.approx(1.0)
    assert report.total_stake == pytest.approx(100.0)


def test_equal_split_lowers_hhi() -> None:
    report = analyze_portfolio(
        [make_position("m1", "sports", 100.0), make_position("m2", "politics", 100.0)]
    )
    assert report.hhi == pytest.approx(0.5)
    assert report.max_position_fraction == pytest.approx(0.5)
    assert report.hhi < 1.0


def test_exposure_sums_to_total() -> None:
    positions = [
        make_position("m1", "sports", 100.0),
        make_position("m2", "sports", 50.0),
        make_position("m3", "politics", 25.0),
    ]
    report = analyze_portfolio(positions)
    assert sum(report.exposure_by_class.values()) == pytest.approx(report.total_stake)
    assert report.exposure_by_class["sports"] == pytest.approx(150.0)
    assert report.exposure_by_class["politics"] == pytest.approx(25.0)


def test_missing_returns_yields_none_var_with_note() -> None:
    report = analyze_portfolio([make_position("m1", "sports", 100.0)])
    assert report.historical_var_95 is None
    assert any("VaR" in note for note in report.notes)


def test_supplied_returns_yield_finite_var_and_drawdown() -> None:
    returns = [-0.10, 0.05, 0.02, -0.03, 0.01, 0.04]
    report = analyze_portfolio([make_position("m1", "sports", 100.0)], returns)
    assert report.historical_var_95 is not None
    assert math.isfinite(report.historical_var_95)
    assert report.max_drawdown >= 0.0
    assert report.max_drawdown <= 1.0
    assert any("parametric" in note for note in report.notes)


def test_drawdown_from_returns_is_deterministic() -> None:
    report = analyze_portfolio([make_position("m1", "sports", 100.0)], [0.10, -0.50, 0.10])
    assert report.max_drawdown == pytest.approx(0.5)


def test_total_loss_drawdown_is_one() -> None:
    report = analyze_portfolio([make_position("m1", "sports", 100.0)], [-1.0])
    assert report.max_drawdown == pytest.approx(1.0)


def test_monotone_decline_counts_from_initial_capital() -> None:
    report = analyze_portfolio([make_position("m1", "sports", 100.0)], [-0.1, -0.1, -0.1])
    assert report.max_drawdown == pytest.approx(1.0 - 0.9**3, abs=1e-6)


def test_empty_returns_treated_as_missing() -> None:
    report = analyze_portfolio([make_position("m1", "sports", 100.0)], [])
    assert report.historical_var_95 is None
    assert any("VaR" in note for note in report.notes)


def test_portfolio_value_marks_to_price() -> None:
    positions = [make_position("m1", "sports", 100.0, yes_probability=0.4)]
    assert portfolio_value(positions, {"m1": 0.6}) == pytest.approx(150.0)


def test_portfolio_value_falls_back_to_stake() -> None:
    positions = [make_position("m1", "sports", 100.0, yes_probability=0.4)]
    assert portfolio_value(positions, {}) == pytest.approx(100.0)


def test_negative_stake_rejected() -> None:
    with pytest.raises(ValueError):
        analyze_portfolio([make_position("m1", "sports", -10.0)])


def test_non_finite_returns_rejected() -> None:
    with pytest.raises(ValueError):
        analyze_portfolio([make_position("m1", "sports", 100.0)], [0.1, float("nan")])


def test_all_zero_stakes_yield_zero_concentration() -> None:
    report = analyze_portfolio(
        [make_position("m1", "sports", 0.0), make_position("m2", "politics", 0.0)]
    )
    assert report.total_stake == 0.0
    assert report.hhi == 0.0
    assert report.max_position_fraction == 0.0
