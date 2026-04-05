import json
import urllib.request
from datetime import datetime, timezone
import dateutil.parser

from tradfi import extract_financial_target, get_tradfi_implied_probability
from simulator import simulate_trade

def fetch_crypto_markets(limit=1000):
    url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "PolyArbScanner/2.0"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

events = fetch_crypto_markets()
found_alpha = []

for event in events:
    markets = event.get("markets", [])
    for m in markets:
        if not m.get("active") or m.get("closed"):
            continue
            
        question = m.get("question", "")
        # Filter out temporal drift fallacies (must be a strict fixed date)
        if "before" in question.lower() or "until" in question.lower() or "before GTA" in question:
            continue
            
        end_date_str = m.get("endDate")
        if not end_date_str:
            continue
            
        try:
            target_date = dateutil.parser.isoparse(end_date_str).astimezone(timezone.utc)
        except:
            continue
            
        now = datetime.now(timezone.utc)
        days = (target_date - now).days
        if days < 7 or days > 365:
            continue
            
        parsed = extract_financial_target(question)
        if not parsed:
            continue
            
        try:
            tokens = json.loads(m.get("outcomePrices", "[]"))
            if not tokens or len(tokens) < 2:
                continue
                
            yes_price = float(tokens[0])
            if yes_price <= 0.02 or yes_price >= 0.98:
                continue
                
            tradfi_prob = get_tradfi_implied_probability(question, target_date)
            if tradfi_prob is None:
                continue
                
            spread = abs(yes_price - tradfi_prob)
            
            no_price_slippage = min((1.0 - yes_price) * 1.02, 0.99)
            pm_shares = 10000.0 / no_price_slippage
            pm_max_profit = (1.0 - no_price_slippage) * pm_shares
            
            if parsed.ticker == "BTC-USD":
                width = 1000.0
            elif parsed.ticker == "ETH-USD":
                width = 100.0
            elif parsed.ticker == "SOL-USD":
                width = 5.0
            else:
                width = parsed.target_price * 0.01
                
            contracts = pm_shares / width
            est_cost = tradfi_prob * width * contracts * 1.20
            
            net = pm_max_profit - est_cost
            total_cap = 10000.0 + est_cost
            
            if total_cap > 0:
                roi = net / total_cap
                apy = roi * (365.0 / days) if days > 0 else 0
                
                if apy > 0.05:
                    found_alpha.append({
                        "question": question,
                        "ticker": parsed.ticker,
                        "strike": parsed.target_price,
                        "days": days,
                        "pm_yes": yes_price,
                        "tradfi": tradfi_prob,
                        "spread": spread,
                        "apy": apy,
                        "roi": roi
                    })
        except Exception as e:
            pass

found_alpha.sort(key=lambda x: x["apy"], reverse=True)

print("\n--- NEW MULTI-TRADE SHORT-TERM ALPHA FOUND ---")
for alpha in found_alpha[:5]:
    print(f"\n[VIABLE] {alpha['question']}")
    print(f"Lockup: {alpha['days']} days | APY: {alpha['apy']*100:.2f}% | ROI: {alpha['roi']*100:.2f}% | Polymarket Retail: {alpha['pm_yes']*100:.1f}% | Deribit/TradFi: {alpha['tradfi']*100:.1f}%")

