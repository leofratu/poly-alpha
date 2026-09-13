"""Tests for the market adapter vertical slice."""

from __future__ import annotations

from typing import Any

from poly_alpha.adapters import (
    BinaryFromSeriesAdapter,
    FixtureMarketAdapter,
    PolymarketAdapter,
    fixture_adapter,
)
from poly_alpha.contracts import DataSourceKind
from poly_alpha.data.polymarket import PolymarketClient


class _StubPolymarketClient(PolymarketClient):
    """Offline client returning canned Gamma payloads."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        super().__init__()
        self._events = events

    def get_events(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        return self._events


def _valid_market() -> dict[str, Any]:
    return {
        "id": "poly-1",
        "slug": "will-it-rain",
        "question": "Will it rain tomorrow?",
        "category": "weather",
        "outcomes": '["Yes", "No"]',
        "outcomePrices": '["0.70", "0.30"]',
        "liquidity": 1234.0,
        "volume": 5678.0,
        "endDate": "2026-06-15T12:00:00Z",
    }


def test_fixture_adapter_snapshots() -> None:
    markets = FixtureMarketAdapter().list_markets()
    assert len(markets) >= 10
    assert all(market.provenance.kind is DataSourceKind.FIXTURE for market in markets)
    assert all(market.is_tradeable for market in markets)
    assert len({market.market_id for market in markets}) == len(markets)
    for market in markets:
        assert market.yes_price is not None and 0.0 < market.yes_price < 1.0
        assert market.no_price is not None and 0.0 < market.no_price < 1.0
        assert market.orderbook
        assert all(0.0 < level.price < 1.0 for level in market.orderbook)


def test_fixture_factory_is_fresh() -> None:
    first = fixture_adapter()
    second = fixture_adapter()
    assert first is not second
    assert first.list_markets() == second.list_markets()


def test_fixture_get_snapshot_round_trip() -> None:
    adapter = FixtureMarketAdapter()
    market = adapter.list_markets()[0]
    assert adapter.get_snapshot(market.market_id) == market
    assert adapter.get_snapshot("does-not-exist") is None


def test_polymarket_adapter_maps_market() -> None:
    client = _StubPolymarketClient([{"markets": [_valid_market()]}])
    markets = PolymarketAdapter(client=client).list_markets()
    assert len(markets) == 1
    snapshot = markets[0]
    assert snapshot.market_id == "poly-1"
    assert snapshot.yes_price == 0.70
    assert snapshot.no_price == 0.30
    assert snapshot.provenance.kind is DataSourceKind.REAL
    assert snapshot.close_time is not None


def test_polymarket_adapter_accepts_list_outcomes() -> None:
    market = _valid_market()
    market["outcomes"] = ["Yes", "No"]
    market["outcomePrices"] = [0.2, 0.8]
    client = _StubPolymarketClient([{"markets": [market]}])
    markets = PolymarketAdapter(client=client).list_markets()
    assert len(markets) == 1
    assert markets[0].yes_price == 0.2


def test_polymarket_adapter_skips_malformed() -> None:
    malformed = _valid_market()
    malformed["outcomes"] = '["Yes"]'
    client = _StubPolymarketClient([{"markets": [malformed]}])
    assert PolymarketAdapter(client=client).list_markets() == []


def test_series_adapter_is_deterministic() -> None:
    series = {"BTC": [100.0, 105.0, 110.0], "ETH": [50.0, 45.0, 40.0]}
    first = BinaryFromSeriesAdapter(series)
    second = BinaryFromSeriesAdapter(series)
    assert first.list_markets() == second.list_markets()


def test_series_adapter_probabilities() -> None:
    series = {"BTC": [100.0, 120.0], "ETH": [100.0, 80.0]}
    markets = {
        market.market_id: market for market in BinaryFromSeriesAdapter(series).list_markets()
    }
    assert set(markets) == {"series:BTC", "series:ETH"}
    for market in markets.values():
        assert market.yes_price is not None and 0.0 < market.yes_price < 1.0
        assert market.no_price is not None and 0.0 < market.no_price < 1.0
        assert abs(market.yes_price + market.no_price - 1.0) < 1e-9
    assert markets["series:BTC"].yes_price > 0.5
    assert markets["series:ETH"].yes_price < 0.5
