"""Offline, deterministic research engine and its provenance-tagged note contracts."""

from __future__ import annotations

from poly_alpha.research.analyst import model_vs_market, research_market, research_markets
from poly_alpha.research.notes import ResearchClaim, ResearchNote

__all__ = [
    "ResearchClaim",
    "ResearchNote",
    "model_vs_market",
    "research_market",
    "research_markets",
]
