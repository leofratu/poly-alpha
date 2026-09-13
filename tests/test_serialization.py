"""Tests for the JSON serialization helpers used by the read-only API."""

from __future__ import annotations

from datetime import UTC, datetime

from poly_alpha.api.server import to_jsonable
from poly_alpha.contracts import DataSourceKind, Uncertainty

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


