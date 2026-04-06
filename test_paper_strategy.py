"""
SSRN PAPER-BASED STRATEGY TEST
Based on Reichenbach & Walther (2025) — 124 million trades.

KEY FINDINGS:
1. Early lifecycle (first 20%): Yes/default overpriced, No UNDERPRICED by 3-5pp
2. Middle lifecycle (20-90%): EFFICIENT — no systematic mispricing
3. Late lifecycle (final 10%): S-shaped pattern — NEGATIVE EV

STRATEGY: Only enter EARLY, exit BEFORE resolution.
"""

import json
import numpy as np
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()


def shin_debiasing(p, cat="other"):
    gamma = {
        "politics": 1.05,
        "crypto": 1.30,
        "weather": 1.15,
        "esports": 1.18,
        "other": 1.18,
        "sports": 1.20,
    }.get(cat, 1.18)
    return (p**gamma) / ((p**gamma) + ((1.0 - p) ** gamma))


def classify_category(q):
    ql = q.lower()
    if any(
        w in ql
        for w in [
            "trump",
            "election",
            "cabinet",
            "strike",
            "war",
            "congress",
            "senate",
            "president",
            "prime minister",
            "governor",
            "mayor",
            "parliament",
            "vote",
            "referendum",
            "impeach",
            "sanction",
            "tariff",
            "policy",
            "recognize",
            "leader of",
            "out as",
            "resign",
            "coup",
            "military",
            "invade",
            "conflict",
            "ceasefire",
            "treaty",
            "diplomatic",
            "strait of hormuz",
            "iran",
            "israel",
            "russia",
            "ukraine",
            "china",
            "taiwan",
            "venezuela",
            "macron",
            "putin",
            "white house",
            "balance of power",
            "fidesz",
        ]
    ):
        return "politics"
    if any(
        w in ql
        for w in [
            "bitcoin",
            "ethereum",
            "solana",
            "xrp",
            "crypto",
            "btc",
            "eth",
            "market cap",
            "dip to",
            "reach $",
            "ipo",
            "kraken",
            "microstrategy",
            "sec",
            "etf",
            "blockchain",
            "defi",
            "token",
            "fdv",
            "bnb",
            "hyperliquid",
            "palantir",
        ]
    ):
        return "crypto"
    if any(
        w in ql
        for w in [
            "temperature",
            "weather",
            "snow",
            "rain",
            "hurricane",
            "highest temperature",
            "lowest temperature",
        ]
    ):
        return "weather"
    if any(
        w in ql
        for w in [
            "lol",
            "valorant",
            "league of legends",
            "counter-strike",
            "csgo",
            "dota",
            "overwatch",
            "esports",
            "game 2",
            "game 3",
            "map ",
            "first blood",
            "total kills",
            "honor of kings",
            "quadra",
            "penta",
        ]
    ):
        return "esports"
    if any(
        w in ql
        for w in [
            "win on",
            "vs.",
            "o/u",
            "ncaa",
            "fc ",
            "championship",
            "premier",
            "la liga",
            "serie a",
            "bundesliga",
        ]
    ):
        return "sports"
    return "other"


