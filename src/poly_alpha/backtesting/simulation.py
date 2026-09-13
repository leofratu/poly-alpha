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


def simulate_portfolio(
    markets: Sequence[ResolvedMarket],
    strategy: Strategy,
    *,
    starting_bankroll: float = 1000.0,
    cap: float = 0.05,
    min_edge: float = 0.01,
) -> SimulationResult:
    """Replay resolved markets into a deterministic paper-portfolio equity curve.

    A market is skipped unless it is two-sided and the strategy returns a fair YES
    probability. A No-side bet is taken only when the strategy's fair No value
    exceeds the quoted No price by at least ``min_edge``. The stake is
    ``kelly_fraction`` of the running bankroll with the lower-bound mode disabled,
    and it settles at ``1.0`` per share on a No resolution, otherwise at ``0.0``.

    Raises:
        ValueError: If ``starting_bankroll`` is not positive or ``cap`` is not in
            ``(0, 1]``.
    """
    if starting_bankroll <= 0.0:
        raise ValueError(f"starting_bankroll must be positive, got {starting_bankroll!r}")
    if not 0.0 < cap <= 1.0:
        raise ValueError(f"cap must be in (0, 1], got {cap!r}")
    bankroll = starting_bankroll
    equity_curve: list[float] = [starting_bankroll]
    trades = 0
    for market in markets:
        snapshot = market.snapshot
        no_price = snapshot.no_price
        if snapshot.yes_price is None or no_price is None:
            continue
        fair = strategy(snapshot)
        if fair is None:
            continue
        if (1.0 - fair) - no_price < min_edge:
            continue
        decision = kelly_fraction(
            probability=1.0 - fair,
            price=no_price,
            cap=cap,
            use_lower_bound=False,
        )
        if decision.fraction <= 0.0:
