"""Tests for the named-strategy library used by the comparison harness."""

from __future__ import annotations

from datetime import UTC, datetime

from poly_alpha.adapters.fixtures import fixture_adapter
from poly_alpha.backtesting.comparison import ResolvedMarket, compare_strategies
from poly_alpha.backtesting.strategies import (
    constant_half,
    default_strategies,
    describe,
    market_implied,
    shin_debiased,
    uncertainty_gated,
)
from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
)

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
STRATEGY_NAMES = {
    "market_implied",
    "shin_debiased",
    "constant_half",
    "uncertainty_gated",
}


def make_snapshot(
    *,
    market_id: str = "m1",
    question: str = "Will the test event resolve YES?",
    yes_price: float | None = 0.60,
    no_price: float | None = 0.40,
    liquidity: float = 1000.0,
    category_hint: str = "prediction",
    orderbook: tuple[PriceLevel, ...] = (),
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        question=question,
        asset=AssetRef(symbol="TEST", asset_class=category_hint),
        yes_price=yes_price,
        no_price=no_price,
        liquidity=liquidity,
        volume=5000.0,
        provenance=Provenance(
            source="test-fixture",
            kind=DataSourceKind.FIXTURE,
            retrieved_at=NOW,
        ),
        orderbook=orderbook,
    )


def test_market_implied_matches_implied_yes() -> None:
    snapshot = make_snapshot(yes_price=0.70, no_price=0.30)
    assert market_implied(snapshot) == snapshot.implied_yes()


def test_market_implied_none_without_two_sided_price() -> None:
    assert market_implied(make_snapshot(yes_price=None, no_price=None)) is None
    assert market_implied(make_snapshot(yes_price=0.60, no_price=None)) is None


def test_shin_debiased_differs_from_implied_for_favorite() -> None:
    snapshot = make_snapshot(
        question="Will BTC exceed $150k by year end?",
        yes_price=0.80,
        no_price=0.20,
    )
    implied = snapshot.implied_yes()
    result = shin_debiased(snapshot)
    assert implied is not None
    assert result is not None
    assert result != implied
    assert 0.0 <= result <= 1.0


def test_shin_debiased_none_without_two_sided_price() -> None:
    assert shin_debiased(make_snapshot(yes_price=0.60, no_price=None)) is None


def test_constant_half_always_half() -> None:
    snapshots = (
        make_snapshot(yes_price=0.10, no_price=0.90),
        make_snapshot(yes_price=0.90, no_price=0.10),
        make_snapshot(yes_price=None, no_price=None),
        fixture_adapter().list_markets()[0],
    )
    assert all(constant_half(snapshot) == 0.5 for snapshot in snapshots)


def test_uncertainty_gated_returns_none_when_lower_edge_not_positive() -> None:
    snapshot = make_snapshot(
        question="Will the test event resolve YES?",
        yes_price=0.60,
        no_price=0.40,
        liquidity=1000.0,
    )
    assert uncertainty_gated(snapshot) is None


def test_uncertainty_gated_returns_value_when_upper_edge_negative() -> None:
    bearish_book = (
        PriceLevel(price=0.05, size=200.0),
        PriceLevel(price=0.05, size=200.0),
        PriceLevel(price=0.05, size=200.0),
    )
    snapshot = make_snapshot(
        yes_price=0.30,
        no_price=0.70,
        liquidity=5000.0,
        orderbook=bearish_book,
    )
    result = uncertainty_gated(snapshot)
    assert result is not None
    assert 0.0 <= result <= 1.0


def test_uncertainty_gated_is_deterministic() -> None:
    snapshot = make_snapshot(yes_price=0.70, no_price=0.30, liquidity=5000.0)
    assert uncertainty_gated(snapshot) == uncertainty_gated(snapshot)
    assert uncertainty_gated(fixture_adapter().list_markets()[0]) == uncertainty_gated(
        fixture_adapter().list_markets()[0]
    )


def test_default_strategies_has_four_callable_entries() -> None:
    strategies = default_strategies()
    assert set(strategies) == STRATEGY_NAMES
    assert all(callable(strategy) for strategy in strategies.values())


def test_default_strategies_returns_a_fresh_dict() -> None:
    first = default_strategies()
    second = default_strategies()
    assert first is not second
    assert first == second


def test_all_strategy_outputs_are_probabilities_or_none() -> None:
    markets = fixture_adapter().list_markets()
    for strategy in default_strategies().values():
        for market in markets:
            result = strategy(market)
            assert result is None or 0.0 <= result <= 1.0


def test_describe_covers_all_strategies_and_disclaims_performance() -> None:
    descriptions = describe()
    assert set(descriptions) == STRATEGY_NAMES
    assert all(isinstance(text, str) and text for text in descriptions.values())
    assert all("\n" not in text for text in descriptions.values())
    assert all("no validated performance" in text for text in descriptions.values())


def test_default_strategies_plug_into_compare_strategies() -> None:
    markets = [
        ResolvedMarket(snapshot=market, resolved_yes=market.yes_price is not None)
        for market in fixture_adapter().list_markets()
    ]
    results = compare_strategies(markets, default_strategies())
    assert {metrics.name for metrics in results} == STRATEGY_NAMES
