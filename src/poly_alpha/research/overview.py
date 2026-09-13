"""Cross-market overview: ranked summary rows over many heterogeneous snapshots.

The overview is a pure, fully offline transformation. Each snapshot is run through the
deterministic research engine, then flattened into one `MarketOverview` row that carries
the market's implied and model probabilities, its signed edge, uncertainty width, and an
explicit `simulated` flag. Rows sort by absolute edge so the most actionable markets lead,
and every count is reproducible for a given input sequence.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from poly_alpha.contracts import MarketSnapshot
from poly_alpha.research.analyst import research_markets

__all__ = ["MarketOverview", "build_overview", "dimensions", "overview_rows"]


@dataclass(frozen=True)
class MarketOverview:
    """One flattened summary row for a single market snapshot."""

    market_id: str
    question: str
    asset_class: str
    source_kind: str
    implied_yes: float | None
    model_yes: float
    edge: float
    uncertainty_width: float
    simulated: bool


def build_overview(
    snapshots: Sequence[MarketSnapshot], *, now: datetime | None = None
) -> list[MarketOverview]:
    """Research every snapshot and return one overview row per market, ranked by edge.

    Rows sort by ``abs(edge)`` descending, with ``market_id`` ascending breaking ties so
    the result is fully deterministic for a given input sequence.
    """
    overviews = [
        MarketOverview(
