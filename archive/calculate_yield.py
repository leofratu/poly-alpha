from rich.console import Console
from rich.table import Table
import numpy as np

console = Console()

def calculate_compounded_yield(starting_capital=1000.0):
    # Base params from historical backtest & hunt_fast.py
    avg_expiry_days = 2.5 # Sub 72-hour markets
    avg_roi_per_trade = 0.0515 # 5.15% average ROI on the "No" side
    
    # Capital Allocation (Kelly Fraction)
    # The L2 limit is ~ $10k per market, so $1,000 fits perfectly into 1 market
    # Or, we can spread the $1,000 across 10 simultaneous sub-72h markets ($100 each)
    markets_per_cycle = 10
    capital_per_market = starting_capital / markets_per_cycle
    
    # Time Cycles
    days_in_month = 30.44
    cycles_per_month = days_in_month / avg_expiry_days
    
    # We assume a highly conservative 1% Black Swan hit rate
    # Meaning 1% of the time, the "Yes" lotto ticket actually hits and we lose 100% of the collateral on that specific bet
    win_rate = 0.99
    
    # Expected Value per trade
    ev_per_trade = (win_rate * avg_roi_per_trade) - ((1 - win_rate) * 1.0)
    
    # Monthly Compounding
    current_capital = starting_capital
    monthly_pnl_trajectory = []
    
    for i in range(int(cycles_per_month)):
        # Every cycle, we reinvest the full capital across 10 markets
        # Correct the EV calculation for the entire portfolio
        # EV per trade is the return ON THE CAPITAL ALLOCATED to that trade
        # The overall portfolio EV is just the EV per trade (since we allocate 100% of capital equally across all trades)
        cycle_profit = current_capital * ev_per_trade
        current_capital += cycle_profit
        monthly_pnl_trajectory.append(current_capital)
        
    total_profit = current_capital - starting_capital
    monthly_yield = total_profit / starting_capital
    annualized_yield = ((1 + monthly_yield) ** 12) - 1
    
    console.print(f"\n[bold cyan]Quantitative Capital Allocation & Compounded Yield Analysis[/bold cyan]")
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Parameter", style="cyan")
    table.add_column("Value", justify="right", style="yellow")
    
    table.add_row("Starting Bankroll", f"${starting_capital:,.2f}")
    table.add_row("Markets per Cycle (Diversification)", f"{markets_per_cycle} markets")
    table.add_row("Capital per Market", f"${capital_per_market:,.2f}")
    table.add_row("Average Expiry Time", f"{avg_expiry_days} Days")
    table.add_row("Turnover Cycles per Month", f"{cycles_per_month:.1f} Cycles")
    table.add_row("Average L2 ROI (No Side)", f"{avg_roi_per_trade*100:.2f}%")
    table.add_row("Conservative Black Swan Penalty", "1.00%")
    table.add_row("Net Expected Value (EV) per Cycle", f"{ev_per_trade*100:.2f}%")
    table.add_row("Ending Bankroll (Month 1)", f"[bold green]${current_capital:,.2f}[/bold green]")
    table.add_row("Compounded Monthly Yield", f"[bold green]{monthly_yield*100:.2f}%[/bold green]")
    table.add_row("Annualized Compounded APY", f"[bold green]{annualized_yield*100:.2f}%[/bold green]")
    
    console.print(table)
    
if __name__ == "__main__":
    calculate_compounded_yield(1000.0)
