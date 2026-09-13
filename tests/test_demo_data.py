"""Tests for the clearly-labeled simulated demo dataset."""

from __future__ import annotations

import socket

import pytest

from poly_alpha.adapters.fixtures import fixture_adapter
from poly_alpha.backtesting.demo_data import (
    DEMO_NOTE,
    demo_positions,
    demo_resolved_markets,
    demo_returns,
)


def test_demo_note_labels_data_as_simulated_and_not_real() -> None:
    assert "DEMO" in DEMO_NOTE
    assert "not real" in DEMO_NOTE


def test_resolved_markets_are_deterministic() -> None:
    assert demo_resolved_markets() == demo_resolved_markets()


def test_resolved_markets_cover_every_fixture_market() -> None:
    fixture_ids = {snapshot.market_id for snapshot in fixture_adapter().list_markets()}
    demo_ids = {market.snapshot.market_id for market in demo_resolved_markets()}
    assert demo_ids == fixture_ids


def test_resolutions_include_both_outcomes_and_disagree_with_naive_rule() -> None:
    markets = demo_resolved_markets()
    demo = {market.snapshot.market_id: market.resolved_yes for market in markets}
    naive = {
        market.snapshot.market_id: (market.snapshot.yes_price or 0.0) > 0.5 for market in markets
    }
    assert any(demo[market_id] != naive[market_id] for market_id in demo)
    assert any(demo.values())
    assert not all(demo.values())


def test_positions_have_positive_total_and_valid_probabilities() -> None:
    positions = demo_positions()
    assert positions
    assert sum(position.stake for position in positions) > 0.0
    assert all(0.0 < position.yes_probability < 1.0 for position in positions)


def test_returns_have_requested_length_and_are_deterministic() -> None:
    assert len(demo_returns(60)) == 60
    assert len(demo_returns(17)) == 17
    assert demo_returns(60) == demo_returns(60)


def test_returns_contain_positive_and_negative_values() -> None:
    series = demo_returns(60)
    assert any(value > 0.0 for value in series)
    assert any(value < 0.0 for value in series)


def test_demo_data_uses_no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError("network access is not allowed in demo data")

    monkeypatch.setattr(socket, "socket", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)
    assert demo_resolved_markets()
    assert demo_positions()
    assert demo_returns()
