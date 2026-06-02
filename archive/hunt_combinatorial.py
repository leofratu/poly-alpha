import json
import urllib.request
import itertools

def fetch_crypto_markets(limit=1000):
    url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "PolyArbScanner/2.0"})
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode())

events = fetch_crypto_markets()

print("Scanning for Combinatorial Arbitrage (Semantic Dependency Mismatches)...\n")

# Example: Finding markets that are logically dependent but priced differently.
# (e.g. "Will BTC hit 100k?" vs "Will BTC hit 150k?")
# If P(150k) > P(100k), there is a pure combinatorial arbitrage.

btc_markets = []
for event in events:
    for m in event.get("markets", []):
        q = m.get("question", "")
        if "Will Bitcoin hit" in q and "by" in q:
            try:
                tokens = json.loads(m.get("outcomePrices", "[]"))
                if not tokens or len(tokens) < 2:
                    continue
                yes_price = float(tokens[0])
                
                # Extract strike
                import re
                strike_match = re.search(r'\$(\d+)k', q)
                if not strike_match:
                    continue
                strike = int(strike_match.group(1)) * 1000
                
                date_match = re.search(r'by (.*)\??', q)
                if not date_match:
                    continue
                date_str = date_match.group(1).replace('?', '').strip()
                
                btc_markets.append({
                    "q": q,
                    "strike": strike,
                    "date": date_str,
                    "yes_price": yes_price
                })
            except Exception:
                pass

# Group by exact same date
grouped = {}
for m in btc_markets:
    grouped.setdefault(m["date"], []).append(m)

found_arb = False
for date, markets in grouped.items():
    if len(markets) < 2:
        continue
    
    # Sort by strike price ascending
    markets.sort(key=lambda x: x["strike"])
    
    # Logic: P(BTC > 100k) MUST BE >= P(BTC > 150k)
    # If P(Higher Strike) > P(Lower Strike), risk-free combinatorial arb exists.
    for i in range(len(markets) - 1):
        lower_strike_market = markets[i]
        higher_strike_market = markets[i+1]
        
        if higher_strike_market["yes_price"] > lower_strike_market["yes_price"]:
            found_arb = True
            print(f"[COMBINATORIAL ARBITRAGE DETECTED!]")
            print(f"Violation of Probability Monotonicity:")
            print(f"Lower Strike ({lower_strike_market['strike']}): {lower_strike_market['yes_price']*100:.1f}% -> {lower_strike_market['q']}")
            print(f"Higher Strike ({higher_strike_market['strike']}): {higher_strike_market['yes_price']*100:.1f}% -> {higher_strike_market['q']}")
            print(f"Action: Buy YES on Lower Strike, Buy NO on Higher Strike.\n")

if not found_arb:
    print("No Probability Monotonicity violations found in current BTC strike chains.")
