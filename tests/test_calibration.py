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
