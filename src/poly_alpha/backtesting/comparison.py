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
