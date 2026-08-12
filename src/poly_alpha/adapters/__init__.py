"""Market data adapters: fixtures, Polymarket, and synthetic series."""

from poly_alpha.adapters.base import AdapterError, MarketAdapter
from poly_alpha.adapters.fixtures import FIXTURE_AS_OF, FixtureMarketAdapter, fixture_adapter
from poly_alpha.adapters.polymarket import PolymarketAdapter
from poly_alpha.adapters.series import BinaryFromSeriesAdapter

__all__ = [
    "AdapterError",
    "BinaryFromSeriesAdapter",
    "FIXTURE_AS_OF",
    "FixtureMarketAdapter",
    "MarketAdapter",
    "PolymarketAdapter",
    "fixture_adapter",
]
