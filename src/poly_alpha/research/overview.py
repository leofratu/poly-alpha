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
            market_id=note.market_id,
            question=note.question,
            asset_class=snapshot.asset.asset_class,
            source_kind=note.provenance.kind.value,
            implied_yes=note.market_implied_yes,
            model_yes=note.model_yes.estimate,
            edge=note.edge.estimate,
            uncertainty_width=note.model_yes.width,
            simulated=note.is_simulated(),
        )
        for snapshot, note in zip(snapshots, research_markets(snapshots, now=now), strict=True)
    ]
    overviews.sort(key=lambda overview: (-abs(overview.edge), overview.market_id))
    return overviews


def dimensions(overviews: Sequence[MarketOverview]) -> dict[str, dict[str, int]]:
    """Count rows per ``source_kind`` and per ``asset_class`` as nested, sorted dicts."""
    nested: dict[str, dict[str, int]] = {"source_kind": {}, "asset_class": {}}
    for overview in overviews:
        for key, value in (
            ("source_kind", overview.source_kind),
            ("asset_class", overview.asset_class),
        ):
            counts = nested[key]
            counts[value] = counts.get(value, 0) + 1
    return {key: dict(sorted(counts.items())) for key, counts in nested.items()}


def overview_rows(overviews: Sequence[MarketOverview]) -> list[tuple[str, ...]]:
    """Render overviews as plain string rows: id, class, kind, implied, model, edge, width, sim."""
    rows: list[tuple[str, ...]] = []
    for overview in overviews:
        implied = "n/a" if overview.implied_yes is None else f"{overview.implied_yes:.4f}"
        rows.append(
            (
                overview.market_id,
                overview.asset_class,
                overview.source_kind,
                implied,
                f"{overview.model_yes:.4f}",
                f"{overview.edge:+.4f}",
                f"{overview.uncertainty_width:.4f}",
                "yes" if overview.simulated else "no",
            )
        )
    return rows
