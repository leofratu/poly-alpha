"""Conservative opportunity screening over provenance-tagged research notes.

Screening ranks markets by the lower bound of the model edge rather than the point
estimate, so a market is surfaced only when even the pessimistic end of its uncertainty
interval clears the threshold. This is research and paper-trading output only; it is not
investment advice. All computation is offline and deterministic.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from poly_alpha.contracts import MarketSnapshot
from poly_alpha.research.analyst import research_markets
from poly_alpha.research.notes import ResearchNote


@dataclass(frozen=True)
class Opportunity:
    """A screened market whose conservative edge clears the screening threshold."""

    note: ResearchNote
    edge_low: float
    edge_high: float
    score: float
    requires_real_data: bool

    @property
    def is_real(self) -> bool:
        """True when the underlying note is backed by real observed data."""
        return self.note.provenance.kind.is_real


def rank_opportunities(
    notes: Sequence[ResearchNote],
    *,
    min_edge_low: float = 0.0,
    require_real: bool = False,
) -> list[Opportunity]:
    """Rank notes by conservative edge, dropping those below the lower-bound threshold.

    A note is kept only when ``note.edge.low`` strictly exceeds ``min_edge_low``. When
    ``require_real`` is True, notes whose provenance is not real are also dropped.
    Results sort by score descending, with ``market_id`` ascending breaking ties.
    """
    opportunities = [
        Opportunity(
            note=note,
            edge_low=note.edge.low,
            edge_high=note.edge.high,
            score=note.edge.low,
            requires_real_data=not note.provenance.kind.is_real,
        )
        for note in notes
        if note.edge.low > min_edge_low and (not require_real or note.provenance.kind.is_real)
    ]
    opportunities.sort(key=lambda opportunity: (-opportunity.score, opportunity.note.market_id))
    return opportunities


def screen_markets(
    snapshots: Sequence[MarketSnapshot],
    *,
    now: datetime | None = None,
    min_edge_low: float = 0.0,
    require_real: bool = False,
) -> list[Opportunity]:
    """Research snapshots offline, then rank the resulting opportunities conservatively."""
    notes = research_markets(snapshots, now=now)
    return rank_opportunities(notes, min_edge_low=min_edge_low, require_real=require_real)


def summarize(opportunities: Sequence[Opportunity]) -> dict[str, float | int]:
    """Aggregate counts and conservative-edge statistics over opportunities."""
    if not opportunities:
        return {"count": 0, "real_count": 0, "mean_edge_low": 0.0, "max_edge_low": 0.0}
    edge_lows = [opportunity.edge_low for opportunity in opportunities]
    return {
        "count": len(opportunities),
        "real_count": sum(1 for opportunity in opportunities if opportunity.is_real),
        "mean_edge_low": sum(edge_lows) / len(edge_lows),
        "max_edge_low": max(edge_lows),
    }
