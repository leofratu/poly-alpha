from __future__ import annotations

import json
import urllib.request
from datetime import datetime, timezone
from typing import Final

DERIBIT_URL: Final[str] = "https://www.deribit.com/api/v2/public"

def get_deribit_implied_volatility(currency: str, target_price: float, target_date: datetime) -> float | None:
    """
    Fetches the live implied volatility from Deribit for the option closest 
    to the target strike and expiration date. Memory safe: purely REST/JSON.
    """
    if currency not in {"BTC", "ETH", "SOL"}:
        return None

    try:
        url = f"{DERIBIT_URL}/get_instruments?currency={currency}&kind=option&expired=false"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyArbScanner/1.0"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read().decode())
        
        instruments = data.get("result", [])
        if not instruments:
            return None

        # Find closest expiration
        best_instrument = None
        min_date_diff = float("inf")
        min_strike_diff = float("inf")

        for inst in instruments:
            exp_ts = inst.get("expiration_timestamp", 0) / 1000.0
            if exp_ts == 0:
                continue
            
            exp_date = datetime.fromtimestamp(exp_ts, tz=timezone.utc)
            date_diff = abs((exp_date - target_date).days)
            
            strike = inst.get("strike", 0.0)
            strike_diff = abs(strike - target_price)

            # Prioritize date match first, then strike proximity
            if date_diff < min_date_diff:
                min_date_diff = date_diff
                min_strike_diff = strike_diff
                best_instrument = inst
            elif date_diff == min_date_diff and strike_diff < min_strike_diff:
                min_strike_diff = strike_diff
                best_instrument = inst

        if not best_instrument:
            return None

        # Fetch live order book IV for the selected instrument
        inst_name = best_instrument["instrument_name"]
        book_url = f"{DERIBIT_URL}/ticker?instrument_name={inst_name}"
        book_req = urllib.request.Request(book_url, headers={"User-Agent": "PolyArbScanner/1.0"})
        with urllib.request.urlopen(book_req, timeout=5) as resp:
            book_data = json.loads(resp.read().decode())
        
        result = book_data.get("result", {})
        # Average the bid/ask IV, or fallback to mark IV
        bid_iv = result.get("bid_iv", 0.0)
        ask_iv = result.get("ask_iv", 0.0)
        mark_iv = result.get("mark_iv", 0.0)

        if bid_iv > 0 and ask_iv > 0:
            iv = (bid_iv + ask_iv) / 2.0
        else:
            iv = mark_iv

        if iv > 0:
            return iv / 100.0  # Deribit returns IV as a percentage (e.g., 50.5 for 50.5%)
        
        return None

    except Exception:
        return None
