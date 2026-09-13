"""Offline, deterministic tests for multi-step fixture histories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import pairwise

import pytest

from poly_alpha.adapters.history import (
    MarketHistory,
    fixture_histories,
    histories_to_markets,
    latest_snapshots,
)
from poly_alpha.contracts import DataSourceKind

_DEFAULT_STEPS = 24
_FIXED_FINAL_CLOSE = datetime(2026, 6, 20, 23, 0, tzinfo=UTC)


def test_history_count_and_length() -> None:
    histories = fixture_histories()
    assert len(histories) >= 4
    assert all(len(history.snapshots) == _DEFAULT_STEPS for history in histories)
    assert all(len(history.snapshots) == 5 for history in fixture_histories(steps=5))


def test_prices_strictly_inside_unit_interval() -> None:
    for history in fixture_histories():
        for snapshot in history.snapshots:
            assert snapshot.yes_price is not None
            assert snapshot.no_price is not None
            assert 0.0 < snapshot.yes_price < 1.0
            assert 0.0 < snapshot.no_price < 1.0
            assert abs(snapshot.yes_price + snapshot.no_price - 1.0) < 1e-9


def test_determinism_across_two_calls() -> None:
    assert fixture_histories() == fixture_histories()


def test_final_close_time_is_fixed_and_earlier_steps_back_one_day() -> None:
    for history in fixture_histories(steps=6):
        final = history.snapshots[-1]
        assert final.close_time is not None
        assert final.close_time.tzinfo is not None
        for earlier, later in pairwise(history.snapshots):
            assert earlier.close_time is not None and later.close_time is not None
            assert later.close_time - earlier.close_time == timedelta(days=1)
    assert fixture_histories()[0].snapshots[-1].close_time == _FIXED_FINAL_CLOSE


def test_market_id_and_latest() -> None:
    history = fixture_histories(steps=3)[0]
    assert history.market_id == history.snapshots[-1].market_id
    assert history.latest == history.snapshots[-1]


def test_empty_history_latest_is_none_and_market_id_raises() -> None:
    sample = fixture_histories(steps=2)[0]
    empty = MarketHistory(asset=sample.asset, snapshots=(), provenance=sample.provenance)
    assert empty.latest is None
    with pytest.raises(ValueError):
        _ = empty.market_id


def test_steps_below_two_raises() -> None:
    for steps in (-1, 0, 1):
        with pytest.raises(ValueError):
            fixture_histories(steps=steps)


def test_histories_to_markets_preserves_order_and_count() -> None:
    steps = 7
    histories = fixture_histories(steps=steps)
    flattened = histories_to_markets(histories)
    expected = [snapshot for history in histories for snapshot in history.snapshots]
    assert len(flattened) == len(histories) * steps
    assert flattened == expected


def test_latest_snapshots_count_and_identity() -> None:
    histories = fixture_histories()
    latest = latest_snapshots(histories)
    assert len(latest) == len(histories)
    assert latest == [history.snapshots[-1] for history in histories]


def test_provenance_is_fixture_and_not_real() -> None:
    for history in fixture_histories():
        assert history.provenance.kind is DataSourceKind.FIXTURE
        assert history.provenance.source == "poly-alpha fixture history"
        assert history.provenance.note
