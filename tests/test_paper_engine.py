"""Tests for paper engine scanning and market filtering logic."""

from __future__ import annotations

from poly_alpha.execution.paper_engine import (
    available_deploy_budget,
    position_size_pct,
    scan_markets,
)


class TestScanMarkets:
    def test_empty_input(self) -> None:
        candidates, rejected = scan_markets([])
        assert candidates == []
        assert rejected == {}

    def test_filters_out_bad_markets(self) -> None:
        markets = [
            {
                "id": "m1",
                "question": "Will it rain?",
                "createdAt": "2020-01-01T00:00:00Z",
                "endDate": "2020-01-02T00:00:00Z",
                "outcomePrices": '["0.50", "0.50"]',
                "outcomes": '["Yes", "No"]',
                "volume": 100,
                "liquidity": 50,
                "volume24hr": 10,
            }
        ]
        candidates, rejected = scan_markets(markets)
        assert candidates == []
        assert sum(rejected.values()) > 0


class TestPositionSizePct:
    def test_default_preset(self) -> None:
        candidate = {"market_type": "spread", "category": "sports", "shin_edge": 0.04}
        size = position_size_pct(candidate, deployed_count=0)
        assert 0.0 < size <= 0.05


def test_available_deploy_budget_does_not_double_count_deployment() -> None:
    # 1000 portfolio, 600 cap, 250 deployed this run, 750 free cash -> 350 left.
    assert available_deploy_budget(1000.0, 0.0, 250.0, 750.0, 0.6) == 350.0
    # Capital locked before this run also counts against the cap.
    assert available_deploy_budget(1000.0, 100.0, 250.0, 650.0, 0.6) == 250.0
    # Never negative, and free cash is the hard limit.
    assert available_deploy_budget(1000.0, 0.0, 700.0, 300.0, 0.6) == 0.0
    assert available_deploy_budget(1000.0, 0.0, 0.0, 40.0, 0.6) == 40.0
