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

_MAX_PAGE_SIZE = 1000


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


class KalshiAdapter:
    """Adapter over the real Kalshi Trade API."""

    name = "kalshi"
    source_kind = DataSourceKind.REAL

    def __init__(self, client: KalshiClient | None = None, limit: int = 100) -> None:
        self._client = client
        self._limit = limit

    def list_markets(self) -> list[MarketSnapshot]:
        """Fetch up to ``limit`` open markets, following the API cursor."""
        client = self._client if self._client is not None else KalshiClient()
        snapshots: list[MarketSnapshot] = []
        cursor = ""
        while len(snapshots) < self._limit:
            page_size = min(_MAX_PAGE_SIZE, self._limit - len(snapshots))
            payload = client.get_markets(limit=page_size, status="open", cursor=cursor)
            if not isinstance(payload, dict):
                break
            raw_markets = payload.get("markets")
            if not isinstance(raw_markets, list):
                break
            for market in raw_markets:
                if isinstance(market, dict):
                    snapshot = self._parse_market(market)
                    if snapshot is not None:
                        snapshots.append(snapshot)
            next_cursor = payload.get("cursor")
            if not isinstance(next_cursor, str) or not next_cursor:
                break
            cursor = next_cursor
        return snapshots

    def get_snapshot(self, market_id: str) -> MarketSnapshot | None:
        """Return the live snapshot for an id, or None when it is not found."""
        for snapshot in self.list_markets():
            if snapshot.market_id == market_id:
                return snapshot
        return None

    def _parse_market(self, market: dict[str, Any]) -> MarketSnapshot | None:
        """Map one raw Kalshi market dict, skipping malformed payloads."""
        ticker = str(market.get("ticker") or "").strip()
        if not ticker:
            return None
        if market.get("market_type") not in (None, "binary"):
            return None
        yes_price = _yes_price(market)
        if yes_price is None:
            return None
        question = str(market.get("title") or market.get("yes_sub_title") or ticker).strip()
        provenance = Provenance(
            source="Kalshi public API",
            kind=DataSourceKind.REAL,
            url=KALSHI_API_BASE,
            retrieved_at=datetime.now(UTC),
            note=(
                "YES price is the bid/ask midpoint in dollars (or the last/one-sided quote "
                "when a side is missing); liquidity and volume are contract counts "
                "(open interest / volume), not dollar amounts."
            ),
        )
        return MarketSnapshot(
            market_id=ticker,
            question=question,
            asset=AssetRef(
                symbol=str(market.get("event_ticker") or ticker),
                asset_class="prediction",
                description=question,
            ),
            yes_price=yes_price,
            no_price=1.0 - yes_price,
            liquidity=_to_float(market.get("open_interest_fp")) or 0.0,
            volume=_to_float(market.get("volume_fp")) or 0.0,
            provenance=provenance,
            close_time=_parse_datetime(market.get("close_time")),
        )
