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
    server = create_server(port=0, provider=provider)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server.server_address[1]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _get(port: int, path: str) -> tuple[int, object]:
    url = f"http://127.0.0.1:{port}{path}"
    with urllib.request.urlopen(url, timeout=5) as response:
        return response.status, json.loads(response.read())


def test_health() -> None:
    with _served(_provider()) as port:
        status, body = _get(port, "/health")
    assert status == 200
    assert body["status"] == "ok"
    assert "markets" in body["capabilities"]


def test_markets() -> None:
    with _served(_provider()) as port:
        status, body = _get(port, "/markets")
    assert status == 200
    assert body["count"] == 1
    market = body["data"][0]
    assert market["market_id"] == "m1"
    assert market["provenance"]["kind"] == "fixture"
    assert market["close_time"].startswith("2026-07-01")
    assert isinstance(market["orderbook"], list)


def test_research() -> None:
    with _served(_provider()) as port:
        status, body = _get(port, "/research")
    assert status == 200
    assert body["count"] == 1
    assert body["data"][0]["edge"] == 0.05
    assert body["simulated"] is True


