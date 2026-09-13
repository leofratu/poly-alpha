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
        lines.append(
            f"- `{opportunity.note.market_id}`: edge_low={opportunity.edge_low:.1%}, "
            f"edge_high={opportunity.edge_high:.1%}, score={opportunity.score:.4f}, "
            f"real={_yes_no(opportunity.is_real)}"
        )
    lines.append("")
    return lines


def _metrics_lines(metrics: Sequence[StrategyMetrics]) -> list[str]:
    """Render the strategy-comparison section with the first metric's caveat."""
    lines = ["## Strategy comparison", ""]
    if not metrics:
        lines.extend(["(none)", ""])
        return lines
    for record in metrics:
        lines.append(
            f"- {record.name}: trades={record.trades}, hit_rate={record.hit_rate:.1%}, "
            f"total_pnl={record.total_pnl:+.2f}, roi={record.roi:+.1%}, "
            f"max_drawdown={record.max_drawdown:.1%}"
        )
    lines.extend(["", f"**Caveat:** {metrics[0].caveat}", ""])
    return lines


def _risk_lines(risk: RiskReport) -> list[str]:
    """Render the portfolio-risk section."""
    var = "n/a" if risk.historical_var_95 is None else f"{risk.historical_var_95:.2%}"
    notes_text = "; ".join(risk.notes) if risk.notes else "none"
    return [
        "## Portfolio risk",
        "",
        f"- Positions: {risk.n_positions}",
        f"- Total stake: {risk.total_stake:.2f}",
        f"- HHI: {risk.hhi:.4f}",
        f"- Max position fraction: {risk.max_position_fraction:.1%}",
        f"- Historical VaR 95: {var}",
        f"- Max drawdown: {risk.max_drawdown:.1%}",
        f"- Notes: {notes_text}",
        "",
    ]


def render_markdown(
    notes: Sequence[ResearchNote],
    *,
    opportunities: Sequence[Opportunity] | None = None,
    metrics: Sequence[StrategyMetrics] | None = None,
    risk: RiskReport | None = None,
    generated_at: datetime | None = None,
    title: str = "Poly-Alpha Research Dossier",
) -> str:
    """Render research notes and optional analysis sections as Markdown.

    The output opens with the title and a bold disclaimer, summarizes provenance,
    renders every note, then appends each optional section only when its argument is
    supplied. Passing ``generated_at`` makes the rendering fully deterministic; when it
    is omitted no timestamp is emitted and no clock is read.
    """
    lines: list[str] = [f"# {title}", ""]
    lines.extend(_DISCLAIMER_LINES)
    lines.append("")
    if generated_at is not None:
        lines.extend([f"Generated at: {generated_at.isoformat()}", ""])
    lines.extend(_provenance_lines(notes))
    for note in notes:
        lines.extend(_note_lines(note))
    if opportunities is not None:
        lines.extend(_opportunity_lines(opportunities))
    if metrics is not None:
        lines.extend(_metrics_lines(metrics))
    if risk is not None:
        lines.extend(_risk_lines(risk))
    return "\n".join(lines).rstrip("\n") + "\n"


def write_markdown(path: str | Path, content: str) -> None:
    """Write ``content`` to ``path`` as UTF-8; the module's only file write."""
    Path(path).write_text(content, encoding="utf-8")
