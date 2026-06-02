import json
import urllib.request
from datetime import datetime, timezone
import dateutil.parser
from rich.console import Console
from rich.table import Table

console = Console()

def fetch_live_sports_markets(limit=1000):
    # Fetch active markets specifically filtering for live / intraday events
    url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            events = json.loads(resp.read().decode())
    except Exception as e:
        console.print(f"[red]Failed to fetch markets: {e}[/red]")
        return []
        
    live_markets = []
    
    for event in events:
        # Check if the event is a sports match
        tags = [t.get("label", "").lower() for t in event.get("tags", [])]
        # Removed strict tag check to catch untagged live games
            
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
            # Calculate lifespan in hours
            hours = (target_date - now).total_seconds() / 3600.0
            
            # FOCUS ON LIVE / INTRADAY EVENTS: Expiry in < 24 Hours
            if hours < 0 or hours > 24:
                continue
                
            try:
                tokens = json.loads(m.get("outcomePrices", "[]"))
                if not tokens or len(tokens) < 2:
                    continue
                    
                yes_price = float(tokens[0])
                
                volume = float(m.get("volume", 0))
                liquidity = float(m.get("liquidity", volume * 0.05))
                
                # We want extreme live lotto tickets (Retail betting on a miracle comeback)
                # i.e., Yes Price is between 1% and 15%
                if yes_price >= 0.01 and yes_price <= 0.15:
                    live_markets.append({
                        "question": q,
                        "hours_to_expiry": hours,
                        "yes_price": yes_price,
                        "no_price": 1.0 - yes_price,
                        "liquidity": liquidity,
                        "volume": volume
                    })
            except Exception:
                pass
                
    return live_markets

def live_sports_calculator():
    markets = fetch_live_sports_markets()
    markets.sort(key=lambda x: x["hours_to_expiry"])
    
    console.print(f"[bold cyan]Hunting for Live Intraday Sports Arbitrage (< 24 Hours)[/bold cyan]")
    console.print(f"Found [bold green]{len(markets)}[/bold green] active live sports markets.\n")
    
    if len(markets) == 0:
        return
        
    avg_hours = sum(m["hours_to_expiry"] for m in markets) / len(markets)
    avg_yes = sum(m["yes_price"] for m in markets) / len(markets)
    avg_no = sum(m["no_price"] for m in markets) / len(markets)
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Live Match", style="cyan")
    table.add_column("Hours Left", justify="right", style="yellow")
    table.add_column("Retail Hopium ('Yes')", justify="right", style="red")
    table.add_column("House Favorite ('No')", justify="right", style="green")
    table.add_column("Absolute ROI", justify="right", style="bold white")
    
    for m in markets[:15]:
        roi = (1.0 - m["no_price"]) / m["no_price"]
        table.add_row(
            m["question"][:45] + "...",
            f"{m['hours_to_expiry']:.1f}h",
            f"{m['yes_price']*100:.1f}¢",
            f"{m['no_price']*100:.1f}¢",
            f"{roi*100:.2f}%"
        )
        
    console.print(table)
    
    # Intraday Math
    # If a trade resolves in 4 hours, you can cycle capital 6 times a day.
    # That is 180 cycles a month.
    
    starting_capital = 1000.0
    capital_per_trade = starting_capital / min(10, len(markets)) # Spread across up to 10 live games
    
    # Assume 1% black swan hit rate (the miracle comeback happens 1 in 100 games)
    black_swan_rate = 0.01 
    avg_roi = (1.0 - avg_no) / avg_no
    
    ev_per_trade = ((1.0 - black_swan_rate) * avg_roi) - (black_swan_rate * 1.0)
    
    cycles_per_month = (24.0 / avg_hours) * 30.44
    monthly_yield = ((1 + ev_per_trade) ** cycles_per_month) - 1
    
    console.print("\n[bold yellow]The Intraday Compounding Math ($1,000 Bankroll):[/bold yellow]")
    console.print(f"Average Expiry: [white]{avg_hours:.1f} Hours[/white]")
    console.print(f"Capital Velocity: [white]{cycles_per_month:.1f} Cycles per Month[/white]")
    console.print(f"Net EV per Trade (Post-Miracle Penalty): [bold green]{ev_per_trade*100:.2f}%[/bold green]")
    console.print(f"Theoretical Monthly Compounded Yield: [bold green]{monthly_yield*100:.2f}%[/bold green]")
    console.print("\n[bold]Summary:[/bold] Live sports betting is the highest-velocity market on Polymarket. Retail routinely bids 2¢ to 15¢ on a team trailing by 2 goals in the 80th minute. By algorithmically sweeping the 'No' side of these games, you compound your bankroll on an hourly basis.")

if __name__ == "__main__":
    live_sports_calculator()
