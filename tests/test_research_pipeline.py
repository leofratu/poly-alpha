"""Offline tests for the deterministic, end-to-end research pipeline."""

from __future__ import annotations

import pytest

from poly_alpha.research.pipeline import run_pipeline

_EPSILON = 1e-9


def test_pipeline_counts_are_consistent() -> None:
    bundle = run_pipeline()
    assert bundle.market_count > 0
    assert bundle.note_count == bundle.market_count
    assert bundle.opportunity_count <= bundle.note_count


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


@pytest.mark.parametrize(
    ("bankroll", "cap"),
    [(0.0, 0.05), (-100.0, 0.05), (1000.0, 0.0), (1000.0, 1.5), (1000.0, -0.1)],
