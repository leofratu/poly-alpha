from datetime import datetime, timezone

from strategy_core import (
    acceleration_config,
    candidate_from_market,
    clean_late_no_config,
    describe_market,
    paper_reset_sports_core_config,
)


NOW = datetime(2026, 4, 7, 12, 0, tzinfo=timezone.utc)
CFG = clean_late_no_config()


def make_market(question: str, yes_price: float = 0.10, volume: float = 5000.0, liquidity: float = 400.0):
    return {
        "id": "m1",
        "question": question,
        "createdAt": "2026-04-06T12:00:00Z",
        "endDate": "2026-04-07T18:00:00Z",
        "outcomePrices": f"[{yes_price}, {1.0-yes_price}]",
        "outcomes": '["Yes", "No"]',
        "volume": volume,
        "volume24hr": 1000.0,
        "liquidity": liquidity,
    }


def test_describe_market_tags_emotional_headline_binary():
    profile = describe_market("Will Elon Musk resign as Tesla CEO by April 8?")
    assert profile.category == "other"
    assert profile.market_type == "moneyline"
    assert profile.emotional is True


def test_candidate_accepts_late_sports_spread():
    market = make_market("Spread: Team A (-1.5)")
    candidate, reason = candidate_from_market(market, NOW, CFG)
    assert reason is None
    assert candidate is not None
    assert candidate["category"] == "sports"
    assert candidate["market_type"] == "spread"
    assert candidate["pct_elapsed"] >= 75.0


def test_candidate_rejects_sports_moneyline_even_when_emotional_band_fits():
    market = make_market("Will Team A win on 2026-04-07?")
    candidate, reason = candidate_from_market(market, NOW, CFG)
    assert candidate is None
    assert reason == "unsupported_sports_type"


def test_candidate_accepts_politics_binary():
    market = make_market("Will Trump announce a new tariff by April 7?", yes_price=0.05)
    candidate, reason = candidate_from_market(market, NOW, CFG)
    assert reason is None
    assert candidate is not None
    assert candidate["category"] == "politics"


def test_candidate_accepts_emotional_other_binary_but_rejects_structured_other():
    binary_market = make_market("Will The Drama open above $12m this weekend?")
    candidate, reason = candidate_from_market(binary_market, NOW, CFG)
    assert reason is None
    assert candidate is not None
    assert candidate["category"] == "other"
    assert candidate["emotional"] is True

    structured_market = make_market('Will "The Drama" Opening Weekend Box Office be between $11m and $12m?')
    candidate, reason = candidate_from_market(structured_market, NOW, CFG)
    assert candidate is None
    assert reason == "structured_other"


def test_acceleration_profile_targets_100_slots_with_smaller_trade_size():
    cfg = acceleration_config()
    assert cfg.max_positions == 100
    assert cfg.max_portfolio_deploy == 0.85
    assert cfg.min_trade_size == 2.0
    assert cfg.jaccard_threshold == 0.85
    assert cfg.category_limits["sports"] >= 60
    assert cfg.category_limits["weather"] >= 10
    assert cfg.allow_synthetic_retail_fill is True


def test_paper_reset_profile_bans_garbage_sleeves_and_focuses_sports_derivatives():
    cfg = paper_reset_sports_core_config()
    assert cfg.include_categories == ("sports",)
    assert cfg.allowed_sports_types == ("spread", "total")
    assert cfg.allow_emotional_other is False
    assert cfg.category_limits["politics"] == 0
    assert cfg.allow_synthetic_retail_fill is False
    assert cfg.max_positions == 40
