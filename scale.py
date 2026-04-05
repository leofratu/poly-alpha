from rich.console import Console
from rich.table import Table

console = Console()

def scale_math():
    # What if we don't just do "Sports < 72h" but actually deploy the entire Multi-Leg Quant Strategy across ALL timeframes?
    # Re-evaluating the aggregate volume of the platform.
    
    total_crypto_markets_month = 150 # BTC, ETH, SOL, Alts
    total_sports_markets_month = 200 # NBA, NFL, NHL, Tennis, Soccer
    total_politics_markets_month = 50 # Elections, Geopolitics
    
    total_markets_month = total_crypto_markets_month + total_sports_markets_month + total_politics_markets_month
    
    # We are not constrained to 20 trades a month if we trade across all timeframes (0 to 90 days)
    # Average trade duration across the blended portfolio: 30 days
    # Average ROI per trade (blended): 5.5%
    # Average Black Swan (Blended): 1.0% (Crypto is hedged, Sports is unhedged but lower tail risk)
    
    blended_markets_per_month = 150 
    avg_roi = 0.055
    black_swan_rate = 0.01
    
    starting_capital = 100000.0 # Institutional sizing
    current_capital = starting_capital
    
    for month in range(12):
        # Trade size: we deploy 100% of capital spread evenly across 150 markets
        capital_per_trade = current_capital / blended_markets_per_month
        
        monthly_profit = 0.0
        for trade in range(blended_markets_per_month):
            import random
            if random.random() < black_swan_rate:
                monthly_profit -= capital_per_trade
            else:
                monthly_profit += capital_per_trade * avg_roi
                
        current_capital += monthly_profit
        
    roi = (current_capital - starting_capital) / starting_capital
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Scaling the Architecture (All Timeframes)", style="cyan")
    table.add_column("Result", justify="right", style="yellow")
    
    table.add_row("Starting Bankroll", f"${starting_capital:,.2f}")
    table.add_row("Total Viable Markets (Monthly)", f"{blended_markets_per_month}")
    table.add_row("Average Expiry", "30 Days")
    table.add_row("Average Size per Trade", f"${current_capital/blended_markets_per_month:,.2f}")
    table.add_row("Black Swan Drag", "-1.0%")
    table.add_row("Expected 1-Year Bankroll", f"[bold green]${current_capital:,.2f}[/bold green]")
    table.add_row("Expected Annual Yield", f"[bold green]{roi*100:.2f}%[/bold green]")
    
    console.print(table)
    console.print("\n[bold]The Reality:[/bold] The 32,000% APY was a theoretical artifact of compounding a $100 trade every 2 days infinitely. Institutional quant funds don't make 32,000%. They make 70-120% on *massive size* ($100k+). This is how you actually scale the alpha.")

if __name__ == "__main__":
    scale_math()
