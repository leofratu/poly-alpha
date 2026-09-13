"""Tests for the Kalshi market adapter."""

from __future__ import annotations

from typing import Any

import pytest

from poly_alpha.adapters.kalshi import KalshiAdapter
from poly_alpha.contracts import DataSourceKind, MarketSnapshot
from poly_alpha.data.kalshi import KalshiClient

TICKER = "HIGHNY-26JUN15-T70"
EVENT_TICKER = "HIGHNY-26JUN15"
CLOSE_TIME = "2026-06-15T12:00:00Z"


class _StubKalshiClient(KalshiClient):
    """Offline client returning a canned Kalshi payload."""

    def __init__(self, payload: dict[str, Any]) -> None:
        super().__init__()
        self._payload = payload

    def get_markets(
        self,
        *,
        limit: int = 100,
        status: str = "open",
        cursor: str = "",
    ) -> dict[str, Any]:
        return self._payload


def _valid_market() -> dict[str, Any]:
    return {
        "ticker": TICKER,
        "event_ticker": EVENT_TICKER,
        "title": "Will it rain tomorrow?",
        "yes_sub_title": "Yes",
        "no_sub_title": "No",
        "yes_bid_dollars": "0.6000",
        "yes_ask_dollars": "0.7000",
        "last_price_dollars": "0.6500",
        "volume_fp": "5678.00",
        "open_interest_fp": "1234.00",
        "close_time": CLOSE_TIME,
        "status": "open",
        "result": "",
    }


def _adapter(markets: list[dict[str, Any]]) -> KalshiAdapter:
    return KalshiAdapter(client=_StubKalshiClient({"markets": markets, "cursor": ""}))


def _stable_fields(snapshot: MarketSnapshot) -> tuple[Any, ...]:
    return (
        snapshot.market_id,
        snapshot.question,
        snapshot.yes_price,
        snapshot.no_price,
        snapshot.liquidity,
        snapshot.volume,
        snapshot.close_time,
        snapshot.asset.symbol,
        snapshot.provenance.source,
        snapshot.provenance.kind,
        snapshot.provenance.url,
    )


def test_kalshi_adapter_maps_market() -> None:
    markets = _adapter([_valid_market()]).list_markets()
    assert len(markets) == 1
    snapshot = markets[0]
    assert snapshot.market_id == TICKER
    assert snapshot.question == "Will it rain tomorrow?"
    assert snapshot.yes_price == pytest.approx(0.65)
    assert snapshot.no_price == pytest.approx(0.35)
    assert snapshot.liquidity == 1234.0
    assert snapshot.volume == 5678.0
    assert snapshot.asset.symbol == EVENT_TICKER
    assert snapshot.asset.asset_class == "prediction"
    assert snapshot.provenance.kind is DataSourceKind.REAL
    assert snapshot.provenance.source == "Kalshi public API"
    assert snapshot.close_time is not None
    assert snapshot.close_time.tzinfo is not None
