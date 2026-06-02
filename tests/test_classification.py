"""Tests for market classification and financial target extraction."""

from __future__ import annotations

from poly_alpha.data.tradfi import PriceDirection, extract_financial_target
from poly_alpha.strategy import classify_category, classify_market_type, describe_market


class TestClassifyCategory:
    def test_crypto_keywords(self) -> None:
        assert classify_category("Will Bitcoin hit $100k?") == "crypto"
        assert classify_category("Will Ethereum reach $5000 by June?") == "crypto"
        assert classify_category("Solana market cap above $50B?") == "crypto"

    def test_sports_keywords(self) -> None:
        assert classify_category("Lakers vs. Warriors: O/U 220.5") == "sports"
        assert classify_category("Will Arsenal win on Saturday?") == "sports"
        assert classify_category("Spread: Team A (-3.5)") == "sports"

    def test_politics_keywords(self) -> None:
        assert classify_category("Will Trump impose tariffs on China?") == "politics"
        assert classify_category("Will there be a ceasefire?") == "politics"
        assert classify_category("Will congress pass the bill?") == "politics"

    def test_weather_keywords(self) -> None:
        assert classify_category("Will NYC temperature exceed 100 degrees F?") == "weather"
        assert classify_category("Will there be a hurricane in Florida?") == "weather"

    def test_esports_keywords(self) -> None:
        assert classify_category("Will T1 win game 2 of VCT Masters?") == "esports"
        assert classify_category("League of Legends worlds first blood?") == "esports"

    def test_other_default(self) -> None:
        assert classify_category("Will the new iPhone be released in September?") == "other"


class TestClassifyMarketType:
    def test_spread(self) -> None:
        assert classify_market_type("Spread: Lakers (-5.5)") == "spread"
        assert classify_market_type("Team A vs Team B (-3.5)") == "spread"

    def test_total(self) -> None:
        assert classify_market_type("Lakers vs Warriors O/U 220.5") == "total"

    def test_exact_score(self) -> None:
        assert classify_market_type("Exact score 2-1 in the final?") == "exact_score"

    def test_halftime(self) -> None:
        assert classify_market_type("Who leads at halftime?") == "halftime"
        assert classify_market_type("First half moneyline winner?") == "halftime"

    def test_range(self) -> None:
        assert classify_market_type("Will it be between $100 and $200?") == "range"

    def test_binary_default(self) -> None:
        # "Will" at start triggers moneyline check; use a non-will phrasing
        assert classify_market_type("Is the temperature above 30?") == "binary"


class TestDescribeMarket:
    def test_sports_spread_not_emotional(self) -> None:
        profile = describe_market("Spread: Lakers (-5.5) vs Warriors")
        assert profile.category == "sports"
        assert profile.market_type == "spread"
        assert profile.emotional is False

    def test_politics_is_emotional(self) -> None:
        profile = describe_market("Will Trump announce new tariffs?")
        assert profile.category == "politics"
        assert profile.emotional is True

    def test_celebrity_other_is_emotional(self) -> None:
        # "Elon Musk" triggers emotional pattern; "tweet" keeps it in "other"
        profile = describe_market("Will Elon Musk tweet about his new movie?")
        assert profile.category == "other"
        assert profile.emotional is True


class TestExtractFinancialTarget:
    def test_bitcoin_above(self) -> None:
        result = extract_financial_target("Will Bitcoin hit $100k by June?")
        assert result is not None
        assert result.ticker == "BTC-USD"
        assert result.target_price == 100_000.0
        assert result.direction == PriceDirection.ABOVE

    def test_spy_above(self) -> None:
        result = extract_financial_target("Will SPY close above 500?")
        assert result is not None
        assert result.ticker == "SPY"
        assert result.target_price == 500.0

    def test_ethereum_below(self) -> None:
        result = extract_financial_target("Will Ethereum crash below $2000?")
        assert result is not None
        assert result.ticker == "ETH-USD"
        assert result.direction == PriceDirection.BELOW

    def test_no_match(self) -> None:
        result = extract_financial_target("Will it rain tomorrow?")
        assert result is None

    def test_empty_string(self) -> None:
        result = extract_financial_target("")
        assert result is None
