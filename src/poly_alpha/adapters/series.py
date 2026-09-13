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
        provenance = Provenance(
            source=_PROVENANCE_SOURCE,
            kind=DataSourceKind.SYNTHETIC,
            retrieved_at=as_of,
            note="Prices are a supplied/synthetic series; probabilities use the last two points only.",
        )
        markets.append(
            MarketSnapshot(
                market_id=f"series:{symbol}",
                question=f"Will {symbol} close above its previous price?",
                asset=AssetRef(
                    symbol=symbol,
                    asset_class=asset_class,
                    description="Synthetic price series",
                ),
                yes_price=yes_price,
                no_price=no_price,
                liquidity=1000.0,
                volume=float(len(prices)),
                provenance=provenance,
                close_time=as_of,
            )
        )
    return markets


class BinaryFromSeriesAdapter:
    """Deterministic adapter turning price-series tails into binary markets."""

    name = "series"
    source_kind = DataSourceKind.SYNTHETIC

    def __init__(
        self,
        series: Mapping[str, Sequence[float]],
        asset_class: str = "crypto",
        as_of: datetime | None = None,
    ) -> None:
        self._as_of = as_of if as_of is not None else _SERIES_AS_OF
        self._markets = _build_markets(series, asset_class, self._as_of)
        self._by_id = {market.market_id: market for market in self._markets}

    def list_markets(self) -> list[MarketSnapshot]:
        """Return one up/down snapshot per usable asset series."""
        return list(self._markets)

    def get_snapshot(self, market_id: str) -> MarketSnapshot | None:
        """Return the synthetic snapshot for an id, or None when unknown."""
        return self._by_id.get(market_id)
