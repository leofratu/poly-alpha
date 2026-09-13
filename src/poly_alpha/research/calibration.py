"""Offline evaluation of whether research uncertainty intervals cover known outcomes.

Everything here is simulated and deterministic: the research engine is a heuristic over
fixture or synthetic snapshots, so coverage measured on demo data says nothing about
real-world calibration. These helpers expose that gap honestly rather than close it.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from poly_alpha.backtesting.demo_data import demo_resolved_markets
from poly_alpha.research.analyst import research_market
from poly_alpha.research.notes import ResearchNote

_SIMULATION_NOTE = (
    "Intervals come from a deterministic heuristic; coverage over demo data is not "
    "evidence of real-world calibration."
)


@dataclass(frozen=True)
class CalibrationReport:
    """How often model intervals covered realized outcomes over labeled data."""

    n: int
    coverage: float
    mean_width: float
    simulated: bool
    notes: tuple[str, ...]


def interval_coverage(
    notes: Sequence[ResearchNote], resolved_yes: Sequence[bool]
) -> CalibrationReport:
    """Measure model-interval coverage against known YES/NO resolutions.

    Each resolution becomes a realized value of 1.0 for YES and 0.0 for NO, which is
    covered when it falls within ``note.model_yes`` inclusive.
    """
    if len(notes) != len(resolved_yes):
        raise ValueError(
            "notes and resolved_yes must have equal length, got "
            f"{len(notes)} and {len(resolved_yes)}"
        )
    n = len(notes)
    covered = 0
    width_sum = 0.0
    simulated = False
    for note, outcome in zip(notes, resolved_yes, strict=True):
        realized = 1.0 if outcome else 0.0
        if note.model_yes.contains(realized):
            covered += 1
        width_sum += note.model_yes.width
        simulated = simulated or note.is_simulated()
    return CalibrationReport(
        n=n,
        coverage=covered / n if n else 0.0,
        mean_width=width_sum / n if n else 0.0,
        simulated=simulated,
        notes=(_SIMULATION_NOTE,),
    )


def calibration_by_kind(
    notes: Sequence[ResearchNote], resolved_yes: Sequence[bool]
) -> dict[str, CalibrationReport]:
    """Compute one coverage report per provenance kind, in sorted kind order."""
    if len(notes) != len(resolved_yes):
        raise ValueError(
            "notes and resolved_yes must have equal length, got "
            f"{len(notes)} and {len(resolved_yes)}"
        )
    grouped: dict[str, list[int]] = {}
    for index, note in enumerate(notes):
        grouped.setdefault(note.provenance.kind.value, []).append(index)
    reports: dict[str, CalibrationReport] = {}
    for kind in sorted(grouped):
        indexes = grouped[kind]
        reports[kind] = interval_coverage(
            [notes[index] for index in indexes],
            [resolved_yes[index] for index in indexes],
        )
    return reports


def demo_calibration() -> CalibrationReport:
    """Run the research engine over demo resolved markets and score coverage."""
    markets = demo_resolved_markets()
    notes = [research_market(market.snapshot) for market in markets]
    return interval_coverage(notes, [market.resolved_yes for market in markets])
