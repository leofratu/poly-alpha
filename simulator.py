from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

def simulate_trade(capital: float, yes_price: float, strike: float, expiry_days: int, tradfi_prob: float):
    console = Console()
    
    # Polymarket Leg (Short the binary by buying "No")
    no_price = 1.0 - yes_price
    # Assume 2% slippage on CLOB for size
    no_price_slippage = min(no_price * 1.02, 0.99) 
    
    pm_shares = capital / no_price_slippage
    pm_max_profit = (1.0 - no_price_slippage) * pm_shares
    
    # TradFi Hedge Leg (Replicating Binary with Call Spread)
    # To hedge 1 PM share ($1 payout), we need a call spread.
    # Strike 1: 150k, Strike 2: 151k. Width = $1000.
    # We need 1/1000th of a BTC contract per PM share.
    call_spread_width = 1000.0
    contracts_needed = pm_shares / call_spread_width
    
    # Estimate call spread cost based on TradFi probability (P-Measure)
    # Option pricing roughly aligns with P(ITM) * Width.
    # We add 20% premium for orderbook slippage and bid/ask spread crossing.
    estimated_spread_cost = tradfi_prob * call_spread_width * contracts_needed * 1.20
    
    # Net Capital Required
    total_capital = capital + estimated_spread_cost
    
    # Outcomes
    # Outcome 1: BTC < 150k (PM wins, Options expire worthless)
    net_profit_1 = pm_max_profit - estimated_spread_cost
    
    # Outcome 2: BTC > 151k (PM loses, Options pay out max width)
    options_payout = contracts_needed * call_spread_width
    net_profit_2 = options_payout - capital - estimated_spread_cost

    # ROI Math
    min_profit = min(net_profit_1, net_profit_2)
    roi = min_profit / total_capital
    apy = roi * (365.0 / expiry_days) if expiry_days > 0 else 0
    
    # Output
    console.print("\n[bold cyan]Execution Simulation & Viability Analysis[/bold cyan]")
    
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="yellow")
    table.add_row("Target Capital Limit", f"${capital:,.2f}")
    table.add_row("Days to Expiry (Lockup)", f"{expiry_days} days")
    table.add_row("Polymarket 'No' Fill Price (incl. 2% slip)", f"${no_price_slippage:.3f}")
    table.add_row("PM Shares Acquired", f"{pm_shares:,.0f} shares")
    table.add_row("Deribit Hedge (150k/151k Call Spread)", f"{contracts_needed:,.3f} BTC")
    table.add_row("TradFi Premium Paid (incl. 20% slip)", f"${estimated_spread_cost:,.2f}")
    console.print(Panel(table, title="[bold]Orderbook Execution Params[/bold]"))

    res_table = Table(show_header=True, header_style="bold magenta")
    res_table.add_column("Outcome Scenario", style="cyan")
    res_table.add_column("Gross Payout", justify="right", style="green")
    res_table.add_column("Net Profit", justify="right", style="green")
    
    res_table.add_row("BTC < $150k (Polymarket Wins)", f"${pm_shares:,.2f}", f"${net_profit_1:,.2f}")
    res_table.add_row("BTC > $151k (Deribit Hedge Wins)", f"${options_payout:,.2f}", f"${net_profit_2:,.2f}")
    console.print(res_table)
    
    summary = f"""
[bold]Viability Check:[/bold]
Total Capital Locked: [yellow]${total_capital:,.2f}[/yellow]
Guaranteed Minimum Profit: [green]${min_profit:,.2f}[/green]
Absolute ROI: [magenta]{roi*100:.2f}%[/magenta]
Annualized APY: [bold cyan]{apy*100:.2f}%[/bold cyan]

[bold red]Verdict:[/bold red] {'✅ VIABLE' if apy > 0.05 else '❌ SUB-OPTIMAL'} (Capital opportunity cost > 5.0% risk-free rate)
"""
    console.print(summary)

if __name__ == "__main__":
    # Hardcoded test for BTC 150k Dec 2026
    simulate_trade(capital=10000.0, yes_price=0.105, strike=150000.0, expiry_days=278, tradfi_prob=0.031)
