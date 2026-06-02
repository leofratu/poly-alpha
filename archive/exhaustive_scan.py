import json
import urllib.request
from datetime import datetime, timezone
import dateutil.parser
import re
from rich.console import Console
from rich.table import Table

console = Console()

def exhaustive_scan():
    console.print("[bold cyan]Initiating Exhaustive Scan of ALL Active Polymarket Events...[/bold cyan]")
    
    limit = 1000
    offset = 0
    all_events = []
    
    while True:
        url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit={limit}&offset={offset}"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/10.0"})
        try:
            with urllib.request.urlopen(req) as resp:
                batch = json.loads(resp.read().decode())
                if not batch:
                    break
                all_events.extend(batch)
                offset += limit
                console.print(f"Fetched {len(all_events)} events so far...")
        except Exception as e:
            console.print(f"[red]Error fetching batch at offset {offset}: {e}[/red]")
            break
            
    console.print(f"\n[green]Successfully downloaded {len(all_events)} total active events from Polymarket.[/green]\n")
    
    total_markets = 0
    valid_markets = []
    
    now = datetime.now(timezone.utc)
    
    for event in all_events:
        for m in event.get("markets", []):
            total_markets += 1
            if not m.get("active") or m.get("closed"): continue
                
            q = m.get("question", "")
            end_date_str = m.get("endDate")
            if not end_date_str: continue
                
            try:
                target_date = dateutil.parser.isoparse(end_date_str).astimezone(timezone.utc)
            except Exception: continue
                
            days = (target_date - now).total_seconds() / 86400.0
            
            # Constraint 1: Days to Expiry (Strictly < 30 Days)
            if days < 0 or days > 30.0: continue
            
            # Constraint 2: Date/Future Mismatch Bug Fix
            q_lower = q.lower()
            months = {"january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6, 
                      "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12}
            
            mismatch = False
            for m_name, m_num in months.items():
                if m_name in q_lower and abs(target_date.month - m_num) > 2 and target_date.year == now.year:
                    mismatch = True
                    break
                    
            years = re.findall(r'\b202[4-9]\b', q_lower)
            if years:
                latest_year = max([int(y) for y in years])
                if target_date.year < latest_year:
                    mismatch = True
                    
            if mismatch: continue
                
            if re.search(r'\b(win the|finish in|relegated|champion|championship|finals|premier league|la liga|serie a|bundesliga)\b', q_lower):
                continue
                
            try:
                tokens = json.loads(m.get("outcomePrices", "[]"))
                if len(tokens) < 2: continue
                yes_price = float(tokens[0])
                
                volume = float(m.get("volume", 0))
                liquidity = float(m.get("liquidity", volume * 0.05))
                
                # Constraint 3: Retail Bias + EV Sweet Spot + Liquidity
                if yes_price >= 0.05 and yes_price <= 0.15 and liquidity > 500:
                    valid_markets.append({
                        "question": q,
                        "days": days,
                        "yes": yes_price,
                        "liq": liquidity
                    })
            except Exception: pass
            
    valid_markets.sort(key=lambda x: x["days"])
    
    console.print(f"[bold yellow]Total Individual Markets Checked:[/bold yellow] {total_markets:,}")
    console.print(f"[bold green]Markets Passing All Mathematical Constraints:[/bold green] {len(valid_markets)}")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Market", style="cyan", width=55)
    table.add_column("Retail 'Yes'", justify="right", style="red")
    table.add_column("L2 Liquidity", justify="right", style="green")
    table.add_column("Time to Expiry", justify="right", style="yellow")
    
    for v in valid_markets:
        table.add_row(
            v["question"][:52] + "...",
            f"{v['yes']*100:.1f}%",
            f"${v['liq']:,.0f}",
            f"{v['days']:.1f} days"
        )
        
    console.print(table)
    console.print("\n[bold]Why lists change between runs:[/bold] Liquidity dynamically breathes on the BBO. A market might have $490 in liquidity at 10:00 AM (rejected by >$500 filter), and $510 at 10:05 AM (accepted). Price ticks between 4.9% and 5.0% also trigger rejection/acceptance boundaries.")

if __name__ == "__main__":
    exhaustive_scan()
