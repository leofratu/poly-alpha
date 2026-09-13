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
    equity = np.cumprod(1.0 + returns)
