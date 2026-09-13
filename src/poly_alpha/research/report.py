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
    lines = ["## Provenance summary", ""]
    for kind in DataSourceKind:
        count = sum(1 for note in notes if note.provenance.kind is kind)
        lines.append(f"- {kind.value}: {count}")
    real_present = any(note.provenance.kind.is_real for note in notes)
    lines.extend(["", f"Real data present: {_yes_no(real_present)}", ""])
    return lines


def _note_lines(note: ResearchNote) -> list[str]:
    """Render one note as a heading, an estimate line, its claims, and its caveats."""
    implied = "n/a" if note.market_implied_yes is None else f"{note.market_implied_yes:.1%}"
    interval = f"[{note.model_yes.low:.1%}, {note.model_yes.high:.1%}]"
    estimate_line = (
        f"- Market implied: {implied}; Model estimate: {note.model_yes.estimate:.1%} "
        f"{interval}; Signed edge: {note.edge.estimate:+.1%}"
    )
    lines = [
        f"## {note.question}",
        "",
        f"- Market: `{note.market_id}`",
        f"- Provenance: {note.provenance.source} ({note.provenance.kind.value})",
        estimate_line,
        f"- Model basis: {note.model_yes.basis}",
        "",
        "**Claims:**",
        "",
    ]
    for claim in note.claims:
        lines.append(
            f"- {claim.text} (direction: {claim.direction}, support: {claim.support:.0%}; "
            f"sources: {_sources_text(claim.sources)})"
        )
    lines.extend(["", "**Caveats:**", ""])
    lines.extend(f"- {caveat}" for caveat in note.caveats)
    lines.append("")
    return lines


def _opportunity_lines(opportunities: Sequence[Opportunity]) -> list[str]:
    """Render the screened-opportunities section."""
    lines = ["## Screened opportunities", ""]
    if not opportunities:
        lines.extend(["(none)", ""])
        return lines
    for opportunity in opportunities:
