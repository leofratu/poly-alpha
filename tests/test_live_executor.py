"""Tests for the legacy live-executor helper logic (offline)."""

from __future__ import annotations

from datetime import UTC, datetime

from poly_alpha.execution.live_executor import _has_date_mismatch


def test_has_date_mismatch_uses_word_boundaries() -> None:
    january = datetime(2026, 1, 15, tzinfo=UTC)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert _has_date_mismatch("will the mayor resign?", january, now) is False
    assert _has_date_mismatch("will it close in june?", january, now) is True


def test_has_date_mismatch_detects_stale_year() -> None:
    january = datetime(2026, 1, 15, tzinfo=UTC)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert _has_date_mismatch("resolves in 2027?", january, now) is True
