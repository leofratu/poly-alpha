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
    return Position(
        market_id=allocation.market_id,
        asset_class=asset_class,
        stake=allocation.stake,
        yes_probability=note.model_yes.estimate,
        provenance=note.provenance,
    )


def run_pipeline(
    *,
    bankroll: float = 1000.0,
    cap: float = 0.05,
    max_positions: int = 20,
    max_deploy: float = 0.6,
) -> ResearchBundle:
    """Run the whole research pipeline once, offline and deterministically.

    Markets come from the adapter registry, notes from the offline research engine,
    and opportunities from conservative screening. A budgeted allocation is then
    marked into risk positions and scored against demo calibration. Constraint
    validation lives in ``allocate``; invalid values raise ``ValueError``.
    """
    markets = default_markets()
    notes = research_markets(markets)
    opportunities = rank_opportunities(notes, min_edge_low=float("-inf"))

    prices = {
        market.market_id: market.yes_price
        for market in markets
        if market.yes_price is not None
    }
    plan = allocate(
        opportunities,
        prices,
        bankroll=bankroll,
        cap=cap,
        max_positions=max_positions,
        max_deploy=max_deploy,
    )

    note_by_id = {note.market_id: note for note in notes}
    asset_class_by_id = {market.market_id: market.asset.asset_class for market in markets}
    positions = [
        _position_for(
            allocation,
