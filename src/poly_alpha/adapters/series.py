"""Adapter deriving binary up/down markets from supplied price series."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime

from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    Provenance,
)

_SERIES_AS_OF = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
_PROVENANCE_SOURCE = "poly-alpha synthetic series"
_LOGISTIC_K = 25.0
_MAX_LOGIT = 60.0
_PROBABILITY_FLOOR = 1e-9


def _logistic(value: float) -> float:
    """Return a numerically safe logistic of a value."""
    clipped = max(-_MAX_LOGIT, min(_MAX_LOGIT, value))
    return 1.0 / (1.0 + math.exp(-clipped))


def _build_markets(
    series: Mapping[str, Sequence[float]],
    asset_class: str,
    as_of: datetime,
) -> list[MarketSnapshot]:
    """Convert each usable series tail into one up/down snapshot."""
    markets: list[MarketSnapshot] = []
    for symbol, prices in series.items():
        if len(prices) < 2:
            continue
        previous = float(prices[-2])
        latest = float(prices[-1])
        if previous == 0.0:
            continue
        relative_move = (latest - previous) / abs(previous)
        yes_price = _logistic(_LOGISTIC_K * relative_move)
        yes_price = min(max(yes_price, _PROBABILITY_FLOOR), 1.0 - _PROBABILITY_FLOOR)
        no_price = 1.0 - yes_price
