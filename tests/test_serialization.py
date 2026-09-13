"""Tests for the JSON serialization helpers used by the read-only API."""

from __future__ import annotations

from datetime import UTC, datetime

from poly_alpha.api.server import snapshot_to_dict, to_jsonable
from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
    Uncertainty,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


def test_to_jsonable_converts_enums_datetimes_and_containers() -> None:
    payload = {
        "kind": DataSourceKind.REAL,
        "when": NOW,
        "band": Uncertainty(estimate=0.5, low=0.4, high=0.6),
        "items": (1, 2),
        "tags": {"a"},
    }
    result = to_jsonable(payload)
    assert result["kind"] == "real"
    assert result["when"].startswith("2026-06-01T12:00:00")
    assert result["band"]["estimate"] == 0.5
    assert "width" not in result["band"]
    assert result["items"] == [1, 2]
    assert result["tags"] == ["a"]


def test_snapshot_to_dict_is_json_safe() -> None:
    snapshot = MarketSnapshot(
        market_id="m1",
        question="Will it rain?",
        asset=AssetRef(symbol="RAIN", asset_class="weather"),
        yes_price=0.6,
        no_price=0.4,
        liquidity=100.0,
        volume=250.0,
        provenance=Provenance(source="fixture", kind=DataSourceKind.FIXTURE, retrieved_at=NOW),
        close_time=NOW,
        orderbook=(PriceLevel(price=0.6, size=10.0),),
    )
    data = snapshot_to_dict(snapshot)
    assert data["market_id"] == "m1"
    assert data["provenance"]["kind"] == "fixture"
    assert data["close_time"].startswith("2026-06-01")
    assert data["orderbook"] == [{"price": 0.6, "size": 10.0}]
