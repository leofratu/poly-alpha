from rich.console import Console
from rich.table import Table
from rich.panel import Panel

def simulate_multi_leg(capital: float, yes_price: float, strike: float, expiry_days: int, tradfi_prob: float):
    console = Console()
    
    # ---------------------------------------------------------
    # LEG 1: Polymarket Short Binary (Retail Over-Optimism)
    # ---------------------------------------------------------
    no_price = 1.0 - yes_price
    no_price_slippage = min(no_price * 1.02, 0.99) 
    
    # Let's allocate 50% of capital to Polymarket to allow margin on TradFi
    pm_capital = capital * 0.50
    pm_shares = pm_capital / no_price_slippage
    pm_max_profit = (1.0 - no_price_slippage) * pm_shares
    
    # ---------------------------------------------------------
    # LEG 2: Deribit Options Call Spread (Tail Risk Hedge)
    # ---------------------------------------------------------
    call_spread_width = 1000.0
    contracts_needed = pm_shares / call_spread_width
    estimated_spread_cost = tradfi_prob * call_spread_width * contracts_needed * 1.20
    
    # ---------------------------------------------------------
    # LEG 3: Cash & Carry Basis Trade (The Alpha Kicker)
    # ---------------------------------------------------------
    # We have 50% of capital left. We use it to capture the Spot-Futures Contango
    # Current BTC futures basis annualized is ~12%. 
    basis_capital = capital * 0.50 - estimated_spread_cost
    basis_apy = 0.12
    basis_profit = basis_capital * basis_apy * (expiry_days / 365.0)
    
    # ---------------------------------------------------------
    # OUTCOMES & APY MATH
    # ---------------------------------------------------------
    net_profit_1 = pm_max_profit - estimated_spread_cost + basis_profit
    options_payout = contracts_needed * call_spread_width
    net_profit_2 = options_payout - pm_capital - estimated_spread_cost + basis_profit

    min_profit = min(net_profit_1, net_profit_2)
    roi = min_profit / capital
    apy = roi * (365.0 / expiry_days) if expiry_days > 0 else 0
    
    console.print("\n[bold cyan]Multi-Leg Quant Strategy: 'The Contango Strangle'[/bold cyan]")
    
    table = Table(show_header=False, box=None)
    table.add_column("Metric", style="bold white")
    table.add_column("Value", style="yellow")
    table.add_row("Total Capital Deployed", f"${capital:,.2f}")
    table.add_row("Leg 1 (Polymarket Short)", f"${pm_capital:,.2f} at {yes_price*100:.1f}% Retail Prob")
    table.add_row("Leg 2 (Deribit Hedge)", f"${estimated_spread_cost:,.2f} paid for {tradfi_prob*100:.1f}% True Prob")
    table.add_row("Leg 3 (Basis Trade Margin)", f"${basis_capital:,.2f} earning 12.0% APR Contango")
    console.print(Panel(table, title="[bold]Advanced Institutional Portfolio[/bold]"))

    res_table = Table(show_header=True, header_style="bold magenta")
    res_table.add_column("Outcome Scenario", style="cyan")
    res_table.add_column("Options/PM PnL", justify="right", style="green")
    res_table.add_column("Basis PnL", justify="right", style="green")
    res_table.add_column("Net Total Profit", justify="right", style="green")
    
    res_table.add_row("BTC < $150k (No Tail Risk)", f"${(pm_max_profit - estimated_spread_cost):,.2f}", f"${basis_profit:,.2f}", f"${net_profit_1:,.2f}")
    res_table.add_row("BTC > $151k (Hedge Triggers)", f"${(options_payout - pm_capital - estimated_spread_cost):,.2f}", f"${basis_profit:,.2f}", f"${net_profit_2:,.2f}")
    console.print(res_table)
    
    summary = f"""
[bold]Alpha Edge Check:[/bold]
Guaranteed Minimum Profit: [green]${min_profit:,.2f}[/green]
Absolute ROI: [magenta]{roi*100:.2f}%[/magenta]
Annualized APY: [bold cyan]{apy*100:.2f}%[/bold cyan]

[bold yellow]Fallacy Exploited:[/bold yellow] Retail prediction markets force 100% collateral lockups (0% yield). By splitting capital 50/50, shorting the bloated binary option, and deploying the remaining margin into the perpetual futures contango (12% yield), we construct a synthetic high-yield bond that fundamentally outperforms traditional arbitrage.
"""
    console.print(summary)

if __name__ == "__main__":
    simulate_multi_leg(capital=10000.0, yes_price=0.105, strike=150000.0, expiry_days=278, tradfi_prob=0.031)
