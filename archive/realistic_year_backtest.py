import numpy as np
from rich.console import Console
from rich.table import Table

console = Console()

def run_single_simulation(starting_capital, markets_per_month, max_capital_per_market, base_black_swan_rate, avg_roi_per_trade):
    current_capital = starting_capital
    peak_capital = starting_capital
    max_drawdown = 0.0
    
    for month in range(12):
        capital_per_trade = current_capital / markets_per_month
        
        if capital_per_trade > max_capital_per_market:
            capital_per_trade = max_capital_per_market
            
        monthly_profit = 0.0
        
        for trade in range(markets_per_month):
            if np.random.rand() < base_black_swan_rate:
                monthly_profit -= capital_per_trade
            else:
                monthly_profit += capital_per_trade * avg_roi_per_trade
                
        current_capital += monthly_profit
        
        if current_capital > peak_capital:
            peak_capital = current_capital
        else:
            drawdown = (peak_capital - current_capital) / peak_capital
            if drawdown > max_drawdown:
                max_drawdown = drawdown
                
    return current_capital, max_drawdown

def realistic_annual_backtest(starting_capital=1000.0):
    console.print("[bold cyan]Initializing 1-Year Realistic Constraints Monte Carlo (10,000 runs)...[/bold cyan]")
    
    markets_per_month = 20
    max_capital_per_market = 2500.0 
    base_black_swan_rate = 0.015 
    avg_roi_per_trade = 0.045
    
    final_capitals = []
    max_drawdowns = []
    
    for _ in range(10000):
        final_cap, md = run_single_simulation(starting_capital, markets_per_month, max_capital_per_market, base_black_swan_rate, avg_roi_per_trade)
        final_capitals.append(final_cap)
        max_drawdowns.append(md)
        
    avg_final_capital = np.mean(final_capitals)
    avg_max_drawdown = np.mean(max_drawdowns)
    avg_apy = (avg_final_capital - starting_capital) / starting_capital
    
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Real-World Constraint", style="cyan")
    table.add_column("Value", justify="right", style="yellow")
    table.add_row("Starting Bankroll", f"${starting_capital:,.2f}")
    table.add_row("Market Inventory Limit", f"{markets_per_month} trades / month")
    table.add_row("L2 Liquidity Cap (Max Size per Trade)", f"${max_capital_per_market:,.2f}")
    table.add_row("Calibrated Black Swan Hit Rate", f"{base_black_swan_rate*100:.2f}%")
    table.add_row("Average Net ROI per Trade", f"{avg_roi_per_trade*100:.1f}%")
    
    console.print(table)
    
    res_table = Table(show_header=True, header_style="bold green")
    res_table.add_column("Monte Carlo Results (1 Year)", style="cyan")
    res_table.add_column("Result", justify="right", style="bold white")
    res_table.add_row("Average Ending Bankroll", f"${avg_final_capital:,.2f}")
    res_table.add_row("Average Max Drawdown", f"[bold red]{avg_max_drawdown*100:.2f}%[/bold red]")
    res_table.add_row("Realistic Expected Annual Yield", f"[bold green]{avg_apy*100:.2f}%[/bold green]")
    res_table.add_row("Worst Case (5th Percentile)", f"${np.percentile(final_capitals, 5):,.2f}")
    res_table.add_row("Best Case (95th Percentile)", f"${np.percentile(final_capitals, 95):,.2f}")
    
    console.print(res_table)
    
    console.print("\n[bold yellow]The Truth About 30,000% APY:[/bold yellow]")
    console.print("1. [white]Inventory Squeeze:[/white] You cannot find 10 perfect markets every 2 days. The real flow is ~20 viable short-term lotto markets a month.")
    console.print("2. [white]Black Swans Exist:[/white] A 1.5% real-world hit rate means you WILL lose 100% of your collateral 1 out of every 66 trades. A huge bankroll guarantees you will hit them.")
    console.print("3. [white]Liquidity Ceiling:[/white] You cannot compound infinitely. The L2 order book physically caps your max trade size at ~$2,500 for the ultra-fast markets.")

if __name__ == "__main__":
    realistic_annual_backtest(1000.0)
