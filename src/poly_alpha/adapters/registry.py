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
from poly_alpha.adapters.kalshi import KalshiAdapter
from poly_alpha.adapters.polymarket import PolymarketAdapter
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
    """Return the fixture adapter plus crypto and equity synthetic-series adapters."""
    series = sample_series()
    crypto = {symbol: prices for symbol, prices in series.items() if symbol in {"BTC", "ETH"}}
    equities = {symbol: prices for symbol, prices in series.items() if symbol not in {"BTC", "ETH"}}
    return [
        fixture_adapter(),
        BinaryFromSeriesAdapter(crypto, asset_class="crypto"),
        BinaryFromSeriesAdapter(equities, asset_class="equity"),
    ]


def aggregate_markets(adapters: Sequence[MarketAdapter]) -> list[MarketSnapshot]:
    """Concatenate `list_markets()` across adapters in the given order.

    Adapters that raise `AdapterError` or `requests.RequestException` are
    skipped so one failed source does not blank the whole result. Snapshots are
    not deduplicated: if two adapters expose the same `market_id`, both are
    returned and resolving that collision is the caller's concern.
    """
    markets: list[MarketSnapshot] = []
    for adapter in adapters:
        try:
            markets.extend(adapter.list_markets())
        except (AdapterError, requests.RequestException):
            continue
    return markets


def markets_by_kind(adapters: Sequence[MarketAdapter]) -> dict[str, int]:
    """Count aggregated snapshots per `DataSourceKind.value`."""
    counts: dict[str, int] = {}
    for market in aggregate_markets(adapters):
        kind = market.provenance.kind.value
        counts[kind] = counts.get(kind, 0) + 1
    return counts


def default_markets() -> list[MarketSnapshot]:
    """Return the snapshots produced by `default_adapters()`."""
    return aggregate_markets(default_adapters())


def real_adapters() -> list[MarketAdapter]:
    """Return the live, read-only market adapters: Polymarket and Kalshi."""
    return [PolymarketAdapter(), KalshiAdapter()]


def real_markets() -> list[MarketSnapshot]:
    """Aggregate real snapshots; a source that fails is skipped, not fatal."""
    return aggregate_markets(real_adapters())
