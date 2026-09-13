"""Tests for the core strategy module."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from poly_alpha.strategy import (
    acceleration_config,
    candidate_from_market,
    classify_category,
    classify_market_type,
    clean_late_no_config,
    describe_market,
    jaccard_similarity,
    paper_reset_sports_core_config,
    shin_debiasing,
)

NOW = datetime(2026, 4, 7, 12, 0, tzinfo=UTC)
CFG = clean_late_no_config()


def make_market(
    question: str,
    yes_price: float = 0.10,
    volume: float = 5000.0,
    liquidity: float = 400.0,
) -> dict:
    return {
        "id": "m1",
        "question": question,
        "createdAt": "2026-04-06T12:00:00Z",
        "endDate": "2026-04-07T18:00:00Z",
        "outcomePrices": f'["{yes_price}", "{1.0 - yes_price}"]',
        "outcomes": '["Yes", "No"]',
        "volume": volume,
        "volume24hr": 1000.0,
        "liquidity": liquidity,
    }


class TestClassifyCategory:
    def test_crypto(self) -> None:
        assert classify_category("Will Bitcoin hit $100k?") == "crypto"
        assert classify_category("Will Ethereum reach $5000?") == "crypto"

    def test_sports(self) -> None:
        assert classify_category("Warriors vs. Lakers: O/U 220.5") == "sports"

    def test_politics(self) -> None:
        assert classify_category("Will Trump win the election?") == "politics"

    def test_weather(self) -> None:
        assert classify_category("Will the temperature exceed 40 degrees C?") == "weather"

    def test_esports(self) -> None:
        assert classify_category("Will T1 win VCT Masters?") == "esports"

    def test_other(self) -> None:
        assert classify_category("Will the new iPhone be released?") == "other"


class TestClassifyMarketType:
    def test_spread(self) -> None:
        assert classify_market_type("Team A vs Team B Spread: (-3.5)") == "spread"

    def test_total(self) -> None:
        assert classify_market_type("Lakers vs Warriors O/U 220.5") == "total"

    def test_exact_score(self) -> None:
        assert classify_market_type("Exact score 2-1?") == "exact_score"


class TestShinDebiasing:
    def test_returns_higher_for_favorites(self) -> None:
        result = shin_debiasing(0.90, "sports")
        assert result > 0.90

    def test_politics_minimal_adjustment(self) -> None:
        result = shin_debiasing(0.90, "politics")
        assert 0.90 < result < 0.92

    def test_crypto_strong_adjustment(self) -> None:
        result = shin_debiasing(0.90, "crypto")
        assert result > 0.92

    def test_boundary_zero(self) -> None:
        assert shin_debiasing(0.0, "sports") == pytest.approx(0.0)

    def test_boundary_one(self) -> None:
        assert shin_debiasing(1.0, "sports") == pytest.approx(1.0)


class TestJaccardSimilarity:
    def test_identical(self) -> None:
        assert jaccard_similarity("hello world", "hello world") == 1.0

    def test_no_overlap(self) -> None:
        assert jaccard_similarity("hello world", "foo bar") == 0.0

    def test_empty_strings(self) -> None:
        assert jaccard_similarity("", "") == 0.0


class TestCandidateFromMarket:
    def test_valid_sports_spread(self) -> None:
        market = make_market("Spread: Team A (-1.5)")
        candidate, reason = candidate_from_market(market, NOW, CFG)
        assert reason is None
        assert candidate is not None
        assert candidate["category"] == "sports"
        assert candidate["market_type"] == "spread"
        assert candidate["pct_elapsed"] >= 75.0

    def test_rejects_sports_moneyline(self) -> None:
        market = make_market("Will Team A win on 2026-04-07?")
        candidate, reason = candidate_from_market(market, NOW, CFG)
        assert candidate is None
        assert reason == "unsupported_sports_type"

    def test_accepts_politics_binary(self) -> None:
        market = make_market("Will Trump announce a new tariff by April 7?", yes_price=0.05)
        candidate, reason = candidate_from_market(market, NOW, CFG)
        assert reason is None
        assert candidate is not None
        assert candidate["category"] == "politics"

    def test_accepts_emotional_other(self) -> None:
        market = make_market("Will The Drama open above $12m this weekend?")
        candidate, reason = candidate_from_market(market, NOW, CFG)
        assert reason is None
        assert candidate is not None
        assert candidate["emotional"] is True

    def test_rejects_structured_other(self) -> None:
        market = make_market(
            'Will "The Drama" Opening Weekend Box Office be between $11m and $12m?'
        )
        candidate, reason = candidate_from_market(market, NOW, CFG)
        assert candidate is None
        assert reason == "structured_other"

    def test_rejects_long_term(self) -> None:
        market = make_market("Will Manchester United win the Premier League?")
        candidate, reason = candidate_from_market(market, NOW, CFG)
        assert candidate is None
        assert reason == "long_term"

    def test_uses_quoted_no_price_over_derived_complement(self) -> None:
        market = make_market("Spread: Team A (-1.5)")
        market["outcomePrices"] = '["0.10", "0.92"]'
        candidate, reason = candidate_from_market(market, NOW, CFG)
        # The quoted NO price (0.92) leaves a Shin edge below the sports minimum,
        # whereas the old derived complement (0.90) would have passed the gate.
        assert candidate is None
        assert reason == "low_edge"

    def test_respects_outcome_order(self) -> None:
        market = make_market("Spread: Team A (-1.5)")
        market["outcomePrices"] = '["0.90", "0.10"]'
        market["outcomes"] = '["No", "Yes"]'
        candidate, reason = candidate_from_market(market, NOW, CFG)
        assert reason is None
        assert candidate is not None
        assert candidate["yes_price"] == pytest.approx(0.10)
        assert candidate["no_price"] == pytest.approx(0.90)


class TestDescribeMarket:
    def test_emotional_headline(self) -> None:
        profile = describe_market("Will Elon Musk resign as Tesla CEO by April 8?")
        assert profile.category == "other"
        assert profile.emotional is True

    def test_sports_total(self) -> None:
        profile = describe_market("Lakers vs Warriors O/U 220.5")
        assert profile.category == "sports"
        assert profile.market_type == "total"


class TestStrategyPresets:
    def test_acceleration_profile(self) -> None:
        cfg = acceleration_config()
        assert cfg.max_positions == 100
        assert cfg.max_portfolio_deploy == 0.85
        assert cfg.min_trade_size == 2.0
        assert cfg.allow_synthetic_retail_fill is True

    def test_paper_reset_sports_only(self) -> None:
        cfg = paper_reset_sports_core_config()
        assert cfg.include_categories == ("sports",)
        assert cfg.allowed_sports_types == ("spread", "total")
        assert cfg.allow_emotional_other is False
        assert cfg.category_limits["politics"] == 0
