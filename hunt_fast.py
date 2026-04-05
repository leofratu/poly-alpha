import json
import urllib.request
from datetime import datetime, timezone
import dateutil.parser

def fetch_active_fast_markets(limit=5000):
    url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            events = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Failed to fetch markets: {e}")
        return []
        
    fast_markets = []
    
    for event in events:
        for m in event.get("markets", []):
            if not m.get("active") or m.get("closed"):
                continue
                
            q = m.get("question", "")
            end_date_str = m.get("endDate")
            if not end_date_str:
                continue
                
            try:
                target_date = dateutil.parser.isoparse(end_date_str).astimezone(timezone.utc)
            except:
                continue
                
            now = datetime.now(timezone.utc)
            days = (target_date - now).days
            
            # FOCUS ON EXTREME SHORT TERM: Expiry in < 3 Days (72 Hours)
            if days < 0 or days > 3:
                continue
                
            try:
                tokens = json.loads(m.get("outcomePrices", "[]"))
                if not tokens or len(tokens) < 2:
                    continue
                    
                yes_price = float(tokens[0])
                
                # The "Retail Lotto Ticket" Bias: Retail bids 1% to 25% on extreme underdogs
                if yes_price >= 0.01 and yes_price <= 0.25:
                    fast_markets.append({
                        "question": q,
                        "days": days,
                        "yes_price": yes_price,
                        "volume": float(m.get("volume", 0))
                    })
            except Exception:
                pass
                
    return fast_markets

def analyze_fast():
    markets = fetch_active_fast_markets()
    markets.sort(key=lambda x: x["days"])
    
    print(f"Hunting for Ultra-Fast Alpha (< 72 Hours Expiry)...\n")
    print(f"Found {len(markets)} active markets expiring in less than 3 days.\n")
    
    for m in markets[:15]:
        no_price = 1.0 - m["yes_price"]
        roi = (1.0 - no_price) / no_price
        apy = roi * (365.0 / max(0.5, m["days"])) # Floor at 0.5 days (12 hours) to avoid division by zero
        
        print(f"[{m['days']} Days] {m['question']}")
        print(f"  Retail buys 'Yes' for {m['yes_price']*100:.1f}%")
        print(f"  We buy 'No' for {no_price*100:.1f}%")
        print(f"  Absolute ROI: {roi*100:.2f}% | Annualized APY: {apy*100:.2f}%\n")

if __name__ == "__main__":
    analyze_fast()
