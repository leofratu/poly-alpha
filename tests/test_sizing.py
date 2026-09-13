"""Tests for conservative, uncertainty-aware position sizing."""

from __future__ import annotations

import pytest

from poly_alpha.contracts import Uncertainty
from poly_alpha.portfolio.sizing import (
    SizingDecision,
    kelly_fraction,
    portfolio_fractions,
    total_fraction,
)


def make_uncertainty(low: float, estimate: float = 0.5, high: float = 0.8) -> Uncertainty:
    return Uncertainty(estimate=estimate, low=low, high=high, basis="test")


def test_zero_edge_returns_zero() -> None:
    decision = kelly_fraction(probability=0.4, price=0.4)
    assert decision.fraction == 0.0
    assert "no positive edge" in decision.rationale


def test_negative_edge_returns_zero() -> None:
    decision = kelly_fraction(probability=0.3, price=0.6)
    assert decision.fraction == 0.0
    assert decision.probability_used == pytest.approx(0.3)


@pytest.mark.parametrize("price", [0.0, 1.0])
def test_price_at_bounds_returns_zero(price: float) -> None:
    decision = kelly_fraction(probability=0.6, price=price)
    assert decision.fraction == 0.0
    assert decision.capped is False


def test_cap_binds_and_marks_capped() -> None:
    decision = kelly_fraction(probability=0.9, price=0.1, cap=0.05)
    full = (0.9 - 0.1) / (1.0 - 0.1)
    assert full > 0.05
    assert decision.fraction == pytest.approx(0.05)
    assert decision.capped is True


