"""Polymarket Gamma API client for fetching active markets and events."""

from __future__ import annotations

from typing import Any

import requests

GAMMA_API_BASE = "https://gamma-api.polymarket.com"
USER_AGENT = "PolyAlpha/1.0"
DEFAULT_TIMEOUT = 30


class PolymarketClient:
    """Thin wrapper around the Polymarket Gamma REST API."""

    def __init__(self, base_url: str = GAMMA_API_BASE, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def get_events(
        self,
        *,
        active: bool = True,
        closed: bool = False,
        limit: int = 100,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Fetch events from the Gamma API."""
        params: dict[str, str] = {
            "active": str(active).lower(),
            "closed": str(closed).lower(),
            "limit": str(limit),
            "offset": str(offset),
        }
        resp = self.session.get(
            f"{self.base_url}/events",
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def get_all_active_events(self, batch_size: int = 1000) -> list[dict[str, Any]]:
        """Paginate through all active events."""
        all_events: list[dict[str, Any]] = []
        offset = 0
        while True:
            batch = self.get_events(active=True, closed=False, limit=batch_size, offset=offset)
            if not batch:
                break
            all_events.extend(batch)
            if len(batch) < batch_size:
                break
            offset += batch_size
        return all_events


def fetch_active_markets(batch_size: int = 1000) -> list[dict[str, Any]]:
    """Fetch all active markets from all active events (convenience function)."""
    client = PolymarketClient()
    events = client.get_all_active_events(batch_size=batch_size)
    markets: list[dict[str, Any]] = []
    for event in events:
        for market in event.get("markets", []):
            if market.get("active") and not market.get("closed"):
                markets.append(market)
    return markets
