"""
EMPIRICAL BACKTEST — Reichenbach & Walther (2025)
Realistic trade counts per cycle, 300,000 trials.
"""

import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

EMPIRICAL_DATA = {
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

CATEGORY_ADJ = {
    "politics": +0.015,
    "crypto": +0.020,
    "sports": -0.005,
    "weather": +0.010,
    "other": +0.005,
}

LIFECYCLE_DIST = {"early": 0.15, "middle": 0.70, "late": 0.15}
PRICE_DIST = {0.80: 0.05, 0.85: 0.15, 0.90: 0.45, 0.95: 0.35}
CATEGORY_DIST = {
    "sports": 0.35,
    "politics": 0.30,
    "crypto": 0.15,
    "weather": 0.05,
    "other": 0.15,
}


def get_win_rate(no_price, lifecycle="middle", category="other"):
    bucket = EMPIRICAL_DATA.get(lifecycle, EMPIRICAL_DATA["middle"])
    nearest = min(bucket.keys(), key=lambda p: abs(p - no_price))
    base_rate, edge = bucket[nearest]
    adj = CATEGORY_ADJ.get(category, 0)
    return max(0.5, min(0.999, base_rate + adj)), edge


def run_backtest(starting_capital=10000.0, trades_per_cycle=50, n_cycles=1):
    console.print(
        Panel(
            "[bold green]EMPIRICAL BACKTEST[/bold green]\n"
            f"[white]{trades_per_cycle} trades/cycle × {n_cycles} cycles = {trades_per_cycle * n_cycles:,} total trades[/white]\n"
            f"[white]300,000 Monte Carlo simulations[/white]"
        )
    )

    np.random.seed(42)
    n_trials = 300000

    categories = list(CATEGORY_DIST.keys())
    cat_w = list(CATEGORY_DIST.values())
    prices = list(PRICE_DIST.keys())
    price_w = list(PRICE_DIST.values())
    lifecycles = list(LIFECYCLE_DIST.keys())
    life_w = list(LIFECYCLE_DIST.values())

    # Generate all random draws at once
    lifecycle_draws = np.random.choice(
        lifecycles, size=(n_trials, trades_per_cycle), p=life_w
    )
    price_draws = np.random.choice(prices, size=(n_trials, trades_per_cycle), p=price_w)
    category_draws = np.random.choice(
        categories, size=(n_trials, trades_per_cycle), p=cat_w
    )
    outcome_draws = np.random.rand(n_trials, trades_per_cycle)

    # Compute win rates for every trade
    win_rates = np.zeros((n_trials, trades_per_cycle))
    no_prices_arr = np.zeros((n_trials, trades_per_cycle))

    for i, lc in enumerate(lifecycles):
        for j, p in enumerate(prices):
            mask = (lifecycle_draws == lc) & (price_draws == p)
            wr, _ = get_win_rate(p, lc)
            win_rates[mask] = wr
            no_prices_arr[mask] = p

    # Simulate
    bankrolls = np.full(n_trials, starting_capital)
    for t in range(trades_per_cycle):
        size = bankrolls * 0.02
        no_p = no_prices_arr[:, t]
        shares = size / no_p
        bankrolls = (
            bankrolls
            - size
            + np.where(outcome_draws[:, t] < win_rates[:, t], shares, 0.0)
        )

    # Stats
    median = np.median(bankrolls)
    mean = np.mean(bankrolls)
    p1 = np.percentile(bankrolls, 1)
    p5 = np.percentile(bankrolls, 5)
    p25 = np.percentile(bankrolls, 25)
    p75 = np.percentile(bankrolls, 75)
    p95 = np.percentile(bankrolls, 95)
    p99 = np.percentile(bankrolls, 99)
    profitable = np.mean(bankrolls > starting_capital) * 100

    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right", style="yellow")
    t.add_row("Trades Per Cycle", f"{trades_per_cycle}")
    t.add_row("Cycles", f"{n_cycles}")
    t.add_row("Total Trades", f"{trades_per_cycle * n_cycles:,}")
    t.add_row("Simulations", f"{n_trials:,}")
    t.add_row("", "")
    t.add_row(
        "1st Percentile", f"${p1:,.2f} ({(p1 / starting_capital - 1) * 100:+.1f}%)"
    )
    t.add_row(
        "5th Percentile", f"${p5:,.2f} ({(p5 / starting_capital - 1) * 100:+.1f}%)"
    )
    t.add_row(
        "25th Percentile", f"${p25:,.2f} ({(p25 / starting_capital - 1) * 100:+.1f}%)"
    )
    t.add_row(
        "MEDIAN",
        f"[bold green]${median:,.2f} ({(median / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    t.add_row(
        "MEAN",
        f"[bold green]${mean:,.2f} ({(mean / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    t.add_row(
        "75th Percentile", f"${p75:,.2f} ({(p75 / starting_capital - 1) * 100:+.1f}%)"
    )
    t.add_row(
        "95th Percentile", f"${p95:,.2f} ({(p95 / starting_capital - 1) * 100:+.1f}%)"
    )
    t.add_row(
        "99th Percentile", f"${p99:,.2f} ({(p99 / starting_capital - 1) * 100:+.1f}%)"
    )
    t.add_row("", "")
    t.add_row("Probability of Profit", f"{profitable:.1f}%")
    console.print(t)

    # Distribution
    console.print(f"\n[bold]Distribution:[/bold]")
    bins = [
        (0, 0.5, "Wiped"),
        (0.5, 0.75, "-25-50%"),
        (0.75, 0.9, "-10-25%"),
        (0.9, 1.0, "-0-10%"),
        (1.0, 1.05, "Flat-+5%"),
        (1.05, 1.15, "+5-15%"),
        (1.15, 1.3, "+15-30%"),
        (1.3, 1.5, "+30-50%"),
        (1.5, 10, "+50%+"),
    ]
    for lo_x, hi_x, label in bins:
        lo = starting_capital * lo_x
        hi = starting_capital * hi_x
        count = int(np.sum((bankrolls >= lo) & (bankrolls < hi)))
        pct = count / n_trials * 100
        bar = "#" * max(0, int(pct / 0.5))
        console.print(
            f"  {label:12s} ({lo_x * 100:.0f}%-{hi_x * 100:.0f}x): {pct:5.1f}% {count:6d} {bar}"
        )

    return (
        median / starting_capital,
        mean / starting_capital,
        p5 / starting_capital,
        p95 / starting_capital,
        p1 / starting_capital,
    )


if __name__ == "__main__":
    console.print(
        "[bold cyan]=== SCENARIO 1: 50 trades, 1 cycle (50 total trades) ===[/bold cyan]"
    )
    m1, mn1, p5_1, p95_1, p1_1 = run_backtest(trades_per_cycle=50, n_cycles=1)

    console.print(
        "\n[bold cyan]=== SCENARIO 2: 50 trades, 20 cycles (1,000 total trades) ===[/bold cyan]"
    )
    # Compound 20 times
    m2 = m1**20
    mn2 = mn1**20
    p5_2 = p5_1**20
    p95_2 = p95_1**20
    p1_2 = p1_1**20

    console.print(f"  Median: ${10000 * m2:,.2f} ({(m2 - 1) * 100:+.1f}%)")
    console.print(f"  Mean:   ${10000 * mn2:,.2f} ({(mn2 - 1) * 100:+.1f}%)")
    console.print(f"  1st %:  ${10000 * p1_2:,.2f} ({(p1_2 - 1) * 100:+.1f}%)")
    console.print(f"  5th %:  ${10000 * p5_2:,.2f} ({(p5_2 - 1) * 100:+.1f}%)")
    console.print(f"  95th %: ${10000 * p95_2:,.2f} ({(p95_2 - 1) * 100:+.1f}%)")

    console.print(
        "\n[bold cyan]=== SCENARIO 3: 50 trades, 60 cycles (3,000 total trades / 3 months) ===[/bold cyan]"
    )
    m3 = m1**60
    mn3 = mn1**60
    p5_3 = p5_1**60
    p95_3 = p95_1**60
    p1_3 = p1_1**60

    console.print(f"  Median: ${10000 * m3:,.2f} ({(m3 - 1) * 100:+.1f}%)")
    console.print(f"  Mean:   ${10000 * mn3:,.2f} ({(mn3 - 1) * 100:+.1f}%)")
    console.print(f"  1st %:  ${10000 * p1_3:,.2f} ({(p1_3 - 1) * 100:+.1f}%)")
    console.print(f"  5th %:  ${10000 * p5_3:,.2f} ({(p5_3 - 1) * 100:+.1f}%)")
    console.print(f"  95th %: ${10000 * p95_3:,.2f} ({(p95_3 - 1) * 100:+.1f}%)")
