"""Registry aggregating several market adapters into one snapshot stream.

The platform spans prediction markets (offline fixtures) and synthetic asset
markets (price-series derived bars). This module composes those adapters
without hiding failures: an adapter that errors is skipped, not silenced.
"""

from __future__ import annotations

from collections.abc import Sequence

import requests

from poly_alpha.adapters.base import AdapterError, MarketAdapter
from poly_alpha.adapters.fixtures import fixture_adapter
from poly_alpha.adapters.series import BinaryFromSeriesAdapter
from poly_alpha.contracts import MarketSnapshot


def sample_series() -> dict[str, list[float]]:
    """Return a fixed, illustrative price series for BTC, ETH, and SPY.

    The values are hand-written for deterministic tests and demos. They are
    not market data, not observed prices, and must not be used for trading.
    """
    return {
        "BTC": [61000.0, 62400.0, 61800.0, 63500.0, 64250.0],
        "ETH": [2980.0, 3010.0, 2965.0, 3040.0, 3120.0],
        "SPY": [521.5, 523.0, 519.75, 525.4, 527.1, 528.6],
    }


def default_adapters() -> list[MarketAdapter]:
    """Return the standard fixture plus synthetic-series adapters."""
    return [fixture_adapter(), BinaryFromSeriesAdapter(sample_series())]


def aggregate_markets(adapters: Sequence[MarketAdapter]) -> list[MarketSnapshot]:
    """Concatenate `list_markets()` across adapters in the given order.

    Adapters that raise `AdapterError` or `requests.RequestException` are
    skipped so one failed source does not blank the whole result. Snapshots are
    not deduplicated: if two adapters expose the same `market_id`, both are
    returned and resolving that collision is the caller's concern.
    """
    markets: list[MarketSnapshot] = []
