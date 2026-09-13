"""Offline, deterministic research engine and its provenance-tagged note contracts."""

from __future__ import annotations

from poly_alpha.research.analyst import model_vs_market, research_market, research_markets
from poly_alpha.research.notes import ResearchClaim, ResearchNote
from poly_alpha.research.overview import (
    MarketOverview,
    build_overview,
    dimensions,
    overview_rows,
)

__all__ = [
    "MarketOverview",
    "ResearchClaim",
    "ResearchNote",
    "build_overview",
    "dimensions",
    "model_vs_market",
    "overview_rows",
    "research_market",
    "research_markets",
]
