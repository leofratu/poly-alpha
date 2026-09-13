"""Tests for the multi-adapter market registry."""

from __future__ import annotations

from poly_alpha.adapters import (
    AdapterError,
    BinaryFromSeriesAdapter,
    MarketAdapter,
    fixture_adapter,
)
from poly_alpha.adapters.registry import (
    aggregate_markets,
    default_adapters,
    default_markets,
    markets_by_kind,
    sample_series,
)
from poly_alpha.contracts import DataSourceKind, MarketSnapshot

_REQUIRED_SYMBOLS = {"BTC", "ETH", "SPY"}


class _FailingAdapter:
    """Tiny adapter whose single method always raises."""

    name = "failing"
    source_kind = DataSourceKind.SIMULATED

    def list_markets(self) -> list[MarketSnapshot]:
        raise AdapterError("synthetic failure for tests")

    def get_snapshot(self, market_id: str) -> MarketSnapshot | None:
        return None


def test_sample_series_is_deterministic_and_complete() -> None:
    first = sample_series()
    second = sample_series()
    assert first == second
    assert _REQUIRED_SYMBOLS <= set(first)
    for prices in first.values():
        assert len(prices) >= 4


def test_default_adapters_span_distinct_kinds() -> None:
    adapters = default_adapters()
