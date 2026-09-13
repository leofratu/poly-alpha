"""Deterministic portfolio stress scenarios over labeled positions.

Scenarios shift YES prices by an additive number of probability points and re-mark
every position with :func:`poly_alpha.portfolio.risk.portfolio_value`. The module
is pure calculation: no randomness, no network, and no fabrication of markets that
were not supplied. Every run is reproducible from its inputs alone.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from poly_alpha.portfolio.risk import Position, portfolio_value

MIN_PRICE: float = 0.0
MAX_PRICE: float = 1.0


@dataclass(frozen=True)
class StressScenario:
    """A named additive shift, in probability points, applied to every YES price."""

    name: str
    yes_price_shift: float


@dataclass(frozen=True)
class StressResult:
    """Marked portfolio value before and after one scenario, plus its worst loss."""

    scenario: str
    start_value: float
    stressed_value: float
    change: float
    worst_market_id: str | None


def default_scenarios() -> list[StressScenario]:
    """Return the standard ordered scenario set: base, both shocks, and a crash."""
    return [
        StressScenario(name="base", yes_price_shift=0.0),
        StressScenario(name="shock_down", yes_price_shift=-0.10),
        StressScenario(name="shock_up", yes_price_shift=0.10),
        StressScenario(name="crash", yes_price_shift=-0.30),
    ]
