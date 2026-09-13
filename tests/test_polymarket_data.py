"""Offline tests for the Polymarket Gamma data client helpers."""

from __future__ import annotations

from typing import Any

import pytest

from poly_alpha.data.polymarket import PolymarketClient, fetch_active_markets


class _PagingClient(PolymarketClient):
    """Stub client that serves one canned page per offset."""

    def __init__(self, pages: dict[int, list[dict[str, Any]]]) -> None:
        super().__init__()
        self._pages = pages
        self.offsets: list[int] = []

    def get_events(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        self.offsets.append(offset)
        return self._pages.get(offset, [])


def test_get_all_active_events_paginates_until_a_short_batch() -> None:
    client = _PagingClient({0: [{"id": "a"}, {"id": "b"}], 2: [{"id": "c"}]})
    events = client.get_all_active_events(batch_size=2)
    assert [event["id"] for event in events] == ["a", "b", "c"]
    assert client.offsets == [0, 2]


def test_get_all_active_events_stops_on_empty_page() -> None:
    client = _PagingClient({})
    assert client.get_all_active_events(batch_size=5) == []
    assert client.offsets == [0]


def test_fetch_active_markets_keeps_only_open_markets(monkeypatch: pytest.MonkeyPatch) -> None:
    events: list[dict[str, Any]] = [
        {
            "markets": [
                {"id": "open", "active": True, "closed": False},
                {"id": "closed", "active": True, "closed": True},
                {"id": "inactive", "active": False, "closed": False},
            ]
        }
    ]
    monkeypatch.setattr(
        PolymarketClient, "get_all_active_events", lambda self, batch_size=1000: events
    )
    assert fetch_active_markets() == [{"id": "open", "active": True, "closed": False}]
