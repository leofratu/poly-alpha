"""Pure Markdown dossier renderer for provenance-tagged research output.

The renderer is a deterministic string builder: it performs no I/O, no network access,
and no computation beyond formatting. Every artifact it emits is labeled with its data
source so fixture, simulated, and synthetic values are never presented as real. The
only file-writing entry point is :func:`write_markdown`, kept explicit and separate.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from poly_alpha.contracts import DataSourceKind, Provenance
from poly_alpha.research.notes import ResearchNote
from poly_alpha.research.screen import Opportunity

if TYPE_CHECKING:
    from poly_alpha.backtesting.comparison import StrategyMetrics
    from poly_alpha.portfolio.risk import RiskReport

__all__ = ["Opportunity", "render_markdown", "write_markdown"]

_DISCLAIMER_LINES: tuple[str, ...] = (
    "> **Research and paper-trading output only. This is not investment advice.**",
    "> **Fixture, simulated, and synthetic data are labeled and are not real observations.**",
    "> **Backtest metrics are in-sample and are not forecasts of future performance.**",
)


def _yes_no(value: bool) -> str:
    """Render a boolean as a lowercase yes/no label."""
    return "yes" if value else "no"


def _sources_text(sources: Sequence[Provenance]) -> str:
    """Render cited sources as ``name (kind)`` pairs, or ``none`` when absent."""
    if not sources:
        return "none"
    return ", ".join(f"{source.source} ({source.kind.value})" for source in sources)


def _provenance_lines(notes: Sequence[ResearchNote]) -> list[str]:
    """Summarize note counts per source kind and whether any real data is present."""
