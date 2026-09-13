"""Portfolio concentration and historical risk analysis.

Risk here is descriptive: it reports how stake is concentrated and, when a real
return series is supplied, how that series historically behaved. It never
fabricates a return series to fill a gap.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

import numpy as np

from poly_alpha.contracts import Provenance

VAR_QUANTILE: float = 5.0

DEMO_CAVEAT: str = (
    "Risk figures are descriptive over the supplied positions and returns; the packaged "
    "demo inputs are simulated. This is not a forecast or investment advice."
)


@dataclass(frozen=True)
class Position:
    """A single holding with its stake, YES probability, and data provenance."""

    market_id: str
    asset_class: str
    stake: float
    yes_probability: float
    provenance: Provenance


@dataclass(frozen=True)
class RiskReport:
    """Concentration and historical risk summary for a set of positions."""

    total_stake: float
    exposure_by_class: dict[str, float]
    hhi: float
    max_position_fraction: float
    historical_var_95: float | None
    max_drawdown: float
    n_positions: int
    notes: tuple[str, ...]


def _drawdown_from_returns(returns: np.ndarray) -> float:
    equity = np.concatenate(([1.0], np.cumprod(1.0 + returns)))
    peaks = np.maximum.accumulate(equity)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdowns = np.where(peaks > 0.0, (peaks - equity) / peaks, 0.0)
    return float(min(1.0, max(0.0, float(np.max(drawdowns)))))


def analyze_portfolio(
    positions: Sequence[Position],
    returns: Sequence[float] | None = None,
) -> RiskReport:
    """Summarize concentration and, when supplied, historical return risk.

    HHI is the sum of squared stake fractions and ``max_position_fraction`` is the
    largest stake divided by total stake. ``historical_var_95`` is the 5th
    percentile of the supplied return series, an empirical rather than parametric
    estimate, and ``max_drawdown`` is read off the equity curve built from that
    same series. When ``returns`` is None or empty, VaR is None and a note records
    that a return series is required.
    """
    stakes = [position.stake for position in positions]
    for stake in stakes:
        if not np.isfinite(stake) or stake < 0.0:
            raise ValueError(f"stake must be finite and non-negative, got {stake!r}")
    total_stake = float(sum(stakes))
    exposure_by_class: dict[str, float] = {}
    for position in positions:
        exposure_by_class[position.asset_class] = (
            exposure_by_class.get(position.asset_class, 0.0) + position.stake
        )
    if total_stake > 0.0:
        hhi = float(sum((stake / total_stake) ** 2 for stake in stakes))
        max_position_fraction = max(stakes) / total_stake
    else:
        hhi = 0.0
        max_position_fraction = 0.0
    notes: list[str] = []
    if returns is None or len(returns) == 0:
        historical_var_95 = None
        max_drawdown = 0.0
        notes.append("historical VaR requires a return series; none was supplied")
    else:
        series = np.asarray(returns, dtype=float)
        if not np.all(np.isfinite(series)):
            raise ValueError("returns must all be finite")
        historical_var_95 = float(np.percentile(series, VAR_QUANTILE))
        max_drawdown = _drawdown_from_returns(series)
        notes.append(
            "historical VaR is the empirical 5th percentile of supplied returns, "
            "not a parametric estimate"
        )
    return RiskReport(
        total_stake=total_stake,
        exposure_by_class=exposure_by_class,
        hhi=hhi,
        max_position_fraction=max_position_fraction,
        historical_var_95=historical_var_95,
        max_drawdown=max_drawdown,
        n_positions=len(positions),
        notes=tuple(notes),
    )


def portfolio_value(positions: Sequence[Position], prices: Mapping[str, float]) -> float:
    """Mark positions to supplied YES prices with a simple stake * price / p mark.

    Each position with a known YES probability and a supplied price contributes
    ``stake * (price / yes_probability)``; positions missing either are carried at
    their original stake.
    """
    value = 0.0
    for position in positions:
        price = prices.get(position.market_id)
        if price is None or position.yes_probability <= 0.0:
            value += position.stake
            continue
        value += position.stake * (price / position.yes_probability)
    return value
