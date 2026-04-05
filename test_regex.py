import re

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
ASSET_PATTERN = r"\b(" + "|".join(escaped_keys) + r")\b"

questions = [
    "Will ETH close above $2,500?",
    "Will SPY close above 500?",
    "Will S&P 500 close above 5000?",
    "Bitcoin to $100k?",
    "Will Solana crash below $100?"
]

for q in questions:
    match = re.search(ASSET_PATTERN, q, re.IGNORECASE)
    if match:
        key = match.group(1).upper()
        print(f"{q} -> {key} -> {ASSET_MAPPING.get(key)}")
    else:
        print(f"{q} -> No match")
