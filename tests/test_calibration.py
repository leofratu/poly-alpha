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
    notes = [
        _note(market_id="a", kind=DataSourceKind.FIXTURE),
        _note(market_id="b", kind=DataSourceKind.FIXTURE),
        _note(market_id="c", kind=DataSourceKind.SIMULATED),
    ]
    reports = calibration_by_kind(notes, [True, False, True])
    assert sorted(reports) == ["fixture", "simulated"]
    assert reports["fixture"].n == 2
    assert reports["simulated"].n == 1
    assert sum(report.n for report in reports.values()) == len(notes)


def test_demo_calibration_runs_and_disclaims_real_world_evidence() -> None:
    report = demo_calibration()
    assert report.n >= 1
    assert report.simulated is True
    assert any("not evidence of real-world calibration" in note for note in report.notes)


def test_interior_intervals_miss_point_outcomes() -> None:
    notes = [_note(low=0.3, high=0.4), _note(low=0.6, high=0.7)]
    report = interval_coverage(notes, [True, False])
    assert report.coverage == 0.0
    assert any("point outcomes" in note for note in report.notes)


def test_calibration_by_kind_length_mismatch_raises() -> None:
    with pytest.raises(ValueError):
        calibration_by_kind([_note(), _note(market_id="b")], [True])
