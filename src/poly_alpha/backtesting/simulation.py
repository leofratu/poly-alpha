"""Deterministic paper-portfolio simulation over already-resolved markets.

The simulator replays a fixed sequence of resolved markets through a fair-probability
strategy, sizes each No-side bet with uncertainty-aware Kelly sizing, and records the
resulting equity curve. It uses no randomness and no network access, so identical
inputs always produce identical output.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from poly_alpha.backtesting.comparison import ResolvedMarket
from poly_alpha.contracts import MarketSnapshot
from poly_alpha.portfolio.sizing import kelly_fraction

Strategy = Callable[[MarketSnapshot], float | None]

CAVEAT: str = (
    "This is a simulated in-sample result over the supplied resolved markets. It is "
    "not annualized, not a forecast of future performance, and does not represent "
    "real returns or investment advice."
)


@dataclass(frozen=True)
class SimulationResult:
    """Settlement outcome of replaying a strategy into a paper bankroll."""

    starting_bankroll: float
    ending_bankroll: float
    equity_curve: tuple[float, ...]
    max_drawdown: float
    trades: int
    caveat: str


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0]
    worst = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0.0:
            worst = max(worst, (peak - equity) / peak)
    return max(0.0, min(1.0, worst))
