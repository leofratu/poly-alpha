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


def test_risk() -> None:
    with _served(_provider()) as port:
        status, body = _get(port, "/risk")
    assert status == 200
    assert body["data"] == {"sharpe": 1.0}


def test_compare() -> None:
    with _served(_provider()) as port:
        status, body = _get(port, "/compare")
    assert status == 200
    assert body["data"] == [{"strategy": "a", "pnl": 2.0}]


def test_unknown_path_returns_404() -> None:
    with _served(_provider()) as port:
        try:
            _get(port, "/nope")
        except urllib.error.HTTPError as exc:
            assert exc.code == 404
            assert json.loads(exc.read())["error"] == "not found"
        else:
            raise AssertionError("expected HTTPError 404")


def test_non_get_method_returns_405() -> None:
    with _served(_provider()) as port:
        url = f"http://127.0.0.1:{port}/health"
        request = urllib.request.Request(url, data=b"", method="POST")
        try:
            urllib.request.urlopen(request, timeout=5)
        except urllib.error.HTTPError as exc:
            assert exc.code == 405
        else:
            raise AssertionError("expected HTTPError 405")


def test_default_provider_exposes_simulated_research_and_demo_compare() -> None:
    from poly_alpha.api.server import default_provider

    provider = default_provider()
    notes = provider.research()
    assert notes
    assert all(note["model_yes"]["simulated"] is True for note in notes)
    metrics = provider.compare()
    assert metrics
    assert "roi" in metrics[0] and "trades" in metrics[0]