def run_paper_based_test():
    console.print(
        Panel(
            "[bold green]SSRN PAPER-BASED STRATEGY TEST[/bold green]\n"
            "[white]Reichenbach & Walther (2025) — 124 million trades on Polymarket.[/white]\n"
            "[white]Testing: Enter EARLY (first 20%), exit BEFORE resolution.[/white]"
        )
    )

    # Load the 1,136 tracked markets
    with open("/tmp/all_target_markets.json", "r") as fp:
        all_targets = json.load(fp)

    console.print(f"[green]Total markets with Yes 5-15¢: {len(all_targets):,}[/green]")

    # Classify by lifecycle stage
    # Early = first 20% of market duration
    # Middle = 20-90%
    # Late = final 10%
    # We don't know exact lifecycle stage from a snapshot, but we can estimate
    # by comparing the market's creation date to its expiry date

    early = []
    middle = []
    late = []
    unknown = []

    for m in all_targets:
        days = m.get("days")
        if days is None:
            unknown.append(m)
        elif days <= 1.0:
            # If expiring within 1 day, likely late lifecycle
            late.append(m)
        elif days <= 3.0:
            # Could be middle or late
            middle.append(m)
        else:
            # More than 3 days to expiry — likely early or middle
            early.append(m)

    console.print(f"\n[bold]Lifecycle stage estimate:[/bold]")
    console.print(f"  Early/Middle (>3 days): {len(early):,}")
    console.print(f"  Middle (1-3 days): {len(middle):,}")
    console.print(f"  Late (<1 day): {len(late):,}")
    console.print(f"  Unknown: {len(unknown):,}")

    # Calculate expected value for each scenario based on paper's findings
    console.print(f"\n[bold cyan]EXPECTED VALUE PER TRADE (paper-based):[/bold cyan]")

    # Paper findings:
    # Early lifecycle: No underpriced by 3-5pp → true win rate = no_price + 0.03 to 0.05
    # Middle lifecycle: efficient → true win rate = no_price
    # Late lifecycle: S-shaped → true win rate = no_price - 0.02

    scenarios = [
        ("EARLY (first 20%)", early, 0.03, 0.05),
        ("MIDDLE (20-90%)", middle, 0.0, 0.0),
        ("LATE (final 10%)", late, -0.02, -0.02),
    ]

    position_size = 20.0

    total_ev_low = 0.0
    total_ev_high = 0.0
    total_trades = 0

    for name, markets, edge_low, edge_high in scenarios:
        if not markets:
            continue

        scenario_ev_low = 0.0
        scenario_ev_high = 0.0
        wins_low = 0
        wins_high = 0

        for m in markets:
            no_entry = m["no_price"]
            cat = classify_category(m["question"])
            shin_no = shin_debiasing(no_entry, cat)

            # Paper-based true win rate
            # Conservative: market price + edge
            true_wr_low = no_entry + edge_low
            true_wr_high = no_entry + edge_high

            # Shin-adjusted true win rate (more aggressive)
            shin_wr_low = shin_no + edge_low
            shin_wr_high = shin_no + edge_high

            shares = position_size / no_entry
            win_profit = shares - position_size
            loss_amount = -position_size

            ev_low = true_wr_low * win_profit + (1 - true_wr_low) * loss_amount
            ev_high = true_wr_high * win_profit + (1 - true_wr_high) * loss_amount

            shin_ev_low = shin_wr_low * win_profit + (1 - shin_wr_low) * loss_amount
            shin_ev_high = shin_wr_high * win_profit + (1 - shin_wr_high) * loss_amount

            scenario_ev_low += ev_low
            scenario_ev_high += ev_high
            total_ev_low += ev_low
            total_ev_high += ev_high

            if ev_low > 0:
                wins_low += 1
            if ev_high > 0:
                wins_high += 1

        total_trades += len(markets)
        avg_ev_low = scenario_ev_low / len(markets)
        avg_ev_high = scenario_ev_high / len(markets)

        console.print(f"\n  {name} ({len(markets):,} markets):")
        console.print(
            f"    Paper-based EV: ${avg_ev_low:+.2f} to ${avg_ev_high:+.2f} per trade"
        )
        console.print(
            f"    Trades with +EV: {wins_low}/{len(markets)} to {wins_high}/{len(markets)}"
        )

        # Monthly projection
        monthly_trades = len(markets)  # assuming one cycle
        monthly_pnl_low = monthly_trades * avg_ev_low
        monthly_pnl_high = monthly_trades * avg_ev_high
        console.print(
            f"    Monthly PnL (1 cycle): ${monthly_pnl_low:+,.0f} to ${monthly_pnl_high:+,.0f}"
        )

    # Overall summary
    console.print(f"\n[bold cyan]=== OVERALL SUMMARY ===[/bold cyan]")

    avg_ev_low = total_ev_low / total_trades if total_trades > 0 else 0
    avg_ev_high = total_ev_high / total_trades if total_trades > 0 else 0

    console.print(f"  Total markets: {total_trades:,}")
    console.print(f"  Average EV per trade: ${avg_ev_low:+.2f} to ${avg_ev_high:+.2f}")
    console.print(
        f"  Total PnL per cycle (all markets): ${total_ev_low:+,.0f} to ${total_ev_high:+,.0f}"
    )

    # Monthly compounding (20 cycles)
    starting = 1000.0
    pnl_per_cycle_low = total_ev_low
    pnl_per_cycle_high = total_ev_high

    # But we can only deploy 60% of capital per cycle
    max_deploy = starting * 0.60
    positions_per_cycle = int(max_deploy / position_size)

    # Scale EV to actual positions
    ev_per_position_low = total_ev_low / total_trades if total_trades > 0 else 0
    ev_per_position_high = total_ev_high / total_trades if total_trades > 0 else 0

    cycle_pnl_low = positions_per_cycle * ev_per_position_low
    cycle_pnl_high = positions_per_cycle * ev_per_position_high

    cycle_return_low = cycle_pnl_low / starting
    cycle_return_high = cycle_pnl_high / starting

    console.print(
        f"\n[bold]Monthly compounding ({positions_per_cycle} positions/cycle, 20 cycles/month):[/bold]"
    )
    console.print(
        f"  Per-cycle return: {cycle_return_low * 100:+.1f}% to {cycle_return_high * 100:+.1f}%"
    )

    mt = Table(show_header=True, header_style="bold green")
    mt.add_column("Months", style="cyan")
    mt.add_column("Cycles", style="yellow")
    mt.add_column("Conservative", justify="right", style="green")
    mt.add_column("Optimistic", justify="right", style="green")

    for mo in [1, 2, 3, 6]:
        c = mo * 20
        conservative = starting * ((1 + cycle_return_low) ** c)
        optimistic = starting * ((1 + cycle_return_high) ** c)
        mt.add_row(str(mo), str(c), f"${conservative:,.0f}", f"${optimistic:,.0f}")
    console.print(mt)

    # The key insight
    console.print(f"\n[bold red]THE REALITY:[/bold red]")
    console.print(f"  The paper finds markets are EFFICIENT overall.")
    console.print(f"  The ONLY edge is entering EARLY in lifecycle.")
    console.print(f"  Early lifecycle edge: +3-5pp on No prices.")
    console.print(
        f"  This translates to ${ev_per_position_low:+.2f}-${ev_per_position_high:+.2f} per trade."
    )
    console.print(f"  With {positions_per_cycle} positions/cycle × 20 cycles/month:")
    console.print(
        f"  Expected monthly profit: ${positions_per_cycle * ev_per_position_low * 20:+,.0f} to ${positions_per_cycle * ev_per_position_high * 20:+,.0f}"
    )
    console.print(f"  From ${starting:,.0f} starting capital.")


if __name__ == "__main__":
    run_paper_based_test()
