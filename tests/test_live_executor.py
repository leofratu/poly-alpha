"""Tests for the legacy live-executor helper logic (offline)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from poly_alpha.execution.live_executor import (
    _has_date_mismatch,
    _is_long_term,
    risk_filter_and_cluster,
)


def test_has_date_mismatch_uses_word_boundaries() -> None:
    january = datetime(2026, 1, 15, tzinfo=UTC)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert _has_date_mismatch("will the mayor resign?", january, now) is False
    assert _has_date_mismatch("will it close in june?", january, now) is True


def test_has_date_mismatch_detects_stale_year() -> None:
    january = datetime(2026, 1, 15, tzinfo=UTC)
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert _has_date_mismatch("resolves in 2027?", january, now) is True


def _market(
    question: str,
    no_price: float = 0.80,
    volume24hr: float = 100.0,
    liquidity: float = 1000.0,
) -> dict:
    return {
        "question": question,
        "no_price": no_price,
        "volume24hr": volume24hr,
        "liquidity": liquidity,
    }


def test_risk_filter_drops_volume_spikes() -> None:
    spike = _market("Will the test market resolve yes?", volume24hr=5000.0, liquidity=100.0)
    assert risk_filter_and_cluster([spike]) == []


def test_risk_filter_drops_low_edge_and_sets_fields() -> None:
    low_edge = _market("Will the test market resolve yes?", no_price=0.50)
    good = _market("Will the test market resolve yes?", no_price=0.80)
    result = risk_filter_and_cluster([low_edge, good])
    assert result == [good]
    assert good["shin_edge"] > 0
    assert "shin_no_prob" in good and "category" in good


def test_risk_filter_clusters_near_duplicates() -> None:
    a = _market("Will the test market resolve yes?", no_price=0.80)
    b = _market("Will the test market resolve?", no_price=0.82)
    distinct = _market("Will Bitcoin hit 100k?", no_price=0.80)
    result = risk_filter_and_cluster([a, b, distinct])
    assert len(result) == 2
    kept = next(market for market in result if "test market" in market["question"])
    assert kept["shin_edge"] == pytest.approx(max(a["shin_edge"], b["shin_edge"]))


def test_is_long_term_detects_championship_phrasing() -> None:
    assert _is_long_term("will manchester united win the premier league?") is True
    assert _is_long_term("will it rain tomorrow?") is False
