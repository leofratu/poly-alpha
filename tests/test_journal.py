"""Tests for the append-only research provenance journal."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from poly_alpha.contracts import DataSourceKind, Provenance, Uncertainty
from poly_alpha.research.journal import (
    JournalEntry,
    append_entry,
    build_entry,
    entry_to_dict,
    read_entries,
)
from poly_alpha.research.notes import ResearchNote

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def make_note(
    market_id: str,
    edge: float,
    *,
    kind: DataSourceKind = DataSourceKind.FIXTURE,
    simulated: bool = False,
) -> ResearchNote:
    uncertainty = Uncertainty(estimate=edge, low=edge - 0.01, high=edge + 0.01, simulated=simulated)
    return ResearchNote(
        market_id=market_id,
        question=f"Will {market_id} resolve YES?",
        summary="offline test note",
        claims=(),
        market_implied_yes=None,
        model_yes=uncertainty,
        edge=uncertainty,
        provenance=Provenance(source="test-fixture", kind=kind),
        generated_at=NOW,
        caveats=(),
    )


def test_build_entry_is_deterministic_for_fixed_now() -> None:
    notes = [make_note("m1", 0.1), make_note("m2", -0.2)]
    first = build_entry(notes, now=NOW)
