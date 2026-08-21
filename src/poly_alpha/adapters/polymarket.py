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
