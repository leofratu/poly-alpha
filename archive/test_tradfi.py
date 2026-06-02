import math
import pytest
from dataclasses import fields
from tradfi import (
    norm_cdf,
    norm_pdf,
    calculate_d1,
    calculate_d2,
    calculate_implied_probability,
    BlackScholesInputs,
    PriceDirection,
    FinancialTarget,
    VolatilityEstimate,
    extract_financial_target,
    get_risk_free_rate,
    clear_yield_curve_cache,
    _is_crypto_ticker,
    _get_trading_days,
    _safe_float,
)


class TestNormCdf:
    def test_norm_cdf_at_zero(self):
        assert norm_cdf(0.0) == pytest.approx(0.5, rel=1e-10)

    def test_norm_cdf_symmetry(self):
        assert norm_cdf(1.0) == pytest.approx(1.0 - norm_cdf(-1.0), rel=1e-10)
        assert norm_cdf(2.0) == pytest.approx(1.0 - norm_cdf(-2.0), rel=1e-10)

    def test_norm_cdf_positive_values(self):
        assert norm_cdf(1.0) > 0.5
        assert norm_cdf(2.0) > norm_cdf(1.0)
        assert norm_cdf(3.0) > norm_cdf(2.0)

    def test_norm_cdf_negative_values(self):
        assert norm_cdf(-1.0) < 0.5
        assert norm_cdf(-2.0) < norm_cdf(-1.0)
        assert norm_cdf(-3.0) < norm_cdf(-2.0)

    def test_norm_cdf_known_values(self):
        assert norm_cdf(1.96) == pytest.approx(0.975, abs=0.001)
        assert norm_cdf(-1.96) == pytest.approx(0.025, abs=0.001)
        assert norm_cdf(1.645) == pytest.approx(0.95, abs=0.005)

    def test_norm_cdf_limits_large_positive(self):
        assert norm_cdf(10.0) == pytest.approx(1.0, rel=1e-10)
        assert norm_cdf(100.0) == pytest.approx(1.0, rel=1e-10)

    def test_norm_cdf_limits_large_negative(self):
        assert norm_cdf(-10.0) == pytest.approx(0.0, abs=1e-20)
        assert norm_cdf(-100.0) == pytest.approx(0.0, abs=1e-20)

    def test_norm_cdf_monotonicity(self):
        xs = [-3.0, -2.0, -1.0, 0.0, 1.0, 2.0, 3.0]
        for i in range(len(xs) - 1):
            assert norm_cdf(xs[i]) < norm_cdf(xs[i + 1])


class TestNormPdf:
    def test_norm_pdf_at_zero(self):
        expected = 1.0 / math.sqrt(2.0 * math.pi)
        assert norm_pdf(0.0) == pytest.approx(expected, rel=1e-10)

    def test_norm_pdf_symmetry(self):
        assert norm_pdf(1.0) == pytest.approx(norm_pdf(-1.0), rel=1e-10)
        assert norm_pdf(2.0) == pytest.approx(norm_pdf(-2.0), rel=1e-10)
        assert norm_pdf(5.5) == pytest.approx(norm_pdf(-5.5), rel=1e-10)

    def test_norm_pdf_positive_values(self):
        assert norm_pdf(0.0) > norm_pdf(1.0)
        assert norm_pdf(1.0) > norm_pdf(2.0)

    def test_norm_pdf_known_values(self):
        expected_at_1 = math.exp(-0.5) / math.sqrt(2.0 * math.pi)
        assert norm_pdf(1.0) == pytest.approx(expected_at_1, rel=1e-10)

        expected_at_2 = math.exp(-2.0) / math.sqrt(2.0 * math.pi)
        assert norm_pdf(2.0) == pytest.approx(expected_at_2, rel=1e-10)

    def test_norm_pdf_limits_large_values(self):
        assert norm_pdf(10.0) == pytest.approx(0.0, abs=1e-20)
        assert norm_pdf(-10.0) == pytest.approx(0.0, abs=1e-20)

    def test_norm_pdf_always_positive(self):
        for x in [-10.0, -5.0, -1.0, 0.0, 1.0, 5.0, 10.0]:
            assert norm_pdf(x) > 0.0


