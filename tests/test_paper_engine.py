"""Tests for paper engine scanning and market filtering logic."""

from __future__ import annotations

from poly_alpha.execution.paper_engine import position_size_pct, scan_markets


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
