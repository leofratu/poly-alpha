"""Deterministic strategy comparison over already-resolved prediction markets.

The harness replays a fixed sequence of resolved markets through each strategy and
scores the resulting No-side betting ledger. It uses no randomness and no network
access, so identical inputs always produce identical metrics.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from poly_alpha.contracts import MarketSnapshot

Strategy = Callable[[MarketSnapshot], float | None]

MIN_EDGE: float = 0.01

CAVEAT: str = (
    "Metrics are in-sample over the supplied resolved markets, are not annualized, "
    "and are not a forecast of future performance."
)


@dataclass(frozen=True)
class ResolvedMarket:
    """A market snapshot paired with its known YES/NO resolution."""

    snapshot: MarketSnapshot
    resolved_yes: bool


@dataclass(frozen=True)
class StrategyMetrics:
    """Aggregate outcome of running one strategy over a set of resolved markets."""

    name: str
    trades: int
    hit_rate: float
    total_stake: float
    total_pnl: float
    roi: float
    max_drawdown: float

    @property
    def caveat(self) -> str:
        """Fixed disclosure that these metrics are in-sample and not annualized."""
        return CAVEAT


def _max_drawdown(equity_curve: Sequence[float]) -> float:
    peak = equity_curve[0]
    worst = 0.0
    for equity in equity_curve:
        peak = max(peak, equity)
        if peak > 0.0:
            worst = max(worst, (peak - equity) / peak)
    return max(0.0, min(1.0, worst))


def _run_strategy(
    name: str,
    strategy: Strategy,
    markets: Sequence[ResolvedMarket],
    starting_bankroll: float,
    stake_fraction: float,
    min_edge: float,
) -> StrategyMetrics:
    bankroll = starting_bankroll
    equity_curve: list[float] = [starting_bankroll]
    trades = 0
    wins = 0
    total_stake = 0.0
    for market in markets:
        snapshot = market.snapshot
        no_price = snapshot.no_price
        if no_price is None or no_price <= 0.0:
            continue
        fair_yes = strategy(snapshot)
        if fair_yes is None:
            continue
        if no_price >= (1.0 - fair_yes) - min_edge:
            continue
        stake = stake_fraction * bankroll
        if stake <= 0.0:
            continue
        shares = stake / no_price
        bankroll += (shares if not market.resolved_yes else 0.0) - stake
        total_stake += stake
        trades += 1
        if not market.resolved_yes:
            wins += 1
        equity_curve.append(bankroll)
    total_pnl = bankroll - starting_bankroll
    return StrategyMetrics(
        name=name,
        trades=trades,
        hit_rate=wins / trades if trades else 0.0,
        total_stake=total_stake,
        total_pnl=total_pnl,
        roi=total_pnl / total_stake if total_stake else 0.0,
        max_drawdown=_max_drawdown(equity_curve),
    )


def compare_strategies(
    markets: Sequence[ResolvedMarket],
    strategies: Mapping[str, Strategy],
    *,
    starting_bankroll: float = 1000.0,
    stake_fraction: float = 0.02,
    min_edge: float = MIN_EDGE,
) -> list[StrategyMetrics]:
    """Run every strategy over resolved markets and rank them by total PnL.

    A strategy receives each snapshot and returns its fair YES probability, or
    None to skip the market. A No side is bought only when the quoted No price is
    below the strategy's fair No value minus ``min_edge``. Each stake is
    ``stake_fraction`` of the running bankroll and settles at 1.0 on a No
    resolution, otherwise 0.0. Results are sorted best total PnL first.
    """
    results = [
        _run_strategy(name, strategy, markets, starting_bankroll, stake_fraction, min_edge)
        for name, strategy in strategies.items()
    ]
    return sorted(results, key=lambda metrics: metrics.total_pnl, reverse=True)
