"""Tests for the deterministic walk-forward paper backtest."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import UTC, datetime

import pytest

from poly_alpha.adapters.history import MarketHistory
from poly_alpha.backtesting.walkforward import (
    CAVEAT,
    WalkForwardResult,
    walk_forward,
)
from poly_alpha.contracts import AssetRef, DataSourceKind, MarketSnapshot, Provenance

PROVENANCE = Provenance(
    source="test",
    kind=DataSourceKind.FIXTURE,
    retrieved_at=datetime(2026, 1, 1, tzinfo=UTC),
)


def make_snapshot(market_id: str, yes_price: float) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        question=f"Question {market_id}?",
        asset=AssetRef(symbol="TEST", asset_class="sports"),
        yes_price=yes_price,
        no_price=1.0 - yes_price,
        liquidity=1000.0,
        volume=500.0,
        provenance=PROVENANCE,
    )


def make_history(market_id: str, yes_prices: Sequence[float]) -> MarketHistory:
    snapshots = tuple(make_snapshot(market_id, yes_price) for yes_price in yes_prices)
    return MarketHistory(
        asset=snapshots[0].asset,
        snapshots=snapshots,
        provenance=PROVENANCE,
    )


def strategy_returning(fair: float | None) -> Callable[[MarketSnapshot], float | None]:
    def strategy(snapshot: MarketSnapshot) -> float | None:
        return fair

    return strategy


def test_none_strategy_yields_flat_result() -> None:
    history = make_history("wf1", [0.30, 0.30])
    result = walk_forward(history, strategy_returning(None), starting_bankroll=500.0)
    assert isinstance(result, WalkForwardResult)
    assert result.market_id == "wf1"
    assert result.trades == 0
    assert result.starting_bankroll == pytest.approx(500.0)
    assert result.ending_bankroll == pytest.approx(500.0)
    assert result.equity_curve == (500.0,)
    assert result.max_drawdown == 0.0
    assert result.caveat == CAVEAT


def test_strong_no_edge_and_final_yes_below_half_gains() -> None:
    history = make_history("wf2", [0.30, 0.30, 0.30])
    result = walk_forward(history, strategy_returning(0.20))
    assert result.trades == 1
    assert len(result.equity_curve) == 4
    assert result.ending_bankroll > result.starting_bankroll
    assert result.ending_bankroll == pytest.approx(result.equity_curve[-1])


def test_final_yes_at_or_above_half_loses() -> None:
    history = make_history("wf3", [0.60, 0.60, 0.60])
    result = walk_forward(history, strategy_returning(0.20))
    assert result.trades == 1
    assert result.ending_bankroll < result.starting_bankroll


def test_equity_curve_length_equals_processed_steps_plus_one() -> None:
    history = make_history("wf4", [0.30, 0.30, 0.30])
    result = walk_forward(history, strategy_returning(0.20))
    assert len(result.equity_curve) == len(history.snapshots) + 1


def test_max_drawdown_within_bounds() -> None:
    history = make_history("wf5", [0.30, 0.30, 0.30])
    result = walk_forward(history, strategy_returning(0.20))
    assert 0.0 <= result.max_drawdown <= 1.0


def test_walk_forward_is_deterministic() -> None:
    history = make_history("wf6", [0.30, 0.30, 0.30])
    first = walk_forward(history, strategy_returning(0.20))
    second = walk_forward(history, strategy_returning(0.20))
    assert first == second


@pytest.mark.parametrize("bankroll", [0.0, -1.0])
def test_invalid_bankroll_raises(bankroll: float) -> None:
    history = make_history("wf7", [0.30])
    with pytest.raises(ValueError):
        walk_forward(history, strategy_returning(0.20), starting_bankroll=bankroll)


@pytest.mark.parametrize("cap", [0.0, -0.1, 1.5])
def test_invalid_cap_raises(cap: float) -> None:
    history = make_history("wf8", [0.30])
    with pytest.raises(ValueError):
        walk_forward(history, strategy_returning(0.20), cap=cap)


def test_at_most_one_trade_across_many_steps() -> None:
    history = make_history("wf9", [0.30, 0.30, 0.30, 0.30, 0.30])
    result = walk_forward(history, strategy_returning(0.20))
    assert result.trades == 1
