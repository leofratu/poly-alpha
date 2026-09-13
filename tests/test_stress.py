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


def test_base_scenario_is_no_op_for_out_of_range_prices() -> None:
    positions = [make_position("m1", 100.0, yes_probability=0.5)]
    result = apply_stress(positions, {"m1": 1.2}, default_scenarios()[0])
    assert result.change == pytest.approx(0.0)
    assert result.stressed_value == pytest.approx(result.start_value)


def test_negative_shift_lowers_long_yes_value() -> None:
    positions = [make_position("m1", 100.0, yes_probability=0.5)]
    result = apply_stress(positions, {"m1": 0.5}, StressScenario("shock_down", -0.10))
    assert result.change < 0.0
    assert result.stressed_value < result.start_value


def test_positive_shift_raises_long_yes_value() -> None:
    positions = [make_position("m1", 100.0, yes_probability=0.5)]
    result = apply_stress(positions, {"m1": 0.5}, StressScenario("shock_up", 0.10))
    assert result.change > 0.0
    assert result.stressed_value > result.start_value


def test_shift_is_clamped_at_bounds() -> None:
    positions = [make_position("m1", 100.0, yes_probability=0.5)]
    down = apply_stress(positions, {"m1": 0.05}, StressScenario("crash", -0.30))
    up = apply_stress(positions, {"m1": 0.95}, StressScenario("up", 0.30))
    assert down.stressed_value == pytest.approx(0.0)
    assert up.stressed_value >= 0.0
    assert down.stressed_value >= 0.0
    assert up.stressed_value == pytest.approx(200.0)


def test_worst_market_id_picks_largest_loss_with_tie_break() -> None:
    positions = [
        make_position("m2", 100.0, yes_probability=0.5),
        make_position("m1", 100.0, yes_probability=0.5),
        make_position("m3", 10.0, yes_probability=0.5),
    ]
    result = apply_stress(
        positions, {"m1": 0.5, "m2": 0.5, "m3": 0.5}, StressScenario("down", -0.10)
    )
    assert result.worst_market_id == "m1"


def test_no_negative_change_yields_none() -> None:
    positions = [make_position("m1", 100.0, yes_probability=0.5)]
    result = apply_stress(positions, {"m1": 0.5}, StressScenario("base", 0.0))
    assert result.worst_market_id is None


def test_empty_positions_are_zero_with_no_worst() -> None:
    result = apply_stress([], {"m1": 0.5}, StressScenario("crash", -0.30))
    assert result.start_value == pytest.approx(0.0)
    assert result.stressed_value == pytest.approx(0.0)
    assert result.change == pytest.approx(0.0)
    assert result.worst_market_id is None


def test_run_scenarios_is_deterministic() -> None:
    positions = [make_position("m1", 100.0, yes_probability=0.5)]
    prices = {"m1": 0.5}
    first = run_scenarios(positions, prices)
    second = run_scenarios(positions, prices)
    assert first == second


def test_default_scenarios_contain_base_with_zero_shift() -> None:
    scenarios = default_scenarios()
    names = [scenario.name for scenario in scenarios]
    assert "base" in names
    base = next(scenario for scenario in scenarios if scenario.name == "base")
    assert base.yes_price_shift == 0.0


def test_position_absent_from_prices_is_carried_at_stake() -> None:
    positions = [make_position("m1", 100.0, yes_probability=0.5)]
    result = apply_stress(positions, {}, StressScenario("shock_down", -0.10))
    assert result.start_value == 100.0
    assert result.change == 0.0


def test_run_scenarios_none_uses_default_scenarios() -> None:
    positions = [make_position("m1", 100.0, yes_probability=0.5)]
    results = run_scenarios(positions, {"m1": 0.5}, scenarios=None)
    names = [result.scenario for result in results]
    assert "base" in names
    assert names == [scenario.name for scenario in default_scenarios()]


def test_default_scenarios_are_at_least_four_with_unique_names() -> None:
    scenarios = default_scenarios()
    names = [scenario.name for scenario in scenarios]
    assert len(scenarios) >= 4
    assert len(set(names)) == len(names)
