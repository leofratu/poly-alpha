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


def test_below_cap_is_not_capped() -> None:
    decision = kelly_fraction(probability=0.52, price=0.5, cap=0.05)
    assert decision.fraction < 0.05
    assert decision.capped is False


def test_lower_bound_reduces_fraction() -> None:
    uncertainty = make_uncertainty(low=0.53, estimate=0.56)
    point = kelly_fraction(probability=0.56, price=0.52, cap=0.05)
    conservative = kelly_fraction(probability=0.56, price=0.52, uncertainty=uncertainty, cap=0.05)
    assert conservative.fraction < point.fraction
    assert conservative.probability_used == pytest.approx(0.53)


def test_probability_used_reflects_lower_bound() -> None:
    uncertainty = make_uncertainty(low=0.62)
    decision = kelly_fraction(probability=0.9, price=0.5, uncertainty=uncertainty)
    assert decision.probability_used == pytest.approx(0.62)
    assert "lower bound used" in decision.rationale


def test_lower_bound_can_be_disabled() -> None:
    uncertainty = make_uncertainty(low=0.2)
    decision = kelly_fraction(
        probability=0.7, price=0.5, uncertainty=uncertainty, use_lower_bound=False
    )
    assert decision.probability_used == pytest.approx(0.7)
    assert decision.fraction > 0.0
    assert "point estimate used" in decision.rationale


def test_probability_used_is_clamped() -> None:
    decision = kelly_fraction(probability=1.5, price=0.5, use_lower_bound=False)
    assert decision.probability_used == pytest.approx(1.0)


def test_mismatched_lengths_raise() -> None:
    with pytest.raises(ValueError):
        portfolio_fractions([0.6, 0.7], [0.5])


def test_portfolio_fractions_are_pairwise_and_un_normalized() -> None:
    decisions = portfolio_fractions([0.9, 0.9], [0.1, 0.1], cap=0.05)
    assert [decision.fraction for decision in decisions] == pytest.approx([0.05, 0.05])
    assert total_fraction(decisions) == pytest.approx(0.1)


def test_total_fraction_sums() -> None:
    decisions = [
        SizingDecision(fraction=0.02, rationale="a", capped=False, probability_used=0.6),
        SizingDecision(fraction=0.03, rationale="b", capped=True, probability_used=0.7),
    ]
    assert total_fraction(decisions) == pytest.approx(0.05)


def test_invalid_cap_rejected() -> None:
    with pytest.raises(ValueError):
        kelly_fraction(probability=0.6, price=0.5, cap=0.0)
    with pytest.raises(ValueError):
        kelly_fraction(probability=0.6, price=0.5, cap=1.5)


def test_unit_cap_keeps_fraction_within_bounds() -> None:
    decision = kelly_fraction(probability=0.9, price=0.5, cap=1.0)
    assert 0.0 < decision.fraction <= 1.0
