"""Deterministic, fully offline composition of the research pipeline.

This module wires the adapter registry, the offline research engine, opportunity
screening, budgeted allocation, portfolio risk, and interval calibration into one
reproducible run. It never places orders, uses no randomness, and makes no network
calls: every output is simulated, in-sample research material over labeled data,
not investment advice and not a forecast.
"""

from __future__ import annotations

from dataclasses import dataclass

from poly_alpha.adapters.registry import default_markets
from poly_alpha.backtesting.demo_data import demo_returns
from poly_alpha.portfolio.allocate import Allocation, allocate
from poly_alpha.portfolio.risk import Position, RiskReport, analyze_portfolio
from poly_alpha.research.analyst import research_markets
from poly_alpha.research.calibration import CalibrationReport, demo_calibration
from poly_alpha.research.notes import ResearchNote
from poly_alpha.research.screen import rank_opportunities

_CAVEAT = (
    "Simulated, in-sample, offline research run over labeled data. This is not "
    "investment advice, not a forecast, and no orders are placed."
)


@dataclass(frozen=True)
class ResearchBundle:
    """Deterministic end-to-end result of one offline research pipeline run."""

    market_count: int
    note_count: int
    opportunity_count: int
    allocations: tuple[Allocation, ...]
    total_fraction: float
    total_stake: float
    cash: float
    risk: RiskReport
    calibration: CalibrationReport
    caveat: str


def _position_for(allocation: Allocation, note: ResearchNote, asset_class: str) -> Position:
    """Build one risk position from an allocation, its note, and an asset class."""
