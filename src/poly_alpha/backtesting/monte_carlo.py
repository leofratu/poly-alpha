"""Monte Carlo backtesting engine against historical Polymarket resolutions."""

from __future__ import annotations

from typing import Any

import numpy as np
import requests
from rich.console import Console
from rich.table import Table

console = Console()

GAMMA_API = "https://gamma-api.polymarket.com"


def fetch_resolved_markets(limit: int = 1000) -> list[dict[str, Any]]:
    """Fetch closed events from the Gamma API."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"closed": "true", "limit": str(limit)},
            headers={"User-Agent": "PolyAlpha/1.0"},
            timeout=30,
        )
        resp.raise_for_status()
        result: list[dict[str, Any]] = resp.json()
        return result
    except requests.RequestException as e:
        console.print(f"[red]Failed to fetch historical markets: {e}[/red]")
        return []


def run(
    iterations: int = 10_000,
    capital_per_trade: float = 10_000.0,
    trades_per_sample: int = 10,
) -> dict[str, float | str]:
    """Run Monte Carlo simulation over historical market data.

    Returns dict with avg_roi, avg_apy, p5, p95, win_rate.
    """
    banner = (
        "[bold red]SYNTHETIC Monte Carlo — resolutions and returns are fabricated, "
        "not observed. This is not a backtest.[/bold red]"
    )
    console.print(banner)

    events = fetch_resolved_markets()
    historical_trades: list[dict[str, Any]] = []

    for event in events:
        for m in event.get("markets", []):
            simulated_entry_yes = np.random.uniform(0.05, 0.35)
            simulated_entry_no = 1.0 - simulated_entry_yes
            no_price_slippage = min(simulated_entry_no * 1.02, 0.99)

            historical_trades.append(
                {
                    "question": m.get("question", ""),
                    "resolution_yes": np.random.rand() < 0.10,
                    "no_price": no_price_slippage,
                    "yes_entry": simulated_entry_yes,
                }
            )

    if not historical_trades:
        console.print("[red]No historical data available.[/red]")
        return {}

    console.print(f"Generated {len(historical_trades)} synthetic market samples (random resolutions).")

    mc_rois = np.zeros(iterations)

    for i in range(iterations):
        indices = np.random.randint(0, len(historical_trades), size=trades_per_sample)
        total_capital = 0.0
        total_profit = 0.0

        for idx in indices:
            trade = historical_trades[idx]
            pm_capital = capital_per_trade * 0.50
            total_capital += capital_per_trade
            pm_shares = pm_capital / trade["no_price"]

            true_prob = trade["yes_entry"] * 0.30
            hedge_cost = true_prob * 1000 * (pm_shares / 1000) * 1.20
            basis_capital = (capital_per_trade * 0.50) - hedge_cost
            days_to_expiry = np.random.randint(7, 45)
            basis_profit = basis_capital * 0.12 * (days_to_expiry / 365.0)

            trade_gross = pm_shares * 1.0
            net = trade_gross - pm_capital - hedge_cost + basis_profit
            total_profit += net

        mc_rois[i] = total_profit / total_capital if total_capital > 0 else 0.0

    avg_roi = float(np.mean(mc_rois))
    avg_apy = avg_roi * (365 / 26)
    p5 = float(np.percentile(mc_rois, 5))
    p95 = float(np.percentile(mc_rois, 95))
    win_rate = float(np.sum(mc_rois > 0) / iterations)

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Metric", style="cyan")
    table.add_column("Result", justify="right", style="yellow")
    table.add_row("Iterations", f"{iterations:,}")
    table.add_row("Synthetic Markets", f"{len(historical_trades)}")
    table.add_row("Win Rate", f"{win_rate * 100:.2f}%")
    table.add_row("Average ROI (per cycle)", f"{avg_roi * 100:.2f}%")
    table.add_row(
        "Annualized (synthetic, not a forecast)",
        f"[bold yellow]{avg_apy * 100:.2f}%[/bold yellow]",
    )
    table.add_row("5th Percentile", f"{p5 * 100:.2f}%")
    table.add_row("95th Percentile", f"{p95 * 100:.2f}%")
    console.print(table)

    return {
        "avg_roi": avg_roi,
        "avg_apy": avg_apy,
        "p5": p5,
        "p95": p95,
        "win_rate": win_rate,
        "synthetic": 1.0,
        "caveat": "Synthetic Monte Carlo; fabricated resolutions and returns, not a forecast.",
    }


if __name__ == "__main__":
    run()
