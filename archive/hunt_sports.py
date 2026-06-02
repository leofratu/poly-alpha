import json
import urllib.request
import numpy as np
from datetime import datetime, timezone
import dateutil.parser

def fetch_active_sports_markets(limit=1000):
    url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            events = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Failed to fetch markets: {e}")
        return []
        
    sports_markets = []
    
    # We want Non-Crypto (Sports, Pop Culture, etc)
    for event in events:
        tags = [t.get("label", "").lower() for t in event.get("tags", [])]
        if "crypto" in tags or "bitcoin" in tags or "ethereum" in tags:
            continue
            
        for m in event.get("markets", []):
            if not m.get("active") or m.get("closed"):
                continue
                
            q = m.get("question", "")
            end_date_str = m.get("endDate")
            if not end_date_str:
                continue
                
            try:
                target_date = dateutil.parser.isoparse(end_date_str).astimezone(timezone.utc)
            except Exception:
                continue
                
            
            now = datetime.now(timezone.utc)
            days = (target_date - now).days
            
            # Focus on short term < 30 days
            if days < 2 or days > 30:
                continue
                
            q_lower = q.lower()
            months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, 
                      "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
            
            mismatch = False
            for m_name, m_num in months.items():
                if m_name in q_lower and abs(target_date.month - m_num) > 2 and target_date.year == now.year:
                    mismatch = True
                    break
                    
            import re as regex
            years = regex.findall(r'(202[4-9])', q_lower)
            if years:
                latest_year = max([int(y) for y in years])
                if target_date.year < latest_year:
                    mismatch = True
                    
            if mismatch:
                continue
                
            print("CHECKING:", q_lower)
            # Bug Fix: Sports Futures Mismatch
            if regex.search(r'(win the|finish in|relegated|champion|championship|finals|premier league|la liga|serie a|bundesliga)', q_lower):
                continue

                
            try:
                tokens = json.loads(m.get("outcomePrices", "[]"))
                if not tokens or len(tokens) < 2:
                    continue
                    
                yes_price = float(tokens[0])
                
                # The "Retail Lotto Ticket" Bias: Retail bids 5% to 15% on massive underdogs
                if yes_price >= 0.03 and yes_price <= 0.15:
                    print("APPENDING:", q_lower)
                    sports_markets.append({
                        "question": q,
                        "days": days,
                        "yes_price": yes_price,
                        "tags": tags
                    })
            except Exception:
                pass
                
    return sports_markets

def analyze_sports_favorites():
    print("Hunting for Extreme Non-Crypto Favorites (Retail Lotto Bias)...\n")
    markets = fetch_active_sports_markets()
    
    # Sort by closest expiration
    markets.sort(key=lambda x: x["days"])
    
    print(f"Found {len(markets)} active short-term retail 'Lotto Ticket' markets (Yes Price between 3% and 15%).")
    print("Strategy: We act as the Casino House. We Buy the 'No' (The 85%+ Favorite).\n")
    
    for m in markets[:10]:
        no_price = 1.0 - m["yes_price"]
        # Retail pays the yes_price for a lotto ticket.
        # We lock up the no_price to win the remaining fraction.
        roi = (1.0 - no_price) / no_price
        apy = roi * (365.0 / m["days"])
        
        print(f"[{m['days']} Days] {m['question']}")
        print(f"  Retail buys 'Yes' for {m['yes_price']*100:.1f}% (The Lotto Ticket)")
        print(f"  We buy 'No' for {no_price*100:.1f}% (The Statistical Favorite)")
        print(f"  Absolute ROI: {roi*100:.2f}% | Annualized APY: {apy*100:.2f}%\n")

if __name__ == "__main__":
    analyze_sports_favorites()
