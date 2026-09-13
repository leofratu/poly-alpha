"""Tests for the read-only JSON HTTP API."""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime

from poly_alpha.api.server import StaticProvider, create_server
from poly_alpha.contracts import AssetRef, DataSourceKind, MarketSnapshot, PriceLevel, Provenance


def _snapshot() -> MarketSnapshot:
    return MarketSnapshot(
        market_id="m1",
        question="Will it rain?",
        asset=AssetRef(symbol="RAIN", asset_class="weather"),
        yes_price=0.6,
        no_price=0.4,
        liquidity=100.0,
        volume=250.0,
        provenance=Provenance(
            source="fixture",
            kind=DataSourceKind.FIXTURE,
            retrieved_at=datetime(2026, 6, 1, 12, 0, tzinfo=UTC),
        ),
        close_time=datetime(2026, 7, 1, tzinfo=UTC),
        orderbook=(PriceLevel(price=0.6, size=10.0),),
    )


def _provider() -> StaticProvider:
    return StaticProvider(
        markets=[_snapshot()],
        research=[{"market_id": "m1", "edge": 0.05}],
        risk={"sharpe": 1.0},
        compare=[{"strategy": "a", "pnl": 2.0}],
    )


@contextmanager
def _served(provider: StaticProvider) -> Iterator[int]:
