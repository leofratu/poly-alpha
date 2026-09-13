"""Deterministic walk-forward paper backtest over one market's snapshot history.

The walk forward replays a single market's snapshots in order, opens at most one
No-side position when the strategy's fair value implies enough edge, marks the
position to market, and settles it against the final snapshot. It uses no
randomness and no network access, so identical inputs produce identical output.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from poly_alpha.adapters.history import MarketHistory
from poly_alpha.backtesting.comparison import max_drawdown
from poly_alpha.contracts import MarketSnapshot
from poly_alpha.portfolio.sizing import kelly_fraction

Strategy = Callable[[MarketSnapshot], float | None]

CAVEAT: str = (
    "This is a simulated in-sample walk forward over labeled fixture data. It is "
    "not annualized, not a forecast of future performance, and does not represent "
    "real returns or investment advice."
)


@dataclass(frozen=True)
class WalkForwardResult:
    """Settlement outcome of replaying one strategy over a snapshot history."""

    market_id: str
    starting_bankroll: float
    ending_bankroll: float
    equity_curve: tuple[float, ...]
    max_drawdown: float
    trades: int
    caveat: str


def walk_forward(
    history: MarketHistory,
    strategy: Strategy,
    *,
    starting_bankroll: float = 1000.0,
    cap: float = 0.05,
