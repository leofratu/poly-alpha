"""Tests for the multi-adapter market registry."""

from __future__ import annotations

from dataclasses import replace

import pytest

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
    real_adapters,
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
    assert set(first) >= _REQUIRED_SYMBOLS
    for prices in first.values():
        assert len(prices) >= 4


def test_default_adapters_span_distinct_kinds() -> None:
    adapters = default_adapters()
    assert len(adapters) >= 2
    kinds = {adapter.source_kind for adapter in adapters}
    assert len(kinds) >= 2


def test_aggregate_markets_sums_fixture_and_synthetic() -> None:
    adapters: list[MarketAdapter] = default_adapters()
    expected = sum(len(adapter.list_markets()) for adapter in adapters)
    markets = aggregate_markets(adapters)
    assert len(markets) == expected
    kinds = {market.provenance.kind for market in markets}
    assert DataSourceKind.FIXTURE in kinds
    assert DataSourceKind.SYNTHETIC in kinds


def test_markets_by_kind_reports_fixture_and_synthetic() -> None:
    counts = markets_by_kind(default_adapters())
    fixture_count = len(fixture_adapter().list_markets())
    synthetic_count = len(BinaryFromSeriesAdapter(sample_series()).list_markets())
    assert counts[DataSourceKind.FIXTURE.value] == fixture_count
    assert counts[DataSourceKind.SYNTHETIC.value] == synthetic_count


def test_failing_adapter_is_skipped_without_losing_others() -> None:
    good: MarketAdapter = fixture_adapter()
    markets = aggregate_markets([_FailingAdapter(), good, _FailingAdapter()])
    assert len(markets) == len(good.list_markets())
    assert all(market.provenance.kind is DataSourceKind.FIXTURE for market in markets)


def test_duplicate_ids_are_kept_not_deduplicated() -> None:
    first: MarketAdapter = fixture_adapter()
    second: MarketAdapter = fixture_adapter()
    markets = aggregate_markets([first, second])
    assert len(markets) == 2 * len(first.list_markets())
    ids = [market.market_id for market in markets]
    assert len(ids) == len(set(ids)) * 2


def test_default_markets_matches_aggregate() -> None:
    assert default_markets() == aggregate_markets(default_adapters())


def test_real_adapters_threads_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    import poly_alpha.adapters.registry as registry

    seen: list[int] = []

    class _FakeAdapter:
        def __init__(self, limit: int = 100) -> None:
            seen.append(limit)

    monkeypatch.setattr(registry, "PolymarketAdapter", _FakeAdapter)
    monkeypatch.setattr(registry, "KalshiAdapter", _FakeAdapter)
    assert len(real_adapters(limit=7)) == 2
    assert seen == [7, 7]


def test_aggregate_markets_drops_invalid_snapshots() -> None:
    good = fixture_adapter().list_markets()[0]
    bad = replace(good, yes_price=1.5)

    class _MixedAdapter:
        name = "mixed"
        source_kind = DataSourceKind.FIXTURE

        def list_markets(self) -> list[MarketSnapshot]:
            return [bad, good]

        def get_snapshot(self, market_id: str) -> MarketSnapshot | None:
            return None

    assert aggregate_markets([_MixedAdapter()]) == [good]
