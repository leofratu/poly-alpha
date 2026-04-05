import json
import urllib.request
from datetime import datetime, timezone
import dateutil.parser

from tradfi import extract_financial_target, get_tradfi_implied_probability
from multi_leg import simulate_multi_leg

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
        if "before" in question.lower() or "until" in question.lower() or "gta" in question.lower():
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
        
        # FOCUS ON SHORT TERM: 3 to 45 days
        if days < 3 or days > 45:
            continue
            
        parsed = extract_financial_target(question)
        if not parsed:
            continue
            
        try:
            tokens = json.loads(m.get("outcomePrices", "[]"))
            if not tokens or len(tokens) < 2:
                continue
                
            yes_price = float(tokens[0])
            # For short term, retail loves buying lotto tickets (1% to 10%)
            if yes_price <= 0.005 or yes_price >= 0.99:
                continue
                
            tradfi_prob = get_tradfi_implied_probability(question, target_date)
            if tradfi_prob is None:
                continue
                
            # Simulate the Multi-Leg Trade mathematically to get APY
            capital = 10000.0
            no_price_slippage = min((1.0 - yes_price) * 1.02, 0.99)
            pm_capital = capital * 0.50
            pm_shares = pm_capital / no_price_slippage
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
            
            basis_capital = capital * 0.50 - est_cost
            basis_apy = 0.12
            basis_profit = basis_capital * basis_apy * (days / 365.0)
            
            net_1 = pm_max_profit - est_cost + basis_profit
            net_2 = (contracts * width) - pm_capital - est_cost + basis_profit
            
            min_profit = min(net_1, net_2)
            if min_profit > 0:
                roi = min_profit / capital
                apy = roi * (365.0 / days)
                
                # Filter for trades yielding > 10% APY
                if apy > 0.10:
                    found_alpha.append({
                        "question": question,
                        "days": days,
                        "pm_yes": yes_price,
                        "tradfi": tradfi_prob,
                        "apy": apy,
                        "roi": roi
                    })
        except Exception as e:
            pass

found_alpha.sort(key=lambda x: x["apy"], reverse=True)

print("\n--- ULTRA SHORT-TERM MULTI-LEG ALPHA (<45 DAYS) ---")
for alpha in found_alpha[:10]:
    print(f"\n[VIABLE] {alpha['question']}")
    print(f"Lockup: {alpha['days']} days | APY: {alpha['apy']*100:.2f}% | ROI: {alpha['roi']*100:.2f}%")
    print(f"Retail Lotts (Q-Measure): {alpha['pm_yes']*100:.1f}% | Deribit Math (P-Measure): {alpha['tradfi']*100:.2f}%")

if not found_alpha:
    print("No viable >10% APY short-term spreads found right now. Trying looser constraints...")
