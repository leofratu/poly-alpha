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
