"""Tests for the execution-cost model."""

from __future__ import annotations

import pytest

from poly_alpha.backtesting.costs import CostModel


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
    assert model.effective_price(0.5, "BUY") == pytest.approx(
        model.effective_price(0.5, "buy")
    )
    assert model.effective_price(0.5, "Sell") == pytest.approx(
        model.effective_price(0.5, "sell")
    )


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
