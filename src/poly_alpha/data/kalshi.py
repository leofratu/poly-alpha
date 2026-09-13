"""Kalshi Trade API v2 client for fetching open markets."""

from __future__ import annotations

from typing import Any

import requests

KALSHI_API_BASE = "https://external-api.kalshi.com/trade-api/v2"
USER_AGENT = "PolyAlpha/1.0"
DEFAULT_TIMEOUT = 30


class KalshiClient:
    """Thin read-only wrapper around the Kalshi Trade API v2."""

    def __init__(self, base_url: str = KALSHI_API_BASE, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.base_url = base_url
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT

    def get_markets(
        self,
        *,
        limit: int = 100,
        status: str = "open",
        cursor: str = "",
    ) -> dict[str, Any]:
        """Fetch one page of markets from the Kalshi Trade API."""
        params: dict[str, str] = {"limit": str(limit), "status": status}
        if cursor:
            params["cursor"] = cursor
        resp = self.session.get(
            f"{self.base_url}/markets",
            params=params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]

    def get_market(self, ticker: str) -> dict[str, Any]:
        """Fetch a single market by ticker from the Kalshi Trade API."""
        resp = self.session.get(
            f"{self.base_url}/markets/{ticker}",
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
