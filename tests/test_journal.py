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
    second = build_entry(list(reversed(notes)), now=NOW)
    assert first.recorded_at == second.recorded_at == NOW.isoformat()
    assert first.mean_edge == second.mean_edge
    assert first.top_market_id == second.top_market_id
    assert first.kind_counts == second.kind_counts


def test_kind_counts_sum_to_market_count() -> None:
    notes = [
        make_note("a", 0.1, kind=DataSourceKind.REAL, simulated=False),
        make_note("b", 0.2, kind=DataSourceKind.FIXTURE),
        make_note("c", 0.3, kind=DataSourceKind.SIMULATED),
        make_note("d", -0.1, kind=DataSourceKind.REAL, simulated=False),
    ]
    entry = build_entry(notes, now=NOW)
    assert entry.market_count == len(notes) == 4
    assert sum(entry.kind_counts.values()) == entry.market_count
    assert entry.kind_counts == {"real": 2, "fixture": 1, "simulated": 1}


def test_simulated_true_for_fixture_notes() -> None:
    entry = build_entry([make_note("m1", 0.1), make_note("m2", 0.2)], now=NOW)
    assert entry.simulated is True


def test_top_market_id_uses_largest_absolute_edge_with_tie_break() -> None:
    notes = [make_note("m2", 0.4), make_note("m1", -0.4), make_note("m3", 0.2)]
    entry = build_entry(notes, now=NOW)
    assert entry.top_market_id == "m1"


def test_mean_edge_matches_manual_computation() -> None:
    notes = [make_note("m1", 0.1), make_note("m2", -0.3), make_note("m3", 0.5)]
    entry = build_entry(notes, now=NOW)
    manual = (0.1 + -0.3 + 0.5) / 3
    assert entry.mean_edge == manual


def test_empty_notes_yield_neutral_entry() -> None:
    entry = build_entry([], now=NOW)
    assert entry.market_count == 0
    assert entry.mean_edge == 0.0
    assert entry.top_market_id is None
    assert entry.simulated is False


