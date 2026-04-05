import json
import urllib.request
from datetime import datetime, timezone
import dateutil.parser
from rich.console import Console
from rich.table import Table

console = Console()

def fetch_active_lotto_markets(limit=3000):
    url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            events = json.loads(resp.read().decode())
    except Exception as e:
        console.print(f"[red]Failed to fetch markets: {e}[/red]")
        return []
        
    viable_markets = []
    
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
            
            # FOCUS ON EXTREME SHORT TERM: Expiry in < 14 Days
            if days < 1 or days > 14:
                continue
                
            try:
                tokens = json.loads(m.get("outcomePrices", "[]"))
                if not tokens or len(tokens) < 2:
                    continue
                    
                yes_price = float(tokens[0])
                
                # The "Retail Lotto Ticket" Bias: Retail bids 1% to 15% on extreme underdogs
                if yes_price >= 0.01 and yes_price <= 0.15:
                    viable_markets.append({
                        "question": q,
                        "days": days,
                        "yes_price": yes_price
                    })
            except Exception:
                pass
                
    return viable_markets

def analyze_max_volume():
    markets = fetch_active_lotto_markets()
    
    # Sort by closest expiration
    markets.sort(key=lambda x: x["days"])
    
    console.print(f"[bold cyan]Hunting for Max-Volume Extreme Short-Term Alpha (< 14 Days)[/bold cyan]")
    console.print(f"Discovered [bold green]{len(markets)}[/bold green] active markets mathematically ripe for the 'No' Casino Strategy.\n")
    
    if len(markets) == 0:
        return
        
    avg_days = sum(m["days"] for m in markets) / len(markets)
    avg_yes = sum(m["yes_price"] for m in markets) / len(markets)
    avg_no = 1.0 - avg_yes
    
    # Capital required to put $1,000 to work in ALL markets
    capital_per_market = 1000.0
    total_capital = len(markets) * capital_per_market
    
    # Assume a 3% Black Swan hit rate
    black_swans = int(len(markets) * 0.03)
    wins = len(markets) - black_swans
    
    # Calculate Total Return per Cycle
    total_payout = wins * (capital_per_market / avg_no)
    net_profit = total_payout - total_capital
    roi = net_profit / total_capital
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Portfolio Metric", style="cyan")
    table.add_column("Value", justify="right", style="yellow")
    
    table.add_row("Total Independent Markets Found", f"{len(markets)}")
    table.add_row("Average Expiry (Days)", f"{avg_days:.1f}")
    table.add_row("Average Retail 'Yes' Bloat", f"{avg_yes*100:.1f}%")
    table.add_row("Total Capital Deployed ($1k/mkt)", f"${total_capital:,.2f}")
    table.add_row("Simulated Black Swans (3%)", f"{black_swans} complete losses")
    table.add_row("Net Expected Profit per Cycle", f"[bold green]${net_profit:,.2f}[/bold green]")
    table.add_row("Absolute ROI per Cycle", f"{roi*100:.2f}%")
    
    console.print(table)
    
    # Compounded Monthly Yield Calculation (assuming reinvestment at max volume)
    cycles_per_month = 30.44 / avg_days
    monthly_yield = ((1 + roi) ** cycles_per_month) - 1
    console.print(f"\n[bold]Theoretical Monthly Yield (Reinvesting across {len(markets)} markets):[/bold] [bold green]{monthly_yield*100:.2f}%[/bold green]")
    
if __name__ == "__main__":
    analyze_max_volume()
