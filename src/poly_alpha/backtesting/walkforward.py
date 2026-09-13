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
    min_edge: float = 0.01,
) -> WalkForwardResult:
    """Replay one snapshot history into a deterministic paper equity curve.

    Snapshots are visited in order and skipped unless they are two-sided and the
    strategy returns a fair YES probability. At most one No-side position is opened:
    while no position is held and ``(1 - fair) - no_price`` exceeds ``min_edge``, the
    stake is ``kelly_fraction`` of the free bankroll with the lower-bound mode
    disabled. The position is marked at the current No price until the final
    snapshot, where it pays 1.0 per share if the final YES price is below 0.5 and
    otherwise 0.0. The curve starts at ``starting_bankroll`` and gains one point per
    processed step.

    Raises:
        ValueError: If ``starting_bankroll`` is not positive or ``cap`` is not in
            ``(0, 1]``.
    """
    if starting_bankroll <= 0.0:
        raise ValueError(f"starting_bankroll must be positive, got {starting_bankroll!r}")
    if not 0.0 < cap <= 1.0:
        raise ValueError(f"cap must be in (0, 1], got {cap!r}")
    snapshots = history.snapshots
    final_index = len(snapshots) - 1
    cash = starting_bankroll
    shares = 0.0
    trades = 0
    equity_curve: list[float] = [starting_bankroll]
    for index, snapshot in enumerate(snapshots):
        yes_price = snapshot.yes_price
        no_price = snapshot.no_price
        if yes_price is None or no_price is None:
            continue
        fair = strategy(snapshot)
        if fair is None:
            continue
        if shares == 0.0 and (1.0 - fair) - no_price > min_edge:
            decision = kelly_fraction(
                probability=1.0 - fair,
                price=no_price,
                cap=cap,
                use_lower_bound=False,
            )
            stake = cash * decision.fraction
            if stake > 0.0:
                shares = stake / no_price
                cash -= stake
