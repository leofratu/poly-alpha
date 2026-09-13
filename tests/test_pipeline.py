"""End-to-end, fully offline pipeline tests across adapters, research, and backtesting."""

from __future__ import annotations

from datetime import UTC, datetime

from poly_alpha.adapters.registry import default_markets
from poly_alpha.backtesting.comparison import compare_strategies
from poly_alpha.backtesting.demo_data import demo_positions, demo_resolved_markets, demo_returns
from poly_alpha.backtesting.simulation import simulate_portfolio
from poly_alpha.backtesting.strategies import default_strategies
from poly_alpha.contracts import DataSourceKind
from poly_alpha.portfolio.risk import analyze_portfolio
from poly_alpha.portfolio.sizing import kelly_fraction
from poly_alpha.research.analyst import research_markets
from poly_alpha.research.overview import build_overview
from poly_alpha.research.report import render_markdown
from poly_alpha.research.screen import rank_opportunities
from poly_alpha.validation import validate_snapshot

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
_EPSILON = 1e-9


def test_default_markets_span_fixture_and_synthetic_without_validation_issues() -> None:
    markets = default_markets()
    kinds = {market.provenance.kind for market in markets}
    assert DataSourceKind.FIXTURE in kinds
    assert DataSourceKind.SYNTHETIC in kinds
    assert all(validate_snapshot(market) == () for market in markets)


def test_overview_has_one_simulated_row_per_market() -> None:
    markets = default_markets()
    overviews = build_overview(markets)
    assert len(overviews) == len(markets)
    assert all(row.simulated for row in overviews)
    assert all(row.uncertainty_width >= 0.0 for row in overviews)
    for row in overviews:
        assert row.implied_yes is not None
        assert abs(row.edge - (row.model_yes - row.implied_yes)) <= _EPSILON


def test_rank_opportunities_is_deterministic_and_keeps_all_at_negative_infinity() -> None:
    notes = research_markets(default_markets())
    first = rank_opportunities(notes)
