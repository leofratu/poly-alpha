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
