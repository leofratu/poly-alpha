"""Edge-case tests for the Polymarket and synthetic-series market adapters."""

from __future__ import annotations

from typing import Any

from poly_alpha.adapters import BinaryFromSeriesAdapter, PolymarketAdapter
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
        """Return the canned events without touching the network."""
        return self._events


def _market(**overrides: Any) -> dict[str, Any]:
    """Return a valid Gamma market payload with optional field overrides."""
    market: dict[str, Any] = {
        "id": "poly-edge",
        "slug": "edge-market",
        "question": "Will the edge case resolve Yes?",
        "category": "misc",
        "outcomes": ["Yes", "No"],
        "outcomePrices": ["0.6", "0.4"],
        "liquidity": 100.0,
        "volume": 200.0,
        "endDate": "2026-06-15T12:00:00Z",
    }
    market.update(overrides)
    return market


def _client(events: list[dict[str, Any]]) -> _StubPolymarketClient:
    """Wrap canned events in an offline stub client."""
    return _StubPolymarketClient(events)


def test_polymarket_maps_reversed_outcome_order() -> None:
    """The adapter selects prices by outcome name, not list position."""
    market = _market(outcomes=["No", "Yes"], outcomePrices=["0.3", "0.7"])
    markets = PolymarketAdapter(client=_client([{"markets": [market]}])).list_markets()
    assert len(markets) == 1
    assert markets[0].yes_price == 0.7
    assert markets[0].no_price == 0.3


def test_polymarket_skips_missing_question() -> None:
    """A market without a non-empty question yields no snapshot."""
    empty = _market(id="poly-empty", question="")
    missing = _market(id="poly-missing")
    missing.pop("question")
    client = _client([{"markets": [empty, missing]}])
    assert PolymarketAdapter(client=client).list_markets() == []


def test_polymarket_skips_non_numeric_prices() -> None:
    """Non-numeric price entries cause the market to be skipped."""
    market = _market(outcomes=["Yes", "No"], outcomePrices=["abc", "0.4"])
    client = _client([{"markets": [market]}])
    assert PolymarketAdapter(client=client).list_markets() == []


def test_polymarket_malformed_end_date_yields_no_close_time() -> None:
    """A malformed endDate still maps the market with close_time unset."""
    market = _market(endDate="not-a-date")
    markets = PolymarketAdapter(client=_client([{"markets": [market]}])).list_markets()
    assert len(markets) == 1
    assert markets[0].close_time is None


def test_polymarket_parses_top_level_market_event() -> None:
    """An event without a nested markets list is parsed as a market itself."""
    markets = PolymarketAdapter(client=_client([_market()])).list_markets()
    assert len(markets) == 1
    assert markets[0].market_id == "poly-edge"
    assert markets[0].provenance.kind is DataSourceKind.REAL


def test_series_skips_short_series() -> None:
    """A series with fewer than two points produces no snapshot."""
    adapter = BinaryFromSeriesAdapter({"BTC": [100.0]})
    assert adapter.list_markets() == []
    assert adapter.get_snapshot("series:BTC") is None


def test_series_skips_zero_previous_price() -> None:
    """A zero previous price cannot form a relative move and is skipped."""
    assert BinaryFromSeriesAdapter({"BTC": [0.0, 5.0]}).list_markets() == []


def test_series_handles_negative_previous_price() -> None:
    """A negative previous price still yields probabilities strictly in (0, 1)."""
    markets = BinaryFromSeriesAdapter({"BTC": [-100.0, -50.0]}).list_markets()
    assert len(markets) == 1
    yes_price = markets[0].yes_price
    no_price = markets[0].no_price
    assert yes_price is not None and 0.0 < yes_price < 1.0
    assert no_price is not None and 0.0 < no_price < 1.0


def test_series_is_deterministic_and_complementary() -> None:
    """Repeated constructions agree and each pair of prices sums to one."""
    series = {"BTC": [100.0, 110.0], "ETH": [-5.0, -6.0]}
    first = BinaryFromSeriesAdapter(series).list_markets()
    second = BinaryFromSeriesAdapter(series).list_markets()
    assert first == second
    for market in first:
        assert market.yes_price is not None and market.no_price is not None
        assert market.yes_price + market.no_price == 1.0
