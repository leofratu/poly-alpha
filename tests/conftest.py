"""Shared test fixtures."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from poly_alpha.strategy import StrategyConfig, clean_late_no_config


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 6, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def cfg() -> StrategyConfig:
    return clean_late_no_config()


@pytest.fixture
def sample_market() -> dict:
    """A market that should pass all filters."""
    return {
        "id": "test-market-1",
        "question": "Will Team A vs. Team B: O/U 4.5 resolve Yes?",
        "createdAt": "2026-05-29T12:00:00Z",
        "endDate": "2026-06-02T12:00:00Z",
        "outcomePrices": '["0.10", "0.90"]',
        "outcomes": '["Yes", "No"]',
        "volume": 5000.0,
        "liquidity": 400.0,
        "volume24hr": 200.0,
    }
