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
