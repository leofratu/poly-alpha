"""Market adapter that maps Kalshi Trade API payloads to snapshots."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    Provenance,
)
from poly_alpha.data.kalshi import KALSHI_API_BASE, KalshiClient


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


def _dollars(market: dict[str, Any], key: str) -> float | None:
    """Parse a fixed-point dollar field, falling back to legacy integer cents."""
    value = _to_float(market.get(key))
    if value is not None:
        return value
    legacy = _to_float(market.get(key.removesuffix("_dollars")))
    if legacy is None:
        return None
    return legacy / 100.0


def _yes_price(market: dict[str, Any]) -> float | None:
    """Derive the YES price from the two-sided quote, last trade, or one side."""
    bid = _dollars(market, "yes_bid_dollars")
    ask = _dollars(market, "yes_ask_dollars")
    if bid is not None and ask is not None and 0.0 < bid < 1.0 and 0.0 < ask < 1.0:
        return (bid + ask) / 2.0
    last = _dollars(market, "last_price_dollars")
    if last is not None and 0.0 < last < 1.0:
        return last
    for candidate in (bid, ask):
        if candidate is not None and 0.0 < candidate < 1.0:
            return candidate
    return None
