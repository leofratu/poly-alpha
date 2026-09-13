"""Offline tests for the deterministic, end-to-end research pipeline."""

from __future__ import annotations

import pytest

from poly_alpha.adapters.registry import default_markets
from poly_alpha.research.analyst import research_markets
from poly_alpha.research.pipeline import run_pipeline
from poly_alpha.research.screen import rank_opportunities

_EPSILON = 1e-9


def test_pipeline_counts_are_consistent() -> None:
    bundle = run_pipeline()
    assert bundle.market_count > 0
    assert bundle.note_count == bundle.market_count
    assert bundle.opportunity_count <= bundle.note_count


def test_opportunity_count_is_the_conservative_screen() -> None:
    notes = research_markets(default_markets())
    expected = len(rank_opportunities(notes))
    assert run_pipeline().opportunity_count == expected
    assert expected < len(notes)


def test_stakes_cash_and_fractions_reconcile() -> None:
    bankroll = 1000.0
    bundle = run_pipeline(bankroll=bankroll)
    assert abs((bundle.total_stake + bundle.cash) - bankroll) <= _EPSILON
    fraction_sum = sum(allocation.fraction for allocation in bundle.allocations)
    assert abs(fraction_sum - bundle.total_fraction) <= _EPSILON


def test_risk_positions_and_calibration_are_populated() -> None:
    bundle = run_pipeline()
    assert bundle.risk.n_positions == len(bundle.allocations)
    assert bundle.calibration.n >= 1


def test_pipeline_is_deterministic_across_calls() -> None:
    assert run_pipeline() == run_pipeline()


def test_caveat_labels_simulation_and_disclaims_advice() -> None:
    caveat = run_pipeline().caveat
    assert "simulat" in caveat.lower()
    assert "not investment advice" in caveat
    assert "not a forecast" in caveat


def test_pipeline_position_uses_market_entry_price_not_model_estimate() -> None:
    from poly_alpha.adapters.registry import default_markets
    from poly_alpha.portfolio.allocate import Allocation
    from poly_alpha.research.analyst import research_market
    from poly_alpha.research.pipeline import _position_for

    snapshot = default_markets()[0]
    note = research_market(snapshot)
    assert note.market_implied_yes is not None
    allocation = Allocation(market_id=note.market_id, fraction=0.05, stake=50.0, rationale="test")
    position = _position_for(allocation, note, snapshot.asset.asset_class)
    assert position.entry_price == note.market_implied_yes


@pytest.mark.parametrize(
    ("bankroll", "cap"),
    [(0.0, 0.05), (-100.0, 0.05), (1000.0, 0.0), (1000.0, 1.5), (1000.0, -0.1)],
)
def test_invalid_constraints_propagate_value_error(bankroll: float, cap: float) -> None:
    with pytest.raises(ValueError):
        run_pipeline(bankroll=bankroll, cap=cap)
