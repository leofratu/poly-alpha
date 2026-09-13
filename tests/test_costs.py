"""Tests for the execution-cost model."""

from __future__ import annotations

import pytest

from poly_alpha.backtesting.costs import CostModel, walk_book
from poly_alpha.contracts import PriceLevel


def test_zero_cost_model_leaves_price_unchanged() -> None:
    model = CostModel()
    assert model.effective_price(0.4, "buy") == pytest.approx(0.4)
    assert model.effective_price(0.4, "sell") == pytest.approx(0.4)
    assert model.total_bps == pytest.approx(0.0)


def test_buy_raises_price_and_sell_lowers_it() -> None:
    model = CostModel(fee_bps=100.0, slippage_bps=50.0)
    assert model.effective_price(0.5, "buy") > 0.5
    assert model.effective_price(0.5, "sell") < 0.5


def test_side_is_case_insensitive() -> None:
    model = CostModel(fee_bps=100.0)
    assert model.effective_price(0.5, "BUY") == pytest.approx(model.effective_price(0.5, "buy"))
    assert model.effective_price(0.5, "Sell") == pytest.approx(model.effective_price(0.5, "sell"))


def test_total_bps_sums_fee_and_slippage() -> None:
    model = CostModel(fee_bps=20.0, slippage_bps=5.0)
    assert model.total_bps == pytest.approx(25.0)


def test_net_edge_shrinks_as_costs_rise() -> None:
    cheap = CostModel(fee_bps=10.0)
    pricey = CostModel(fee_bps=200.0)
    cheap_edge = cheap.net_edge(fair_probability=0.6, price=0.5)
    pricey_edge = pricey.net_edge(fair_probability=0.6, price=0.5)
    assert cheap_edge > pricey_edge


def test_net_edge_flips_sign_for_marginal_edge() -> None:
    fair, price = 0.55, 0.54
    cheap = CostModel(fee_bps=10.0)
    pricey = CostModel(fee_bps=500.0)
    assert cheap.net_edge(fair_probability=fair, price=price) > 0.0
    assert pricey.net_edge(fair_probability=fair, price=price) < 0.0


def test_net_edge_sell_uses_other_side() -> None:
    model = CostModel(fee_bps=100.0)
    edge = model.net_edge(fair_probability=0.3, price=0.6, side="sell")
    expected = (1.0 - 0.3) - (1.0 - model.effective_price(0.6, "sell"))
    assert edge == pytest.approx(expected)
    assert edge > 0.0


@pytest.mark.parametrize("side", ["hold", "", "BUYS"])
def test_invalid_side_raises(side: str) -> None:
    model = CostModel()
    with pytest.raises(ValueError):
        model.effective_price(0.5, side)
    with pytest.raises(ValueError):
        model.net_edge(fair_probability=0.5, price=0.5, side=side)


@pytest.mark.parametrize("bad", [-1.0, -0.01, float("nan"), float("inf")])
def test_invalid_bps_raises(bad: float) -> None:
    with pytest.raises(ValueError):
        CostModel(fee_bps=bad)
    with pytest.raises(ValueError):
        CostModel(slippage_bps=bad)


def test_effective_price_clamps_at_bounds() -> None:
    huge = CostModel(fee_bps=1_000_000.0)
    assert huge.effective_price(0.5, "buy") == 1.0
    assert huge.effective_price(0.5, "sell") == 0.0
    assert CostModel().effective_price(1.0, "buy") == 1.0
    assert CostModel().effective_price(0.0, "sell") == 0.0


def _book() -> tuple[PriceLevel, ...]:
    return (PriceLevel(0.60, 100.0), PriceLevel(0.50, 100.0))


def test_walk_book_buy_consumes_cheapest_first() -> None:
    fill = walk_book(_book(), 150.0, side="buy")
    assert fill.shares == pytest.approx(150.0)
    assert fill.average_price == pytest.approx(80.0 / 150.0)
    assert fill.levels_consumed == 2
    assert fill.is_complete


def test_walk_book_sell_consumes_highest_first() -> None:
    fill = walk_book(_book(), 50.0, side="sell")
    assert fill.average_price == pytest.approx(0.60)
    assert fill.levels_consumed == 1


def test_walk_book_reports_shortfall() -> None:
    fill = walk_book((PriceLevel(0.5, 10.0),), 100.0)
    assert fill.shares == pytest.approx(10.0)
    assert fill.unfilled == pytest.approx(90.0)
    assert not fill.is_complete


def test_walk_book_rejects_bad_size() -> None:
    with pytest.raises(ValueError):
        walk_book(_book(), 0.0)


def test_depth_effective_price_none_when_depth_is_short() -> None:
    model = CostModel(fee_bps=100.0)
    assert model.depth_effective_price(_book(), 50.0) is not None
    assert model.depth_effective_price((PriceLevel(0.5, 10.0),), 100.0) is None


def test_depth_net_edge_worsens_with_size() -> None:
    model = CostModel(fee_bps=100.0)
    small = model.depth_net_edge(fair_probability=0.6, levels=_book(), size=50.0)
    large = model.depth_net_edge(fair_probability=0.6, levels=_book(), size=200.0)
    assert small is not None and large is not None
    assert small > large
