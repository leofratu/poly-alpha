"""Tests for deterministic portfolio stress scenarios."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from poly_alpha.contracts import DataSourceKind, Provenance
from poly_alpha.portfolio.risk import Position
from poly_alpha.portfolio.stress import (
    StressScenario,
    apply_stress,
    default_scenarios,
    run_scenarios,
)

PROVENANCE = Provenance(
    source="test",
    kind=DataSourceKind.FIXTURE,
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def make_position(
    market_id: str,
    stake: float,
    yes_probability: float = 0.5,
) -> Position:
    return Position(
        market_id=market_id,
        asset_class="sports",
        stake=stake,
        yes_probability=yes_probability,
        provenance=PROVENANCE,
    )


def test_base_scenario_change_is_zero() -> None:
    positions = [make_position("m1", 100.0, yes_probability=0.5)]
    result = apply_stress(positions, {"m1": 0.5}, default_scenarios()[0])
    assert result.change == pytest.approx(0.0)
    assert result.stressed_value == pytest.approx(result.start_value)


def test_negative_shift_lowers_long_yes_value() -> None:
