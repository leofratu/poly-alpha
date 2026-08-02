"""Structural interface and error type shared by all market adapters."""

from __future__ import annotations

from typing import Protocol

from poly_alpha.contracts import DataSourceKind, MarketSnapshot


class AdapterError(Exception):
    """Raised when an adapter cannot produce a valid market snapshot."""


class MarketAdapter(Protocol):
    """Structural contract every market data source adapter satisfies."""

    name: str
    source_kind: DataSourceKind

    def list_markets(self) -> list[MarketSnapshot]:
        """Return snapshots for every market the adapter currently exposes."""
        ...

    def get_snapshot(self, market_id: str) -> MarketSnapshot | None:
        """Return the snapshot for one market id, or None when it is unknown."""
        ...
