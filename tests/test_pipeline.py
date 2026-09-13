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
    second = rank_opportunities(notes)
    assert [item.note.market_id for item in first] == [item.note.market_id for item in second]

    everything = rank_opportunities(notes, min_edge_low=float("-inf"))
    assert len(everything) == len(notes)
    assert {item.note.market_id for item in everything} == {note.market_id for note in notes}


def test_kelly_fraction_stays_within_cap_for_every_overview_row() -> None:
    for row in build_overview(default_markets()):
        assert row.implied_yes is not None
        decision = kelly_fraction(probability=row.model_yes, price=row.implied_yes)
        assert 0.0 <= decision.fraction <= 0.05


def test_compare_strategies_returns_bounded_metrics_per_strategy() -> None:
    strategies = default_strategies()
    metrics = compare_strategies(demo_resolved_markets(), strategies)
    assert len(metrics) == len(strategies)
    assert all(0.0 <= metric.max_drawdown <= 1.0 for metric in metrics)
    assert all("not annualized" in metric.caveat for metric in metrics)


def test_simulate_portfolio_equity_curve_matches_trade_count() -> None:
    markets = demo_resolved_markets()
    for strategy in default_strategies().values():
        result = simulate_portfolio(markets, strategy)
        assert len(result.equity_curve) == result.trades + 1
        assert 0.0 <= result.max_drawdown <= 1.0
        assert "not a forecast" in result.caveat


def test_render_markdown_includes_disclaimer_and_is_deterministic() -> None:
    notes = research_markets(default_markets())
    opportunities = rank_opportunities(notes)
    metrics = compare_strategies(demo_resolved_markets(), default_strategies())
    risk = analyze_portfolio(demo_positions(), demo_returns())
    first = render_markdown(
        notes,
        opportunities=opportunities,
        metrics=metrics,
        risk=risk,
        generated_at=NOW,
    )
    second = render_markdown(
        notes,
