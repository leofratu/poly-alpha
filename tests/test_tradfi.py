"""Deterministic tests for the TradFi Black-Scholes probability helpers (offline)."""

from __future__ import annotations

import math

import pytest

from poly_alpha.data.tradfi import calculate_implied_probability, norm_cdf, norm_pdf


def test_norm_cdf_and_pdf() -> None:
    assert norm_cdf(0.0) == pytest.approx(0.5)
    assert norm_cdf(10.0) == pytest.approx(1.0, abs=1e-9)
    assert norm_pdf(0.0) == pytest.approx(1.0 / math.sqrt(2.0 * math.pi))


def test_implied_probability_atm_matches_n_d2() -> None:
    # S=K and r=q=0 gives d2 = -0.5*sigma*sqrt(T) = -0.1.
    probability = calculate_implied_probability(100.0, 100.0, 1.0, 0.0, 0.2)
    assert probability == pytest.approx(norm_cdf(-0.1), abs=1e-12)
    assert probability < 0.5


def test_implied_probability_is_monotonic_in_moneyness() -> None:
    in_the_money = calculate_implied_probability(120.0, 100.0, 1.0, 0.0, 0.2)
    out_of_the_money = calculate_implied_probability(80.0, 100.0, 1.0, 0.0, 0.2)
    assert in_the_money > 0.5 > out_of_the_money


def test_dividend_yield_lowers_the_probability() -> None:
    without = calculate_implied_probability(100.0, 100.0, 1.0, 0.05, 0.2, q=0.0)
    with_dividend = calculate_implied_probability(100.0, 100.0, 1.0, 0.05, 0.2, q=0.05)
    assert with_dividend < without


def test_expired_contract_is_a_step_function() -> None:
    assert calculate_implied_probability(101.0, 100.0, 0.0, 0.05, 0.2) == 1.0
    assert calculate_implied_probability(99.0, 100.0, 0.0, 0.05, 0.2) == 0.0


@pytest.mark.parametrize(
    "args",
    [
        (-1.0, 100.0, 1.0, 0.05, 0.2),
        (100.0, -1.0, 1.0, 0.05, 0.2),
        (100.0, 100.0, -1.0, 0.05, 0.2),
        (100.0, 100.0, 1.0, 0.05, 0.0),
    ],
)
def test_implied_probability_rejects_bad_inputs(args: tuple[float, ...]) -> None:
    with pytest.raises(ValueError):
        calculate_implied_probability(*args)


def test_risk_free_rate_interpolates_and_clamps(monkeypatch: pytest.MonkeyPatch) -> None:
    from poly_alpha.data import tradfi

    monkeypatch.setattr(tradfi, "get_yield_curve", lambda: {30: 4.0, 90: 5.0})
    assert tradfi.get_risk_free_rate(10) == pytest.approx(4.0)
    assert tradfi.get_risk_free_rate(30) == pytest.approx(4.0)
    assert tradfi.get_risk_free_rate(60) == pytest.approx(4.5)
    assert tradfi.get_risk_free_rate(200) == pytest.approx(5.0)


def test_risk_free_rate_falls_back_without_a_curve(monkeypatch: pytest.MonkeyPatch) -> None:
    from poly_alpha.data import tradfi

    monkeypatch.setattr(tradfi, "get_yield_curve", lambda: {})
    assert tradfi.get_risk_free_rate(90) == pytest.approx(tradfi.FALLBACK_YIELDS[90])


def test_risk_free_rate_rejects_nonpositive_days(monkeypatch: pytest.MonkeyPatch) -> None:
    from poly_alpha.data import tradfi

    with pytest.raises(ValueError):
        tradfi.get_risk_free_rate(0)


def test_trading_days_classification() -> None:
    from poly_alpha.data import tradfi

    assert tradfi._is_crypto_ticker("BTC-USD") is True
    assert tradfi._is_crypto_ticker("GC=F") is True
    assert tradfi._is_crypto_ticker("SPY") is False
    assert tradfi._get_trading_days("BTC-USD") == tradfi.TRADING_DAYS_CRYPTO
    assert tradfi._get_trading_days("SPY") == tradfi.TRADING_DAYS_EQUITY


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, None), ("3.5", 3.5), (7, 7.0), ("nope", None), (object(), None)],
)
def test_safe_float(value: object, expected: float | None) -> None:
    from poly_alpha.data import tradfi

    assert tradfi._safe_float(value) == expected


def test_black_scholes_d2_is_d1_minus_sigma_root_t() -> None:
    from poly_alpha.data.tradfi import BlackScholesInputs, calculate_d1, calculate_d2

    inputs = BlackScholesInputs(
        spot=100.0,
        strike=100.0,
        time_to_maturity_years=1.0,
        risk_free_rate=0.05,
        volatility=0.2,
        dividend_yield=0.0,
    )
    assert calculate_d2(inputs) == pytest.approx(calculate_d1(inputs) - 0.2)


def test_extract_direction_uses_the_nearest_clause() -> None:
    from poly_alpha.data.tradfi import PriceDirection, extract_financial_target

    result = extract_financial_target("Will BTC fall to $80k after reaching above $100k?")
    assert result is not None
    assert result.direction is PriceDirection.BELOW
    assert result.target_price == 80_000.0


def test_extract_requires_a_real_separator_token() -> None:
    from poly_alpha.data.tradfi import extract_financial_target

    assert extract_financial_target("Will SPY cover 500?") is None


def test_extract_scales_units_and_matches_case_insensitively() -> None:
    from poly_alpha.data.tradfi import extract_financial_target

    million = extract_financial_target("Will Bitcoin Reach $1 million?")
    assert million is not None
    assert million.target_price == 1_000_000.0


def test_extract_direction_recognizes_bearish_verbs() -> None:
    from poly_alpha.data.tradfi import PriceDirection, extract_financial_target

    dip = extract_financial_target("Will Bitcoin dip to $80,000?")
    assert dip is not None
    assert dip.direction is PriceDirection.BELOW
    assert dip.target_price == 80_000.0
    plunge = extract_financial_target("Will Ethereum plunge to $1500?")
    assert plunge is not None
    assert plunge.direction is PriceDirection.BELOW
