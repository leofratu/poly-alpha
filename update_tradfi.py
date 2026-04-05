import re

content = """import math
import re
from datetime import datetime, timezone
from typing import Final, Tuple

import yfinance as yf

_YIELD_CURVE_CACHE: dict[int, float] = {}
FALLBACK_YIELDS: Final[dict[int, float]] = {90: 4.5, 5 * 365: 4.0, 10 * 365: 4.2}
TICKER_DAYS: Final[dict[str, int]] = {"^IRX": 90, "^FVX": 5 * 365, "^TNX": 10 * 365}

ASSET_MAPPING = {
    # Crypto
    "BTC": "BTC-USD", "BITCOIN": "BTC-USD",
    "ETH": "ETH-USD", "ETHEREUM": "ETH-USD",
    "SOL": "SOL-USD", "SOLANA": "SOL-USD",
    "XRP": "XRP-USD", "RIPPLE": "XRP-USD",
    "ADA": "ADA-USD", "CARDANO": "ADA-USD",
    "AVAX": "AVAX-USD", "AVALANCHE": "AVAX-USD",
    "DOGE": "DOGE-USD", "DOGECOIN": "DOGE-USD",
    "DOT": "DOT-USD", "POLKADOT": "DOT-USD",
    "MATIC": "MATIC-USD", "POLYGON": "MATIC-USD",
    "LINK": "LINK-USD", "CHAINLINK": "LINK-USD",
    "UNI": "UNI7083-USD", "UNISWAP": "UNI7083-USD",
    "LTC": "LTC-USD", "LITECOIN": "LTC-USD",
    "ALGO": "ALGO-USD", "ALGORAND": "ALGO-USD",
    "BCH": "BCH-USD", "BITCOIN CASH": "BCH-USD",
    "XLM": "XLM-USD", "STELLAR": "XLM-USD",
    "VET": "VET-USD", "VECHAIN": "VET-USD",
    "ICP": "ICP-USD", "INTERNET COMPUTER": "ICP-USD",
    "FIL": "FIL-USD", "FILECOIN": "FIL-USD",
    "THETA": "THETA-USD",
    "TRX": "TRX-USD", "TRON": "TRX-USD",
    "ATOM": "ATOM-USD", "COSMOS": "ATOM-USD",
    
    # Macro / Equities / ETFs
    "SPY": "SPY", "S&P 500": "^GSPC", "S&P": "^GSPC",
    "QQQ": "QQQ", "NASDAQ": "^IXIC",
    "DIA": "DIA", "DOW": "^DJI", "DOW JONES": "^DJI",
    "IWM": "IWM", "RUSSELL": "^RUT",
    "AAPL": "AAPL", "APPLE": "AAPL",
    "MSFT": "MSFT", "MICROSOFT": "MSFT",
    "GOOGL": "GOOGL", "GOOG": "GOOG", "GOOGLE": "GOOGL",
    "AMZN": "AMZN", "AMAZON": "AMZN",
    "NVDA": "NVDA", "NVIDIA": "NVDA",
    "TSLA": "TSLA", "TESLA": "TSLA",
    "META": "META", "FACEBOOK": "META",
    "NFLX": "NFLX", "NETFLIX": "NFLX",
    "COIN": "COIN", "COINBASE": "COIN",
    "MSTR": "MSTR", "MICROSTRATEGY": "MSTR",
    "JPM": "JPM", "JPMORGAN": "JPM",
    "V": "V", "VISA": "V",
    "MA": "MA", "MASTERCARD": "MA",
    "WMT": "WMT", "WALMART": "WMT",
    "DIS": "DIS", "DISNEY": "DIS",
    "AMD": "AMD",
    "INTC": "INTC", "INTEL": "INTC",
    
    # Commodities / Forex
    "GLD": "GLD", "GOLD": "GC=F",
    "SLV": "SLV", "SILVER": "SI=F",
    "USO": "USO", "OIL": "CL=F", "CRUDE": "CL=F",
    "EUR/USD": "EURUSD=X", "EURUSD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X", "GBPUSD": "GBPUSD=X",
    "USD/JPY": "JPY=X", "USDJPY": "JPY=X",
}

escaped_keys = [re.escape(k) for k in sorted(ASSET_MAPPING.keys(), key=len, reverse=True)]
ASSET_PATTERN = r"\\b(" + "|".join(escaped_keys) + r")\\b"


def get_yield_curve() -> dict[int, float]:
    if _YIELD_CURVE_CACHE:
        return _YIELD_CURVE_CACHE

    curve: dict[int, float] = {}
    for ticker, days in TICKER_DAYS.items():
        try:
            price = yf.Ticker(ticker).fast_info.last_price
            if price is not None:
                curve[days] = float(price)
        except Exception:
            continue

    if not curve:
        curve = FALLBACK_YIELDS.copy()

    _YIELD_CURVE_CACHE.update(curve)
    return _YIELD_CURVE_CACHE


def get_risk_free_rate(days_to_maturity: int) -> float:
    curve = get_yield_curve()
    points = sorted(curve.items())

    if days_to_maturity <= points[0][0]:
        return points[0][1]
    if days_to_maturity >= points[-1][0]:
        return points[-1][1]

    for i in range(len(points) - 1):
        d1, y1 = points[i]
        d2, y2 = points[i + 1]
        if d1 <= days_to_maturity <= d2:
            fraction = (days_to_maturity - d1) / (d2 - d1)
            return y1 + fraction * (y2 - y1)

    return points[-1][1]


def norm_cdf(x: float) -> float:
    \"\"\"Basic normal cumulative distribution function.\"\"\"
    return (1.0 + math.erf(x / math.sqrt(2.0))) / 2.0


def calculate_implied_probability(
    S: float, K: float, T_years: float, r: float, sigma: float
) -> float:
    \"\"\"Calculate the Black-Scholes implied probability N(d2) of finishing ITM.\"\"\"
    if T_years <= 0 or sigma <= 0:
        return 1.0 if S >= K else 0.0
    d2 = (math.log(S / K) + (r - 0.5 * sigma**2) * T_years) / (sigma * math.sqrt(T_years))
    return norm_cdf(d2)


def extract_financial_target(question: str) -> Tuple[str, float, bool] | None:
    \"\"\"Parse a Polymarket question to extract a ticker, target price, and direction.\"\"\"
    ticker_match = re.search(ASSET_PATTERN, question, re.IGNORECASE)
    if not ticker_match:
        return None

    matched_key = ticker_match.group(1).upper()
    ticker = ASSET_MAPPING.get(matched_key)
    if not ticker:
        return None

    # Match numeric target with optional commas and k/m suffixes
    price_match = re.search(r\"\\$?(\\d+(?:,\\d{3})*(?:\\.\\d+)?)\\s*([kKmM]?)\", question)
    if not price_match:
        return None

    price_str = price_match.group(1).replace(\",\", \"\")
    try:
        price = float(price_str)
    except ValueError:
        return None

    suffix = price_match.group(2).lower()
    if suffix == \"k\":
        price *= 1000.0
    elif suffix == \"m\":
        price *= 1000000.0

    # Direction: above (default) vs below
    is_above = True
    if re.search(r\"\\b(below|under|lower|less|crash|down)\\b\", question, re.IGNORECASE):
        is_above = False

    return ticker, price, is_above


def get_historical_volatility(ticker: str, days: int = 30) -> float | None:
    \"\"\"Calculate historical volatility based on the last `days` of daily returns.\"\"\"
    try:
        t = yf.Ticker(ticker)
        # Fetch a bit more to ensure we have enough trading days
        hist = t.history(period=f\"{days*2}d\")
        if hist.empty or len(hist) < 5:
            return None
            
        hist = hist.tail(days)
        returns = hist['Close'].pct_change().dropna()
        if returns.empty:
            return None
            
        trading_days = 365 if \"-\" in ticker else 252
        daily_vol = returns.std()
        annualized_vol = daily_vol * math.sqrt(trading_days)
        return float(annualized_vol)
    except Exception:
        return None


def get_tradfi_implied_probability(
    question: str, target_date: datetime
) -> float | None:
    \"\"\"
    Given a Polymarket question, attempt to derive a TradFi options-based implied probability.
    Returns None if no ticker match or data is unavailable.
    \"\"\"
    parsed = extract_financial_target(question)
    if not parsed:
        return None

    ticker, target_price, is_above = parsed

    try:
        t = yf.Ticker(ticker)
        current_price = t.fast_info.last_price
        if current_price is None or current_price == 0:
            # Maybe the fast_info failed, try history
            hist = t.history(period=\"1d\")
            if not hist.empty:
                current_price = hist['Close'].iloc[-1]
            if current_price is None or current_price == 0:
                return None

        # Attempt to get options data
        options = None
        try:
            options = t.options
        except Exception:
            pass

        sigma = None
        
        if options:
            # Find closest expiration date on or after target_date
            best_exp = None
            min_diff = float(\"inf\")
            for exp_str in options:
                try:
                    exp_date = datetime.strptime(exp_str, \"%Y-%m-%d\").replace(tzinfo=timezone.utc)
                    diff = (exp_date - target_date).days
                    if 0 <= diff < min_diff:
                        min_diff = diff
                        best_exp = exp_str
                except Exception:
                    continue

            if not best_exp:
                best_exp = options[-1]

            try:
                chain = t.option_chain(best_exp)
                calls = chain.calls
                if not calls.empty:
                    # Get IV from the option closest to the target strike
                    closest_call = calls.iloc[(calls[\"strike\"] - target_price).abs().argsort()[:1]]
                    if not closest_call.empty:
                        impl_vol = float(closest_call[\"impliedVolatility\"].values[0])
                        if impl_vol >= 0.01:
                            sigma = impl_vol
            except Exception:
                pass

        # Fallback to Historical Volatility if Options IV is unavailable or illiquid
        if sigma is None or sigma < 0.01:
            sigma = get_historical_volatility(ticker, days=30)
            
        if sigma is None or sigma < 0.01:
            sigma = 0.3  # Final fallback

        days_to_maturity = max(1, (target_date - datetime.now(timezone.utc)).days)
        T_years = days_to_maturity / 365.25
        r = get_risk_free_rate(days_to_maturity) / 100.0

        prob_above = calculate_implied_probability(
            current_price, target_price, T_years, r, sigma
        )

        return prob_above if is_above else max(0.0, 1.0 - prob_above)

    except Exception:
        return None
"""

with open('tradfi.py', 'w') as f:
    f.write(content)

