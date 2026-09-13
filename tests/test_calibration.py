"""Offline tests for uncertainty-interval calibration over labeled outcomes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from poly_alpha.contracts import DataSourceKind, Provenance, Uncertainty
from poly_alpha.research.calibration import (
    calibration_by_kind,
    demo_calibration,
    interval_coverage,
)
from poly_alpha.research.notes import ResearchNote

_AS_OF = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def _note(
    *,
    market_id: str = "m1",
    low: float = 0.4,
    high: float = 0.6,
    kind: DataSourceKind = DataSourceKind.FIXTURE,
    simulated: bool = True,
) -> ResearchNote:
    model = Uncertainty(estimate=(low + high) / 2.0, low=low, high=high, simulated=simulated)
    edge = Uncertainty(estimate=0.0, low=-0.5, high=0.5, simulated=simulated)
    return ResearchNote(
        market_id=market_id,
        question="Will the test event resolve YES?",
        summary="hand-built calibration fixture",
        claims=(),
        market_implied_yes=0.5,
        model_yes=model,
        edge=edge,
        provenance=Provenance(source="test-fixture", kind=kind, retrieved_at=_AS_OF),
        generated_at=_AS_OF,
        caveats=(),
    )


def test_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        interval_coverage([_note()], [])


def test_all_covered_yields_full_coverage() -> None:
    notes = [_note(market_id="a", low=0.0, high=1.0), _note(market_id="b", low=0.0, high=1.0)]
    report = interval_coverage(notes, [True, False])
    assert report.n == 2
    assert report.coverage == 1.0


def test_all_missed_yields_zero_coverage() -> None:
    notes = [_note(market_id="a", low=0.4, high=0.6), _note(market_id="b", low=0.4, high=0.6)]
    report = interval_coverage(notes, [True, False])
    assert report.n == 2
    assert report.coverage == 0.0


def test_mean_width_matches_manual_computation() -> None:
    notes = [
        _note(market_id="a", low=0.4, high=0.6),
        _note(market_id="b", low=0.2, high=0.6),
        _note(market_id="c", low=0.1, high=0.2),
    ]
    report = interval_coverage(notes, [True, False, True])
    expected = (0.2 + 0.4 + 0.1) / 3
    assert report.mean_width == pytest.approx(expected)


def test_empty_input_is_zeroed() -> None:
    report = interval_coverage([], [])
    assert report.n == 0
    assert report.coverage == 0.0
    assert report.mean_width == 0.0
    assert report.simulated is False


def test_simulated_flag_true_for_fixture_notes() -> None:
    report = interval_coverage([_note(kind=DataSourceKind.FIXTURE, simulated=False)], [True])
    assert report.simulated is True


def test_simulated_flag_true_when_intervals_are_simulated() -> None:
    report = interval_coverage([_note(kind=DataSourceKind.REAL, simulated=True)], [True])
    assert report.simulated is True


def test_calibration_by_kind_groups_and_sums_to_n() -> None:
