"""Tests for the deterministic paper-portfolio simulation."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime

import pytest

from poly_alpha.backtesting.comparison import ResolvedMarket
from poly_alpha.backtesting.simulation import (
    CAVEAT,
    SimulationResult,
    simulate_portfolio,
)
from poly_alpha.contracts import AssetRef, DataSourceKind, MarketSnapshot, Provenance

PROVENANCE = Provenance(
    source="test",
    kind=DataSourceKind.FIXTURE,
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def make_market(market_id: str, yes_price: float, resolved_yes: bool) -> ResolvedMarket:
    snapshot = MarketSnapshot(
        market_id=market_id,
        question=f"Question {market_id}?",
        asset=AssetRef(symbol="TEST", asset_class="sports"),
        yes_price=yes_price,
        no_price=1.0 - yes_price,
        liquidity=1000.0,
        volume=500.0,
        provenance=PROVENANCE,
    )
    return ResolvedMarket(snapshot=snapshot, resolved_yes=resolved_yes)


MARKETS = [
    make_market("m1", 0.10, resolved_yes=False),
    make_market("m2", 0.08, resolved_yes=False),
    make_market("m3", 0.80, resolved_yes=True),
]

RESOLUTIONS = {"m1": False, "m2": False, "m3": True}


def oracle(resolutions: Mapping[str, bool]) -> Callable[[MarketSnapshot], float | None]:
    def strategy(snapshot: MarketSnapshot) -> float | None:
        return 1.0 if resolutions[snapshot.market_id] else 0.0

    return strategy


def always_skip(snapshot: MarketSnapshot) -> float | None:
    return None


def test_empty_input_yields_flat_result() -> None:
    result = simulate_portfolio((), oracle(RESOLUTIONS), starting_bankroll=500.0)
    assert result.trades == 0
    assert result.starting_bankroll == pytest.approx(500.0)
    assert result.ending_bankroll == pytest.approx(500.0)
    assert result.equity_curve == (500.0,)
    assert result.max_drawdown == 0.0
    assert result.caveat == CAVEAT


def test_strong_no_edge_produces_trades_and_curve() -> None:
    result = simulate_portfolio(MARKETS, oracle(RESOLUTIONS))
    assert result.trades == 2
    assert len(result.equity_curve) == result.trades + 1
    assert result.equity_curve[0] == pytest.approx(result.starting_bankroll)
    assert result.ending_bankroll == pytest.approx(result.equity_curve[-1])
    assert result.ending_bankroll > result.starting_bankroll


def test_none_strategy_takes_no_trades() -> None:
    result = simulate_portfolio(MARKETS, always_skip)
    assert result.trades == 0
    assert result.ending_bankroll == pytest.approx(result.starting_bankroll)
    assert result.equity_curve == (result.starting_bankroll,)


def test_max_drawdown_within_bounds() -> None:
    result = simulate_portfolio(MARKETS, oracle(RESOLUTIONS))
    assert 0.0 <= result.max_drawdown <= 1.0


def test_simulation_is_deterministic() -> None:
    first = simulate_portfolio(MARKETS, oracle(RESOLUTIONS))
    second = simulate_portfolio(MARKETS, oracle(RESOLUTIONS))
