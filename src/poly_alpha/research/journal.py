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
    ascending ``market_id``. ``mean_edge`` is ``0.0`` when there are no notes.
    """
    recorded = now if now is not None else datetime.now(UTC)
    kind_counts: dict[str, int] = {}
    for note in notes:
        kind = note.provenance.kind.value
        kind_counts[kind] = kind_counts.get(kind, 0) + 1

    if notes:
        mean_edge = sum(note.edge.estimate for note in notes) / len(notes)
        top = min(notes, key=lambda note: (-abs(note.edge.estimate), note.market_id))
        top_market_id: str | None = top.market_id
    else:
        mean_edge = 0.0
        top_market_id = None

    simulated = any(note.is_simulated() for note in notes)

    return JournalEntry(
        recorded_at=recorded.isoformat(),
        market_count=len(notes),
        kind_counts=kind_counts,
        simulated=simulated,
        mean_edge=mean_edge,
        top_market_id=top_market_id,
    )


def entry_to_dict(entry: JournalEntry) -> dict[str, object]:
    """Convert an entry to a JSON-serializable dict with sorted kind counts."""
    return {
        "recorded_at": entry.recorded_at,
        "market_count": entry.market_count,
        "kind_counts": dict(sorted(entry.kind_counts.items())),
        "simulated": entry.simulated,
        "mean_edge": entry.mean_edge,
        "top_market_id": entry.top_market_id,
    }


def entry_from_dict(data: dict[str, object]) -> JournalEntry:
    """Rebuild an entry from a dict, raising on missing or mistyped fields."""
    raw_counts = data["kind_counts"]
    if not isinstance(raw_counts, dict):
        raise ValueError("kind_counts must be an object")
    kind_counts = {str(key): int(value) for key, value in raw_counts.items()}
    top = data.get("top_market_id")
    market_count = data["market_count"]
    if not isinstance(market_count, int):
        raise ValueError("market_count must be an int")
    mean_edge = data["mean_edge"]
    if not isinstance(mean_edge, (int, float)):
        raise ValueError("mean_edge must be a number")
    return JournalEntry(
        recorded_at=str(data["recorded_at"]),
        market_count=market_count,
        kind_counts=kind_counts,
        simulated=bool(data["simulated"]),
        mean_edge=float(mean_edge),
        top_market_id=None if top is None else str(top),
    )


def append_entry(path: str | Path, entry: JournalEntry) -> None:
    """Append ``entry`` as one UTF-8 JSON line, creating parent directories."""
    journal_path = Path(path)
    journal_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(entry_to_dict(entry), sort_keys=True)
    with journal_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_entries(path: str | Path) -> list[JournalEntry]:
    """Read entries from a journal, returning ``[]`` when missing.

    Malformed or unreadable lines are skipped rather than raising, so a partially written
    or externally edited journal never blocks readers.
    """
    journal_path = Path(path)
    if not journal_path.exists():
        return []
    entries: list[JournalEntry] = []
    with journal_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                entries.append(entry_from_dict(data))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return entries
