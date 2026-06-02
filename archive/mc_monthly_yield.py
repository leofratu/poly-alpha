import numpy as np
from rich.console import Console
from rich.table import Table

console = Console()

def run_monte_carlo(starting_capital=1000.0, months=1, iterations=100000):
    # Live Executor Parameters
    risk_per_trade = 0.15 # 15% of total portfolio per trade
    trades_per_cycle = 6 # 90% deployment across 6 uncorrelated markets
    avg_expiry_days = 2.5 # Timeframe for fast markets
    cycles_per_month = int(30.44 / avg_expiry_days) # 12 complete turnover cycles a month
    total_cycles = cycles_per_month * months
    
    black_swan_rate = 0.0241 # Empirical P-Measure from the 77k-trade SQLite DB backtest
    
    final_capitals = []
    drawdowns = []
    
    for _ in range(iterations):
        capital = starting_capital
        peak = starting_capital
        max_dd = 0.0
        
        for c in range(total_cycles):
            cycle_profit = 0.0
            
            for t in range(trades_per_cycle):
                trade_size = capital * risk_per_trade
                
                # Simulate Retail 'Yes' bloat between 1% and 15%
                sim_yes = np.random.uniform(0.01, 0.15)
                # Apply 2% slippage cap to entry
                sim_no = min((1.0 - sim_yes) * 1.02, 0.99)
                
                if np.random.rand() < black_swan_rate:
                    # Black swan hit, lost the 15% collateral
                    cycle_profit -= trade_size
                else:
                    # 'No' hit, collect payout
                    payout = trade_size / sim_no
                    cycle_profit += (payout - trade_size)
                    
            capital += cycle_profit
            
            if capital > peak:
                peak = capital
            else:
                dd = (peak - capital) / peak
                if dd > max_dd:
                    max_dd = dd
                    
            if capital <= 0:
                capital = 0
                break
                
        final_capitals.append(capital)
        drawdowns.append(max_dd)
        
    avg_final = np.mean(final_capitals)
    median_final = np.median(final_capitals)
    p5 = np.percentile(final_capitals, 5)
    p95 = np.percentile(final_capitals, 95)
    avg_dd = np.mean(drawdowns)
    p95_dd = np.percentile(drawdowns, 95)
    
    roi = (avg_final - starting_capital) / starting_capital
    
    console.print(f"\n[bold cyan]Live Strategy Monte Carlo Simulation ({iterations:,} Runs)[/bold cyan]")
    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Execution Parameters", style="cyan")
    table.add_column("Value", justify="right", style="yellow")
    
    table.add_row("Timeframe Simulated", f"{months} Month(s)")
    table.add_row("Total Cycles (Turnovers)", f"{total_cycles} Cycles")
    table.add_row("Trades per Cycle", f"{trades_per_cycle} Uncorrelated Markets")
    table.add_row("Max Risk per Trade", f"{risk_per_trade*100:.1f}% of Bankroll")
    table.add_row("L2 Slippage Penalty", "2.0%")
    table.add_row("Empirical Black Swan Hit Rate", f"{black_swan_rate*100:.2f}%")
    
    console.print(table)
    
    res = Table(show_header=True, header_style="bold green")
    res.add_column("Expected Monthly Returns", style="cyan")
    res.add_column("Result", justify="right", style="bold white")
    
    res.add_row("Average Ending Bankroll", f"${avg_final:,.2f}")
    res.add_row("Median Ending Bankroll", f"${median_final:,.2f}")
    res.add_row("Expected Average Monthly Yield", f"[bold green]{((avg_final/starting_capital)**(1/months) - 1)*100:.2f}%[/bold green]")
    res.add_row("Worst Case (5th Percentile)", f"${p5:,.2f}")
    res.add_row("Best Case (95th Percentile)", f"${p95:,.2f}")
    res.add_row("Average Max Drawdown", f"[bold red]{avg_dd*100:.2f}%[/bold red]")
    res.add_row("Extreme Drawdown (95th Percentile)", f"[bold red]{p95_dd*100:.2f}%[/bold red]")
    
    console.print(res)

if __name__ == "__main__":
    run_monte_carlo(1000.0, 1, 100000)
