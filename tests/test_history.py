"""Offline, deterministic tests for multi-step fixture histories."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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