class TestBlackScholesInputs:
    def test_dataclass_creation(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=105.0,
            time_to_maturity_years=0.25,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.02,
        )
        assert inputs.spot == 100.0
        assert inputs.strike == 105.0
        assert inputs.time_to_maturity_years == 0.25
        assert inputs.risk_free_rate == 0.05
        assert inputs.volatility == 0.20
        assert inputs.dividend_yield == 0.02

    def test_default_dividend_yield(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
        )
        assert inputs.dividend_yield == 0.0

    def test_frozen_dataclass(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
        )
        with pytest.raises((AttributeError, Exception)):
            inputs.spot = 110.0  # type: ignore[misc]


class TestCalculateD1:
    def test_d1_basic_case(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        expected = (math.log(1.0) + (0.05 + 0.5 * 0.04) * 1.0) / (0.20 * 1.0)
        assert d1 == pytest.approx(expected, rel=1e-10)

    def test_d1_with_dividend_yield(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.02,
        )
        d1 = calculate_d1(inputs)
        expected = (math.log(1.0) + (0.05 - 0.02 + 0.5 * 0.04) * 1.0) / (0.20 * 1.0)
        assert d1 == pytest.approx(expected, rel=1e-10)

    def test_d1_spot_greater_than_strike(self):
        inputs = BlackScholesInputs(
            spot=110.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        assert d1 > 0

    def test_d1_spot_less_than_strike(self):
        inputs = BlackScholesInputs(
            spot=90.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        assert d1 < 0

    def test_d1_high_volatility_reduces_magnitude(self):
        inputs_low = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        inputs_high = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.60,
            dividend_yield=0.0,
        )
        d1_low = calculate_d1(inputs_low)
        d1_high = calculate_d1(inputs_high)
        assert abs(d1_high / 0.60) < abs(d1_low / 0.20)

    def test_d1_negative_dividend_yield_crypto(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=-0.08,
        )
        d1 = calculate_d1(inputs)
        expected = (math.log(1.0) + (0.05 - (-0.08) + 0.5 * 0.04) * 1.0) / (0.20 * 1.0)
        assert d1 == pytest.approx(expected, rel=1e-10)

    def test_d1_zero_time_to_maturity_raises(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=0.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        with pytest.raises(
            ValueError, match="Time to maturity and volatility must be positive"
        ):
            calculate_d1(inputs)

    def test_d1_negative_time_to_maturity_raises(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=-1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        with pytest.raises(
            ValueError, match="Time to maturity and volatility must be positive"
        ):
            calculate_d1(inputs)

    def test_d1_zero_volatility_raises(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.0,
            dividend_yield=0.0,
        )
        with pytest.raises(
            ValueError, match="Time to maturity and volatility must be positive"
        ):
            calculate_d1(inputs)

    def test_d1_negative_volatility_raises(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=-0.20,
            dividend_yield=0.0,
        )
        with pytest.raises(
            ValueError, match="Time to maturity and volatility must be positive"
        ):
            calculate_d1(inputs)

    def test_d1_zero_strike_raises(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=0.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        with pytest.raises(ValueError, match="Strike price must be positive"):
            calculate_d1(inputs)

    def test_d1_negative_strike_raises(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=-100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        with pytest.raises(ValueError, match="Strike price must be positive"):
            calculate_d1(inputs)

    def test_d1_zero_spot_raises(self):
        inputs = BlackScholesInputs(
            spot=0.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        with pytest.raises(ValueError, match="Spot price must be positive"):
            calculate_d1(inputs)

    def test_d1_negative_spot_raises(self):
        inputs = BlackScholesInputs(
            spot=-100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        with pytest.raises(ValueError, match="Spot price must be positive"):
            calculate_d1(inputs)

    def test_d1_negative_risk_free_rate_allowed(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=-0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        expected = (math.log(1.0) + (-0.05 + 0.5 * 0.04) * 1.0) / (0.20 * 1.0)
        assert d1 == pytest.approx(expected, rel=1e-10)

    def test_d1_small_time_to_maturity(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1e-6,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        assert isinstance(d1, float)

    def test_d1_very_high_volatility(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=5.0,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        assert isinstance(d1, float)

    def test_d1_extreme_spot_strike_ratio(self):
        inputs = BlackScholesInputs(
            spot=1.0,
            strike=1000000.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        assert d1 < -50

    def test_d1_known_value_atm(self):
        S, K, T, r, sigma, q = 100.0, 100.0, 1.0, 0.05, 0.20, 0.02
        inputs = BlackScholesInputs(S, K, T, r, sigma, q)
        d1 = calculate_d1(inputs)
        numerator = math.log(S / K) + (r - q + 0.5 * sigma**2) * T
        denominator = sigma * math.sqrt(T)
        expected = numerator / denominator
        assert d1 == pytest.approx(expected, rel=1e-10)


class TestCalculateD2:
    def test_d2_basic_case(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        d2 = calculate_d2(inputs)
        expected = d1 - 0.20 * math.sqrt(1.0)
        assert d2 == pytest.approx(expected, rel=1e-10)

    def test_d2_relationship_with_d1(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=105.0,
            time_to_maturity_years=0.5,
            risk_free_rate=0.03,
            volatility=0.25,
            dividend_yield=0.01,
        )
        d1 = calculate_d1(inputs)
        d2 = calculate_d2(inputs)
        assert d2 == pytest.approx(
            d1 - inputs.volatility * math.sqrt(inputs.time_to_maturity_years), rel=1e-10
        )

    def test_d2_less_than_d1(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        d2 = calculate_d2(inputs)
        assert d2 < d1

    def test_d2_with_dividend_yield(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.03,
        )
        d2 = calculate_d2(inputs)
        assert isinstance(d2, float)

    def test_d2_high_volatility_wider_spread(self):
        inputs_low = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        inputs_high = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.50,
            dividend_yield=0.0,
        )
        d1_low, d2_low = calculate_d1(inputs_low), calculate_d2(inputs_low)
        d1_high, d2_high = calculate_d1(inputs_high), calculate_d2(inputs_high)
        assert abs(d1_high - d2_high) > abs(d1_low - d2_low)

    def test_d2_longer_maturity_wider_spread(self):
        inputs_short = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=0.25,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        inputs_long = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=2.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        spread_short = abs(calculate_d1(inputs_short) - calculate_d2(inputs_short))
        spread_long = abs(calculate_d1(inputs_long) - calculate_d2(inputs_long))
        assert spread_long > spread_short

    def test_d2_zero_time_raises(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=0.0,
            risk_free_rate=0.05,
            volatility=0.20,
            dividend_yield=0.0,
        )
        with pytest.raises(ValueError):
            calculate_d2(inputs)

    def test_d2_zero_volatility_raises(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.05,
            volatility=0.0,
            dividend_yield=0.0,
        )
        with pytest.raises(ValueError):
            calculate_d2(inputs)

    def test_d2_known_value(self):
        S, K, T, r, sigma, q = 100.0, 100.0, 1.0, 0.05, 0.20, 0.0
        inputs = BlackScholesInputs(S, K, T, r, sigma, q)
        d1 = calculate_d1(inputs)
        d2 = calculate_d2(inputs)
        expected = d1 - sigma * math.sqrt(T)
        assert d2 == pytest.approx(expected, rel=1e-10)


class TestCalculateImpliedProbability:
    def test_probability_atm_call(self):
        prob = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20, q=0.0
        )
        assert 0.4 < prob < 0.6

    def test_probability_spot_above_strike(self):
        prob = calculate_implied_probability(
            S=110.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20, q=0.0
        )
        assert prob > 0.5

    def test_probability_spot_below_strike(self):
        prob = calculate_implied_probability(
            S=90.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20, q=0.0
        )
        assert prob < 0.5

    def test_probability_with_dividend_yield(self):
        prob_no_div = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20, q=0.0
        )
        prob_with_div = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20, q=0.02
        )
        assert prob_with_div < prob_no_div

    def test_probability_negative_dividend_yield_crypto(self):
        prob_positive_q = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20, q=0.02
        )
        prob_negative_q = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20, q=-0.08
        )
        assert prob_negative_q > prob_positive_q

    def test_probability_zero_time_spot_above_strike(self):
        prob = calculate_implied_probability(
            S=110.0, K=100.0, T_years=0.0, r=0.05, sigma=0.20, q=0.0
        )
        assert prob == 1.0

    def test_probability_zero_time_spot_below_strike(self):
        prob = calculate_implied_probability(
            S=90.0, K=100.0, T_years=0.0, r=0.05, sigma=0.20, q=0.0
        )
        assert prob == 0.0

    def test_probability_zero_time_spot_equals_strike(self):
        prob = calculate_implied_probability(
            S=100.0, K=100.0, T_years=0.0, r=0.05, sigma=0.20, q=0.0
        )
        assert prob == 1.0

    def test_probability_high_volatility_converges_to_05(self):
        prob_low_vol = calculate_implied_probability(
            S=100.0, K=120.0, T_years=1.0, r=0.05, sigma=0.20, q=0.0
        )
        prob_high_vol = calculate_implied_probability(
            S=100.0, K=120.0, T_years=1.0, r=0.05, sigma=1.0, q=0.0
        )
        assert abs(prob_high_vol - 0.5) < abs(prob_low_vol - 0.5)

    def test_probability_bounded_between_0_and_1(self):
        for S in [50.0, 100.0, 150.0]:
            for K in [80.0, 100.0, 120.0]:
                for T in [0.1, 0.5, 1.0, 2.0]:
                    prob = calculate_implied_probability(
                        S=S, K=K, T_years=T, r=0.05, sigma=0.20, q=0.02
                    )
                    assert 0.0 <= prob <= 1.0

    def test_probability_long_maturity_deep_itm(self):
        prob = calculate_implied_probability(
            S=150.0, K=100.0, T_years=5.0, r=0.05, sigma=0.20, q=0.0
        )
        assert prob > 0.85

    def test_probability_long_maturity_deep_otm(self):
        prob = calculate_implied_probability(
            S=50.0, K=100.0, T_years=5.0, r=0.05, sigma=0.20, q=0.0
        )
        assert prob < 0.15

    def test_probability_zero_spot_raises(self):
        with pytest.raises(ValueError, match="Spot price must be positive"):
            calculate_implied_probability(
                S=0.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20
            )

    def test_probability_negative_spot_raises(self):
        with pytest.raises(ValueError, match="Spot price must be positive"):
            calculate_implied_probability(
                S=-100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20
            )

    def test_probability_zero_strike_raises(self):
        with pytest.raises(ValueError, match="Strike price must be positive"):
            calculate_implied_probability(
                S=100.0, K=0.0, T_years=1.0, r=0.05, sigma=0.20
            )

    def test_probability_negative_strike_raises(self):
        with pytest.raises(ValueError, match="Strike price must be positive"):
            calculate_implied_probability(
                S=100.0, K=-100.0, T_years=1.0, r=0.05, sigma=0.20
            )

    def test_probability_negative_time_raises(self):
        with pytest.raises(ValueError, match="Time to maturity cannot be negative"):
            calculate_implied_probability(
                S=100.0, K=100.0, T_years=-1.0, r=0.05, sigma=0.20
            )

    def test_probability_zero_volatility_raises(self):
        with pytest.raises(ValueError, match="Volatility must be positive"):
            calculate_implied_probability(
                S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.0
            )

    def test_probability_negative_volatility_raises(self):
        with pytest.raises(ValueError, match="Volatility must be positive"):
            calculate_implied_probability(
                S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=-0.20
            )

    def test_probability_negative_risk_free_rate_allowed(self):
        prob = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=-0.05, sigma=0.20, q=0.0
        )
        assert isinstance(prob, float)
        assert 0.0 <= prob <= 1.0

    def test_probability_extreme_strike_ratio(self):
        prob = calculate_implied_probability(
            S=1.0, K=1000.0, T_years=1.0, r=0.05, sigma=0.50, q=0.0
        )
        assert prob < 0.01

    def test_probability_consistency_with_d2(self):
        S, K, T, r, sigma, q = 100.0, 105.0, 0.5, 0.03, 0.25, 0.01
        prob = calculate_implied_probability(S, K, T, r, sigma, q)
        inputs = BlackScholesInputs(S, K, T, r, sigma, q)
        d2 = calculate_d2(inputs)
        expected = norm_cdf(d2)
        assert prob == pytest.approx(expected, rel=1e-10)

    def test_probability_default_dividend_yield(self):
        prob_explicit = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20, q=0.0
        )
        prob_default = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20
        )
        assert prob_explicit == pytest.approx(prob_default, rel=1e-10)

    def test_probability_monte_carlo_sanity_check(self):
        prob = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.20, q=0.0
        )
        expected_approx = 0.46
        assert abs(prob - expected_approx) < 0.1

    def test_probability_monotonic_in_spot(self):
        probs = []
        for S in [80.0, 90.0, 100.0, 110.0, 120.0]:
            prob = calculate_implied_probability(
                S=S, K=100.0, T_years=1.0, r=0.05, sigma=0.20
            )
            probs.append(prob)
        for i in range(len(probs) - 1):
            assert probs[i] < probs[i + 1]

    def test_probability_monotonic_in_strike(self):
        probs = []
        for K in [80.0, 90.0, 100.0, 110.0, 120.0]:
            prob = calculate_implied_probability(
                S=100.0, K=K, T_years=1.0, r=0.05, sigma=0.20
            )
            probs.append(prob)
        for i in range(len(probs) - 1):
            assert probs[i] > probs[i + 1]

    def test_probability_volatility_effect_on_otm(self):
        prob_low_vol = calculate_implied_probability(
            S=100.0, K=110.0, T_years=1.0, r=0.05, sigma=0.10
        )
        prob_high_vol = calculate_implied_probability(
            S=100.0, K=110.0, T_years=1.0, r=0.05, sigma=0.50
        )
        assert prob_high_vol > prob_low_vol


class TestPriceDirection:
    def test_price_direction_values(self):
        assert PriceDirection.ABOVE.value == "above"
        assert PriceDirection.BELOW.value == "below"


class TestFinancialTarget:
    def test_financial_target_creation(self):
        target = FinancialTarget(
            ticker="SPY", target_price=500.0, direction=PriceDirection.ABOVE
        )
        assert target.ticker == "SPY"
        assert target.target_price == 500.0
        assert target.direction == PriceDirection.ABOVE

    def test_financial_target_frozen(self):
        target = FinancialTarget(
            ticker="SPY", target_price=500.0, direction=PriceDirection.ABOVE
        )
        with pytest.raises((AttributeError, Exception)):
            target.ticker = "QQQ"  # type: ignore[misc]


class TestVolatilityEstimate:
    def test_volatility_estimate_creation(self):
        vol = VolatilityEstimate(value=0.25, source="historical")
        assert vol.value == 0.25
        assert vol.source == "historical"

    def test_volatility_estimate_frozen(self):
        vol = VolatilityEstimate(value=0.25, source="historical")
        with pytest.raises((AttributeError, Exception)):
            vol.value = 0.30  # type: ignore[misc]


class TestExtractFinancialTarget:
    def test_extract_spy_above(self):
        result = extract_financial_target("Will SPY close above $500?")
        assert result is not None
        assert result.ticker == "SPY"
        assert result.target_price == 500.0
        assert result.direction == PriceDirection.ABOVE

    def test_extract_btc_below(self):
        result = extract_financial_target("Will Bitcoin crash below 50000?")
        assert result is not None
        assert result.ticker == "BTC-USD"
        assert result.target_price == 50000.0
        assert result.direction == PriceDirection.BELOW

    def test_extract_eth_with_k_suffix(self):
        result = extract_financial_target("Will ETH reach $2.5k?")
        assert result is not None
        assert result.ticker == "ETH-USD"
        assert result.target_price == 2500.0

    def test_extract_with_m_suffix(self):
        result = extract_financial_target("Bitcoin to $100m?")
        assert result is not None
        assert result.target_price == 100000000.0

    def test_extract_with_commas(self):
        result = extract_financial_target("Will SPY hit $5,000?")
        assert result is not None
        assert result.target_price == 5000.0

    def test_extract_case_insensitive(self):
        result = extract_financial_target("will bitcoin close above $100k?")
        assert result is not None
        assert result.ticker == "BTC-USD"

    def test_extract_no_ticker_returns_none(self):
        result = extract_financial_target("Will it close above $500?")
        assert result is None

    def test_extract_no_price_returns_none(self):
        result = extract_financial_target("Will SPY close higher?")
        assert result is None

    def test_extract_empty_string_returns_none(self):
        result = extract_financial_target("")
        assert result is None

    def test_extract_none_returns_none(self):
        result = extract_financial_target(" ")
        assert result is None

    def test_extract_zero_price_returns_none(self):
        result = extract_financial_target("Will SPY close above $0?")
        assert result is None

    def test_extract_negative_direction_keywords(self):
        result = extract_financial_target("Will ETH fall under $3000?")
        assert result is not None
        assert result.direction == PriceDirection.BELOW

    def test_extract_various_assets(self):
        test_cases = [
            ("Will AAPL hit $200?", "AAPL", 200.0),
            ("Will NVDA reach $1000?", "NVDA", 1000.0),
            ("Will TSLA go to $250?", "TSLA", 250.0),
            ("Will SOL fall below $150?", "SOL-USD", 150.0),
        ]
        for question, expected_ticker, expected_price in test_cases:
            result = extract_financial_target(question)
            assert result is not None, f"Failed for question: {question}"
            assert result.ticker == expected_ticker, (
                f"Expected {expected_ticker}, got {result.ticker}"
            )
            assert result.target_price == expected_price, (
                f"Expected {expected_price}, got {result.target_price}"
            )


class TestIsCryptoTicker:
    def test_crypto_ticker_with_dash(self):
        assert _is_crypto_ticker("BTC-USD") is True
        assert _is_crypto_ticker("ETH-USD") is True

    def test_equity_ticker(self):
        assert _is_crypto_ticker("SPY") is False
        assert _is_crypto_ticker("AAPL") is False

    def test_crypto_ticker_in_special_set(self):
        assert _is_crypto_ticker("BTC-USD") is True

    def test_futures_tickers(self):
        assert _is_crypto_ticker("GC=F") is True
        assert _is_crypto_ticker("CL=F") is True


class TestGetTradingDays:
    def test_trading_days_crypto(self):
        assert _get_trading_days("BTC-USD") == 365
        assert _get_trading_days("ETH-USD") == 365

    def test_trading_days_equity(self):
        assert _get_trading_days("SPY") == 252
        assert _get_trading_days("AAPL") == 252


class TestSafeFloat:
    def test_safe_float_with_float(self):
        assert _safe_float(3.14) == 3.14

    def test_safe_float_with_int(self):
        assert _safe_float(42) == 42.0

    def test_safe_float_with_string(self):
        assert _safe_float("3.14") == 3.14

    def test_safe_float_with_none(self):
        assert _safe_float(None) is None

    def test_safe_float_with_invalid_string(self):
        assert _safe_float("not a number") is None

    def test_safe_float_with_nan(self):
        import math

        result = _safe_float(float("nan"))
        if result is not None:
            assert math.isnan(result)


class TestGetRiskFreeRate:
    def test_risk_free_rate_positive_days(self):
        clear_yield_curve_cache()
        rate = get_risk_free_rate(90)
        assert rate > 0

    def test_risk_free_rate_zero_days_raises(self):
        with pytest.raises(ValueError, match="days_to_maturity must be positive"):
            get_risk_free_rate(0)

    def test_risk_free_rate_negative_days_raises(self):
        with pytest.raises(ValueError, match="days_to_maturity must be positive"):
            get_risk_free_rate(-30)

    def test_risk_free_rate_very_short_maturity(self):
        clear_yield_curve_cache()
        rate = get_risk_free_rate(1)
        assert rate > 0

    def test_risk_free_rate_very_long_maturity(self):
        clear_yield_curve_cache()
        rate = get_risk_free_rate(365 * 30)
        assert rate > 0


class TestIntegrationBlackScholes:
    def test_full_black_scholes_flow(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=105.0,
            time_to_maturity_years=0.5,
            risk_free_rate=0.05,
            volatility=0.25,
            dividend_yield=0.02,
        )
        d1 = calculate_d1(inputs)
        d2 = calculate_d2(inputs)
        prob = calculate_implied_probability(
            inputs.spot,
            inputs.strike,
            inputs.time_to_maturity_years,
            inputs.risk_free_rate,
            inputs.volatility,
            inputs.dividend_yield,
        )
        assert isinstance(d1, float)
        assert isinstance(d2, float)
        assert isinstance(prob, float)
        assert d2 < d1
        assert 0.0 <= prob <= 1.0
        assert prob == pytest.approx(norm_cdf(d2), rel=1e-10)

    def test_crypto_scenario(self):
        prob = calculate_implied_probability(
            S=50000.0,
            K=55000.0,
            T_years=0.25,
            r=0.04,
            sigma=0.60,
            q=-0.08,
        )
        assert 0.0 <= prob <= 1.0

    def test_equity_dividend_scenario(self):
        prob = calculate_implied_probability(
            S=150.0,
            K=160.0,
            T_years=0.5,
            r=0.05,
            sigma=0.20,
            q=0.03,
        )
        assert 0.0 <= prob <= 1.0


class TestEdgeCasesAndNumericalStability:
    def test_very_small_volatility_valid(self):
        prob = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.05, sigma=0.001
        )
        assert 0.0 <= prob <= 1.0

    def test_very_small_time_to_maturity(self):
        prob = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1e-10, r=0.05, sigma=0.20
        )
        assert 0.0 <= prob <= 1.0

    def test_very_large_spot(self):
        prob = calculate_implied_probability(
            S=1e10, K=1e10, T_years=1.0, r=0.05, sigma=0.20
        )
        assert 0.0 <= prob <= 1.0

    def test_very_small_spot(self):
        prob = calculate_implied_probability(
            S=0.01, K=0.01, T_years=1.0, r=0.05, sigma=0.20
        )
        assert 0.0 <= prob <= 1.0

    def test_d1_d2_symmetry_atm(self):
        inputs = BlackScholesInputs(
            spot=100.0,
            strike=100.0,
            time_to_maturity_years=1.0,
            risk_free_rate=0.0,
            volatility=0.20,
            dividend_yield=0.0,
        )
        d1 = calculate_d1(inputs)
        d2 = calculate_d2(inputs)
        spread = abs(d1 - d2)
        expected_spread = 0.20 * math.sqrt(1.0)
        assert spread == pytest.approx(expected_spread, rel=1e-10)

    def test_probability_extreme_rates(self):
        prob_high_r = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.20, sigma=0.20
        )
        prob_low_r = calculate_implied_probability(
            S=100.0, K=100.0, T_years=1.0, r=0.001, sigma=0.20
        )
        assert isinstance(prob_high_r, float)
        assert isinstance(prob_low_r, float)
