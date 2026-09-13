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

