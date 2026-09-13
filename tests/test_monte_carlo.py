"""Regression tests for synthetic Monte Carlo settlement accounting."""

from __future__ import annotations

from typing import Any

import pytest

from poly_alpha.backtesting import monte_carlo


def _single_market_events(limit: int = 1000) -> list[dict[str, Any]]:
    return [{"markets": [{"question": "Will it resolve Yes?"}]}]


def test_yes_resolution_pays_nothing_on_no_shares(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(monte_carlo, "fetch_resolved_markets", _single_market_events)
    monkeypatch.setattr(monte_carlo.np.random, "rand", lambda: 0.0)
    result = monte_carlo.run(iterations=5, capital_per_trade=10_000.0, trades_per_sample=3)
    assert float(result["avg_roi"]) < 0.0
