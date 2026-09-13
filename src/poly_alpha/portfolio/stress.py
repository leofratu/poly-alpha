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


def _shifted_prices(prices: Mapping[str, float], yes_price_shift: float) -> dict[str, float]:
    """Clamp every supplied price after shifting, preserving the original key set."""
    return {
        market_id: min(MAX_PRICE, max(MIN_PRICE, price + yes_price_shift))
        for market_id, price in prices.items()
    }


def _worst_market_id(
    positions: Sequence[Position],
    prices: Mapping[str, float],
    shifted: Mapping[str, float],
) -> str | None:
    """Return the market with the most negative per-position change, if any.

    Ties on the change are broken by ascending market id so the choice is stable.
    """
    worst: tuple[float, str] | None = None
    for position in positions:
        before = portfolio_value([position], prices)
        after = portfolio_value([position], shifted)
        change = after - before
        if change >= 0.0:
            continue
        candidate = (change, position.market_id)
        if worst is None or candidate < worst:
            worst = candidate
    return None if worst is None else worst[1]


def apply_stress(
    positions: Sequence[Position],
    prices: Mapping[str, float],
    scenario: StressScenario,
) -> StressResult:
    """Mark ``positions`` under one additive YES-price scenario.

    ``yes_price_shift`` is added in probability points; each shifted price is
    clamped to ``[0.0, 1.0]`` and the price key set is left unchanged. ``change`` is
    the stressed minus start value, and ``worst_market_id`` names the position with
    the most negative change, or None when nothing loses value.
    """
    baseline = _shifted_prices(prices, 0.0)
    start_value = portfolio_value(positions, baseline)
    shifted = _shifted_prices(prices, scenario.yes_price_shift)
    stressed_value = portfolio_value(positions, shifted)
    return StressResult(
        scenario=scenario.name,
        start_value=start_value,
        stressed_value=stressed_value,
        change=stressed_value - start_value,
        worst_market_id=_worst_market_id(positions, baseline, shifted),
    )


def run_scenarios(
    positions: Sequence[Position],
    prices: Mapping[str, float],
    scenarios: Sequence[StressScenario] | None = None,
) -> list[StressResult]:
    """Apply each scenario in order, defaulting to :func:`default_scenarios`."""
    active = default_scenarios() if scenarios is None else list(scenarios)
    return [apply_stress(positions, prices, scenario) for scenario in active]
