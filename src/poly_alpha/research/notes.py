"""Provenance-tagged research note contracts with explicit uncertainty.

These are pure data containers: every claim cites its sources, and every model interval
records the basis it was derived from. Populated by the deterministic, fully offline
engine in ``poly_alpha.research.analyst``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from poly_alpha.contracts import DataSourceKind, Provenance, Uncertainty

_DIRECTIONS: frozenset[str] = frozenset({"bullish_yes", "bearish_yes", "neutral"})


@dataclass(frozen=True)
class ResearchClaim:
    """A single asserted statement about a market, with direction and claimed support."""

    text: str
    direction: str
    support: float
    sources: tuple[Provenance, ...]

    def __post_init__(self) -> None:
        if self.direction not in _DIRECTIONS:
            raise ValueError(f"unsupported direction: {self.direction!r}")
        if not 0.0 <= self.support <= 1.0:
            raise ValueError(f"support must be within [0, 1], got {self.support!r}")


@dataclass(frozen=True)
class ResearchNote:
    """A market research note with an explicit model estimate, edge, and caveats."""

    market_id: str
    question: str
    summary: str
    claims: tuple[ResearchClaim, ...]
    market_implied_yes: float | None
    model_yes: Uncertainty
    edge: Uncertainty
    provenance: Provenance
    generated_at: datetime
