"""TradFi implied probability via Black-Scholes, yield curve, and volatility estimation."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any, Final

import yfinance as yf

_YIELD_CURVE_CACHE: dict[int, float] = {}

FALLBACK_YIELDS: Final[dict[int, float]] = {
    90: 4.5,
    5 * 365: 4.0,
    10 * 365: 4.2,
}

TICKER_DAYS: Final[dict[str, int]] = {
    "^IRX": 90,
    "^FVX": 5 * 365,
    "^TNX": 10 * 365,
}

TRADING_DAYS_EQUITY: Final[int] = 252
TRADING_DAYS_CRYPTO: Final[int] = 365
MIN_VOLATILITY: Final[float] = 0.01
DEFAULT_VOLATILITY: Final[float] = 0.30
MIN_DATA_POINTS: Final[int] = 5

ASSET_MAPPING: Final[dict[str, str]] = {
    "BTC": "BTC-USD",
    "BITCOIN": "BTC-USD",
    "ETH": "ETH-USD",
    "ETHEREUM": "ETH-USD",
    "SOL": "SOL-USD",
    "SOLANA": "SOL-USD",
    "XRP": "XRP-USD",
    "RIPPLE": "XRP-USD",
    "ADA": "ADA-USD",
    "CARDANO": "ADA-USD",
    "AVAX": "AVAX-USD",
    "AVALANCHE": "AVAX-USD",
    "DOGE": "DOGE-USD",
    "DOGECOIN": "DOGE-USD",
    "DOT": "DOT-USD",
    "POLKADOT": "DOT-USD",
    "MATIC": "MATIC-USD",
    "POLYGON": "MATIC-USD",
    "LINK": "LINK-USD",
    "CHAINLINK": "LINK-USD",
    "UNI": "UNI7083-USD",
    "UNISWAP": "UNI7083-USD",
    "LTC": "LTC-USD",
    "LITECOIN": "LTC-USD",
    "ALGO": "ALGO-USD",
    "ALGORAND": "ALGO-USD",
    "BCH": "BCH-USD",
    "BITCOIN CASH": "BCH-USD",
    "XLM": "XLM-USD",
    "STELLAR": "XLM-USD",
    "VET": "VET-USD",
    "VECHAIN": "VET-USD",
    "ICP": "ICP-USD",
    "INTERNET COMPUTER": "ICP-USD",
    "FIL": "FIL-USD",
    "FILECOIN": "FIL-USD",
    "THETA": "THETA-USD",
    "TRX": "TRX-USD",
    "TRON": "TRX-USD",
    "ATOM": "ATOM-USD",
    "COSMOS": "ATOM-USD",
    "SPY": "SPY",
    "S&P 500": "^GSPC",
    "S&P": "^GSPC",
    "QQQ": "QQQ",
    "NASDAQ": "^IXIC",
    "DIA": "DIA",
    "DOW": "^DJI",
    "DOW JONES": "^DJI",
    "IWM": "IWM",
    "RUSSELL": "^RUT",
    "AAPL": "AAPL",
    "APPLE": "AAPL",
    "MSFT": "MSFT",
    "MICROSOFT": "MSFT",
    "GOOGL": "GOOGL",
    "GOOG": "GOOG",
    "GOOGLE": "GOOGL",
    "AMZN": "AMZN",
    "AMAZON": "AMZN",
    "NVDA": "NVDA",
    "NVIDIA": "NVDA",
    "TSLA": "TSLA",
    "TESLA": "TSLA",
    "META": "META",
    "FACEBOOK": "META",
    "NFLX": "NFLX",
    "NETFLIX": "NFLX",
    "COIN": "COIN",
    "COINBASE": "COIN",
    "MSTR": "MSTR",
    "MICROSTRATEGY": "MSTR",
    "JPM": "JPM",
    "JPMORGAN": "JPM",
    "V": "V",
    "VISA": "V",
    "MA": "MA",
    "MASTERCARD": "MA",
    "WMT": "WMT",
    "WALMART": "WMT",
    "DIS": "DIS",
    "DISNEY": "DIS",
    "AMD": "AMD",
    "INTC": "INTC",
    "INTEL": "INTC",
    "GLD": "GLD",
    "GOLD": "GC=F",
    "SLV": "SLV",
    "SILVER": "SI=F",
    "USO": "USO",
    "OIL": "CL=F",
    "CRUDE": "CL=F",
    "EUR/USD": "EURUSD=X",
    "EURUSD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USD/JPY": "JPY=X",
    "USDJPY": "JPY=X",
}

_ESCAPED_KEYS = [re.escape(k) for k in sorted(ASSET_MAPPING.keys(), key=len, reverse=True)]
ASSET_PATTERN: Final[str] = r"\b(" + "|".join(_ESCAPED_KEYS) + r")\b"

_PRICE_PATTERN: Final[str] = (
    r"(?<!\w)(above|below|reaches|hit|hits|reach|to|under|over|at least|>|<|=)"
    r"\s*\$?\s*(\d+(?:,\d{3})*(?:\.\d+)?)\s*"
    r"(k|m|b|thousand|million|billion|trillion)?\b"
)
_ABOVE_KEYWORDS: Final[str] = r"\b(above|over|higher|greater|exceed|surpass|reach|hit)\b"
_BELOW_KEYWORDS: Final[str] = (
    r"\b(below|under|lower|less|crash|down|drop|dip|fall|decline|plunge|tumble"
    r"|sink|slide|plummet|retreat|decrease|slump)(?:s|es|d|ed|ing|ped|ping)?\b"
)
_DIRECTION_WINDOW: Final[int] = 40


class PriceDirection(Enum):
    ABOVE = "above"
    BELOW = "below"


@dataclass(frozen=True, slots=True)
class FinancialTarget:
    ticker: str
    target_price: float
    direction: PriceDirection


@dataclass(frozen=True, slots=True)
class VolatilityEstimate:
    value: float
    source: str


@dataclass(frozen=True, slots=True)
class BlackScholesInputs:
    spot: float
    strike: float
    time_to_maturity_years: float
    risk_free_rate: float
    volatility: float
    dividend_yield: float = 0.0


def _is_crypto_ticker(ticker: str) -> bool:
    return "-" in ticker or ticker in {"BTC-USD", "ETH-USD", "GC=F", "SI=F", "CL=F"}


def _get_trading_days(ticker: str) -> int:
    return TRADING_DAYS_CRYPTO if _is_crypto_ticker(ticker) else TRADING_DAYS_EQUITY


def _safe_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def get_yield_curve() -> dict[int, float]:
    """Fetch US Treasury yield curve from yfinance (cached)."""
    if _YIELD_CURVE_CACHE:
        return _YIELD_CURVE_CACHE.copy()

    curve: dict[int, float] = {}
    for ticker, days in TICKER_DAYS.items():
        try:
            ticker_obj = yf.Ticker(ticker)
            price = _safe_float(ticker_obj.fast_info.last_price)
            if price is not None and price > 0:
                curve[days] = price
        except (ValueError, KeyError, AttributeError):
            continue

    if not curve:
        curve = FALLBACK_YIELDS.copy()

    _YIELD_CURVE_CACHE.update(curve)
    return _YIELD_CURVE_CACHE.copy()


def clear_yield_curve_cache() -> None:
    """Clear the cached yield curve data."""
    _YIELD_CURVE_CACHE.clear()


def get_risk_free_rate(days_to_maturity: int) -> float:
    """Interpolate risk-free rate from yield curve for given maturity."""
    if days_to_maturity <= 0:
        raise ValueError(f"days_to_maturity must be positive, got {days_to_maturity}")

    curve = get_yield_curve()
    if not curve:
        return FALLBACK_YIELDS.get(90, 4.5)

    points = sorted(curve.items())
    min_days, min_rate = points[0]
    max_days, max_rate = points[-1]

    if days_to_maturity <= min_days:
        return min_rate
    if days_to_maturity >= max_days:
        return max_rate

    for i in range(len(points) - 1):
        d1, y1 = points[i]
        d2, y2 = points[i + 1]
        if d1 <= days_to_maturity <= d2:
            if d2 == d1:
                return y1
            fraction = (days_to_maturity - d1) / (d2 - d1)
            return y1 + fraction * (y2 - y1)

    return max_rate


def norm_cdf(x: float) -> float:
    """Standard normal cumulative distribution function."""
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def norm_pdf(x: float) -> float:
    """Standard normal probability density function."""
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def calculate_d1(inputs: BlackScholesInputs) -> float:
    """Calculate Black-Scholes d1 parameter."""
    S, K, T, r, sigma, q = (
        inputs.spot,
        inputs.strike,
        inputs.time_to_maturity_years,
        inputs.risk_free_rate,
        inputs.volatility,
        inputs.dividend_yield,
    )

    if T <= 0 or sigma <= 0:
        raise ValueError(f"T and sigma must be positive. Got T={T}, sigma={sigma}")
    if K <= 0:
        raise ValueError(f"Strike must be positive. Got K={K}")
    if S <= 0:
        raise ValueError(f"Spot must be positive. Got S={S}")

    return (math.log(S / K) + (r - q + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))


def calculate_d2(inputs: BlackScholesInputs) -> float:
    """Calculate Black-Scholes d2 parameter."""
    d1 = calculate_d1(inputs)
    return d1 - inputs.volatility * math.sqrt(inputs.time_to_maturity_years)


def calculate_implied_probability(
    S: float, K: float, T_years: float, r: float, sigma: float, q: float = 0.0
) -> float:
    """Calculate P(S > K at expiry) using Black-Scholes N(d2)."""
    if S <= 0:
        raise ValueError(f"Spot must be positive, got {S}")
    if K <= 0:
        raise ValueError(f"Strike must be positive, got {K}")
    if T_years < 0:
        raise ValueError(f"Time to maturity cannot be negative, got {T_years}")
    if sigma <= 0:
        raise ValueError(f"Volatility must be positive, got {sigma}")

    if T_years == 0:
        return 1.0 if S >= K else 0.0

    inputs = BlackScholesInputs(
        spot=S,
        strike=K,
        time_to_maturity_years=T_years,
        risk_free_rate=r,
        volatility=sigma,
        dividend_yield=q,
    )

    d2 = calculate_d2(inputs)
    return max(0.0, min(1.0, norm_cdf(d2)))


def extract_financial_target(question: str) -> FinancialTarget | None:
    """Parse a prediction market question to extract asset, target price, and direction."""
    if not question or not isinstance(question, str):
        return None

    ticker_match = re.search(ASSET_PATTERN, question, re.IGNORECASE)
    if not ticker_match:
        return None

    matched_key = ticker_match.group(1).upper()
    ticker = ASSET_MAPPING.get(matched_key)
    if not ticker:
        return None

    price_match = re.search(_PRICE_PATTERN, question, re.IGNORECASE)
    if not price_match:
        return None

    price_str = price_match.group(2).replace(",", "")
    try:
        price = float(price_str)
    except ValueError:
        return None

    unit = (price_match.group(3) or "").lower()
    multipliers = {
        "k": 1_000.0,
        "thousand": 1_000.0,
        "m": 1_000_000.0,
        "million": 1_000_000.0,
        "b": 1_000_000_000.0,
        "billion": 1_000_000_000.0,
        "trillion": 1_000_000_000_000.0,
    }
    price *= multipliers.get(unit, 1.0)

    if price <= 0:
        return None

    token = price_match.group(1).lower()
    if token in {"above", "over", ">"} or token == "at least":
        direction = PriceDirection.ABOVE
    elif token in {"below", "under", "<"}:
        direction = PriceDirection.BELOW
    else:
        clause = question[max(0, price_match.start() - _DIRECTION_WINDOW) : price_match.start()]
        if re.search(_BELOW_KEYWORDS, clause, re.IGNORECASE):
            direction = PriceDirection.BELOW
        elif re.search(_ABOVE_KEYWORDS, clause, re.IGNORECASE):
            direction = PriceDirection.ABOVE
        else:
            above_match = re.search(_ABOVE_KEYWORDS, question, re.IGNORECASE)
            below_match = re.search(_BELOW_KEYWORDS, question, re.IGNORECASE)
            direction = (
                PriceDirection.BELOW if below_match and not above_match else PriceDirection.ABOVE
            )
    return FinancialTarget(ticker=ticker, target_price=price, direction=direction)


def get_historical_volatility(ticker: str, days: int = 30) -> VolatilityEstimate | None:
    """Calculate annualized historical volatility from daily returns."""
    if days <= 0:
        raise ValueError(f"Days must be positive, got {days}")

    try:
        t = yf.Ticker(ticker)
        lookback_days = max(days * 2, 60)
        hist = t.history(period=f"{lookback_days}d")

        if hist.empty or len(hist) < MIN_DATA_POINTS:
            return None

        hist = hist.tail(days)
        if hist.empty:
            return None

        close_prices = hist["Close"]
        if close_prices.isnull().all():
            return None

        returns = close_prices.pct_change().dropna()
        if returns.empty or len(returns) < MIN_DATA_POINTS // 2:
            return None

        trading_days = _get_trading_days(ticker)
        daily_vol = float(returns.std())

        if daily_vol <= 0:
            return None

        annualized_vol = daily_vol * math.sqrt(trading_days)
        return VolatilityEstimate(value=annualized_vol, source="historical")
    except (ValueError, KeyError, AttributeError):
        return None


def get_tradfi_implied_probability(question: str, target_date: datetime) -> float | None:
    """Full pipeline: parse question -> fetch market data -> compute P(above/below strike)."""
    if not question or not isinstance(question, str):
        return None
    if not isinstance(target_date, datetime):
        return None
    if target_date.tzinfo is None:
        target_date = target_date.replace(tzinfo=UTC)

    parsed = extract_financial_target(question)
    if parsed is None:
        return None

    ticker = parsed.ticker
    target_price = parsed.target_price
    direction = parsed.direction

    try:
        t = yf.Ticker(ticker)
        current_price = _safe_float(t.fast_info.last_price)

        if current_price is None or current_price <= 0:
            hist = t.history(period="5d")
            if hist.empty:
                return None
            current_price = _safe_float(hist["Close"].iloc[-1])
            if current_price is None or current_price <= 0:
                return None

        vol_estimate = _get_options_implied_volatility(t, target_price, target_date)
        hist_vol = get_historical_volatility(ticker, days=30)

        if vol_estimate is None or vol_estimate.value < MIN_VOLATILITY:
            if hist_vol is not None and hist_vol.value >= MIN_VOLATILITY:
                vol_estimate = hist_vol
        else:
            # VRP blend: 70% IV / 30% HV strips the volatility risk premium
            if hist_vol is not None and hist_vol.value >= MIN_VOLATILITY:
                blended_vol = (0.7 * vol_estimate.value) + (0.3 * hist_vol.value)
                vol_estimate = VolatilityEstimate(value=blended_vol, source="vrp_blended")

        if vol_estimate is None or vol_estimate.value < MIN_VOLATILITY:
            vol_estimate = VolatilityEstimate(value=DEFAULT_VOLATILITY, source="default")

        now = datetime.now(UTC)
        days_to_maturity = max(1, (target_date - now).days)
        T_years = days_to_maturity / 365.25
        r = get_risk_free_rate(days_to_maturity) / 100.0

        q = _get_implied_dividend_yield(t, ticker)

        prob_above = calculate_implied_probability(
            S=current_price, K=target_price, T_years=T_years, r=r, sigma=vol_estimate.value, q=q
        )

        if direction == PriceDirection.BELOW:
            return max(0.0, 1.0 - prob_above)
        return prob_above

    except (ValueError, KeyError, AttributeError):
        return None


def _get_options_implied_volatility(
    ticker_obj: yf.Ticker,
    target_price: float,
    target_date: datetime,
) -> VolatilityEstimate | None:
    try:
        options = ticker_obj.options
    except (ValueError, AttributeError):
        return None

    if not options:
        return None

    best_exp: str | None = None
    min_diff = float("inf")

    for exp_str in options:
        try:
            exp_date = datetime.strptime(exp_str, "%Y-%m-%d").replace(tzinfo=UTC)
            diff = abs((exp_date - target_date).days)
            if diff < min_diff:
                min_diff = diff
                best_exp = exp_str
        except ValueError:
            continue

    if best_exp is None:
        best_exp = options[-1] if options else None
        if best_exp is None:
            return None

    try:
        chain = ticker_obj.option_chain(best_exp)
        calls = chain.calls

        if calls.empty:
            return None

        strikes = calls["strike"].values
        close_idx = int((abs(strikes - target_price)).argmin())
        closest_call = calls.iloc[close_idx]

        iv = _safe_float(closest_call["impliedVolatility"])
        if iv is None or iv < MIN_VOLATILITY:
            return None

        return VolatilityEstimate(value=iv, source="options")
    except (ValueError, KeyError, IndexError, AttributeError):
        return None


def _get_implied_dividend_yield(ticker_obj: yf.Ticker, ticker: str) -> float:
    # Crypto trades in contango (~8% annualized offshore perp funding)
    if _is_crypto_ticker(ticker):
        return -0.08

    try:
        info = ticker_obj.info
        if info and "dividendYield" in info and info["dividendYield"]:
            return float(info["dividendYield"])
    except (ValueError, KeyError, AttributeError):
        pass
    return 0.0
