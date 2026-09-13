"""Synthetic Monte Carlo over hardcoded win-rate assumptions (not a backtest)."""

from __future__ import annotations

import numpy as np
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

# Win rates by lifecycle stage and No-price bucket (from paper Table 3)
EMPIRICAL_DATA: dict[str, dict[float, tuple[float, float]]] = {
    "early": {
        0.80: (0.86, +6.0),
        0.85: (0.89, +4.0),
        0.90: (0.93, +3.0),
        0.95: (0.97, +2.0),
    },
    "middle": {
        0.80: (0.80, 0.0),
        0.85: (0.85, 0.0),
        0.90: (0.90, 0.0),
        0.95: (0.95, 0.0),
    },
    "late": {
        0.80: (0.78, -2.0),
        0.85: (0.83, -2.0),
        0.90: (0.88, -2.0),
        0.95: (0.94, -1.0),
    },
}

CATEGORY_ADJ: dict[str, float] = {
    "politics": +0.015,
    "crypto": +0.020,
    "sports": -0.005,
    "weather": +0.010,
    "other": +0.005,
}

LIFECYCLE_DIST: dict[str, float] = {"early": 0.15, "middle": 0.70, "late": 0.15}
PRICE_DIST: dict[float, float] = {0.80: 0.05, 0.85: 0.15, 0.90: 0.45, 0.95: 0.35}
CATEGORY_DIST: dict[str, float] = {
    "sports": 0.35,
    "politics": 0.30,
    "crypto": 0.15,
    "weather": 0.05,
    "other": 0.15,
}


def get_win_rate(
    no_price: float, lifecycle: str = "middle", category: str = "other"
) -> tuple[float, float]:
    """Look up empirical win rate for a given No-price and lifecycle stage."""
    bucket = EMPIRICAL_DATA.get(lifecycle, EMPIRICAL_DATA["middle"])
    nearest = min(bucket.keys(), key=lambda p: abs(p - no_price))
    base_rate, edge = bucket[nearest]
    adj = CATEGORY_ADJ.get(category, 0)
    return max(0.5, min(0.999, base_rate + adj)), edge


def run(
    starting_capital: float = 10_000.0,
    trades_per_cycle: int = 50,
    n_trials: int = 300_000,
    position_size_pct: float = 0.02,
    seed: int = 42,
) -> dict[str, float | str]:
    """Run a synthetic Monte Carlo over hardcoded win-rate assumptions.

    This is not a backtest of observed markets: outcomes are generated and the win
    rates are hand-set in this module. Returns a dict with median, mean, p1, p5, p95,
    p99, profit_probability, plus a synthetic marker and caveat.
    """
    console.print(
        Panel(
            f"[bold red]SYNTHETIC Monte Carlo[/bold red]\n"
            f"[white]hardcoded win rates + generated outcomes; not observed data, "
            f"not a backtest[/white]\n"
            f"[white]{trades_per_cycle} trades/cycle | {n_trials:,} simulations[/white]"
        )
    )

    rng = np.random.default_rng(seed)

    categories = list(CATEGORY_DIST.keys())
    cat_w = list(CATEGORY_DIST.values())
    prices = list(PRICE_DIST.keys())
    price_w = list(PRICE_DIST.values())
    lifecycles = list(LIFECYCLE_DIST.keys())
    life_w = list(LIFECYCLE_DIST.values())

    lifecycle_draws = rng.choice(lifecycles, size=(n_trials, trades_per_cycle), p=life_w)
    price_draws = rng.choice(prices, size=(n_trials, trades_per_cycle), p=price_w)
    _ = rng.choice(categories, size=(n_trials, trades_per_cycle), p=cat_w)
    outcome_draws = rng.random((n_trials, trades_per_cycle))

    win_rates = np.zeros((n_trials, trades_per_cycle))
    no_prices_arr = np.zeros((n_trials, trades_per_cycle))

    for lc in lifecycles:
        for p in prices:
            mask = (lifecycle_draws == lc) & (price_draws == p)
            wr, _ = get_win_rate(p, lc)
            win_rates[mask] = wr
            no_prices_arr[mask] = p

    bankrolls = np.full(n_trials, starting_capital)
    for t in range(trades_per_cycle):
        size = bankrolls * position_size_pct
        no_p = no_prices_arr[:, t]
        shares = size / no_p
        bankrolls = bankrolls - size + np.where(outcome_draws[:, t] < win_rates[:, t], shares, 0.0)

    median = float(np.median(bankrolls))
    mean = float(np.mean(bankrolls))
    p1 = float(np.percentile(bankrolls, 1))
    p5 = float(np.percentile(bankrolls, 5))
    p25 = float(np.percentile(bankrolls, 25))
    p75 = float(np.percentile(bankrolls, 75))
    p95 = float(np.percentile(bankrolls, 95))
    p99 = float(np.percentile(bankrolls, 99))
    profitable = float(np.mean(bankrolls > starting_capital) * 100)

    tbl = Table(show_header=True, header_style="bold magenta")
    tbl.add_column("Metric", style="cyan")
    tbl.add_column("Value", justify="right", style="yellow")
    tbl.add_row("Trades Per Cycle", f"{trades_per_cycle}")
    tbl.add_row("Simulations", f"{n_trials:,}")
    tbl.add_row("Position Size", f"{position_size_pct * 100:.1f}%")
    tbl.add_row("", "")
    tbl.add_row("1st Percentile", f"${p1:,.2f} ({(p1 / starting_capital - 1) * 100:+.1f}%)")
    tbl.add_row("5th Percentile", f"${p5:,.2f} ({(p5 / starting_capital - 1) * 100:+.1f}%)")
    tbl.add_row("25th Percentile", f"${p25:,.2f} ({(p25 / starting_capital - 1) * 100:+.1f}%)")
    tbl.add_row(
        "MEDIAN",
        f"[bold green]${median:,.2f} ({(median / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    tbl.add_row(
        "MEAN",
        f"[bold green]${mean:,.2f} ({(mean / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    tbl.add_row("75th Percentile", f"${p75:,.2f} ({(p75 / starting_capital - 1) * 100:+.1f}%)")
    tbl.add_row("95th Percentile", f"${p95:,.2f} ({(p95 / starting_capital - 1) * 100:+.1f}%)")
    tbl.add_row("99th Percentile", f"${p99:,.2f} ({(p99 / starting_capital - 1) * 100:+.1f}%)")
    tbl.add_row("", "")
    tbl.add_row("Probability of Profit", f"{profitable:.1f}%")
    console.print(tbl)

    return {
        "median": median / starting_capital,
        "mean": mean / starting_capital,
        "p1": p1 / starting_capital,
        "p5": p5 / starting_capital,
        "p95": p95 / starting_capital,
        "p99": p99 / starting_capital,
        "profit_probability": profitable,
        "synthetic": 1.0,
        "caveat": "Synthetic Monte Carlo over assumed win rates; not a backtest or forecast.",
    }


if __name__ == "__main__":
    run()
