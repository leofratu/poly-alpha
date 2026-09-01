"""Market adapter that maps Polymarket Gamma event/market payloads to snapshots."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    Provenance,
)
from poly_alpha.data.polymarket import GAMMA_API_BASE, PolymarketClient


def _as_list(value: Any) -> list[Any] | None:
    """Coerce a JSON string or list payload into a list, else None."""
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, ValueError):
            return None
        return parsed if isinstance(parsed, list) else None
    if isinstance(value, list):
        return value
    return None


def _to_float(value: Any) -> float | None:
    """Convert a numeric payload to float, or None when it is not numeric."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_datetime(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware datetime, or None."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def _two_sided_prices(market: dict[str, Any]) -> tuple[float, float] | None:
    """Return (yes, no) prices when the market has exactly two valid outcomes."""
    outcomes = _as_list(market.get("outcomes"))
    prices = _as_list(market.get("outcomePrices"))
    if outcomes is None or prices is None:
        return None
    if len(outcomes) != 2 or len(prices) != 2:
        return None
    lowered = [str(outcome).strip().lower() for outcome in outcomes]
    if "yes" in lowered and "no" in lowered:
        yes_index, no_index = lowered.index("yes"), lowered.index("no")
    else:
        yes_index, no_index = 0, 1
    yes_price = _to_float(prices[yes_index])
    no_price = _to_float(prices[no_index])
    if yes_price is None or no_price is None:
        return None
    if not 0.0 < yes_price < 1.0 or not 0.0 < no_price < 1.0:
        return None
    return yes_price, no_price


class PolymarketAdapter:
    """Adapter over the real Polymarket Gamma API."""

    name = "polymarket"
    source_kind = DataSourceKind.REAL

    def __init__(self, client: PolymarketClient | None = None, limit: int = 100) -> None:
        self._client = client
        self._limit = limit

    def list_markets(self) -> list[MarketSnapshot]:
        """Fetch active events and map their markets into snapshots."""
        client = self._client if self._client is not None else PolymarketClient()
        events = client.get_events(active=True, closed=False, limit=self._limit)
        snapshots: list[MarketSnapshot] = []
        for event in events:
