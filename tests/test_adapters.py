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
