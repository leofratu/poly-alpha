"""Append-only provenance journal for research runs.

Each run emits a compact, deterministic audit entry summarizing how many markets were
researched, their provenance mix, whether any input was non-real, and the aggregate model
edge. Entries contain no raw note text and no secrets: only counts, a single float, and one
market identifier. The journal is plain UTF-8 JSON Lines so it can be appended and read
offline without a database. :func:`append_entry` is the module's only write.
"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from poly_alpha.research.notes import ResearchNote

__all__ = [
    "JournalEntry",
    "append_entry",
    "build_entry",
    "entry_from_dict",
    "entry_to_dict",
    "read_entries",
]


@dataclass(frozen=True)
class JournalEntry:
    """A compact, immutable audit record of one research run."""

    recorded_at: str
    market_count: int
    kind_counts: dict[str, int]
    simulated: bool
    mean_edge: float
    top_market_id: str | None


def build_entry(notes: Sequence[ResearchNote], *, now: datetime | None = None) -> JournalEntry:
    """Summarize ``notes`` into a :class:`JournalEntry`.

    Supplying ``now`` makes the result fully deterministic; otherwise the current UTC time
    is used. ``top_market_id`` is the note with the largest absolute edge, breaking ties by
