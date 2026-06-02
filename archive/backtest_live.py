"""
POLY-ALPHA LIVE BACKTEST — Shin-Debiased Edge
Scans ALL active markets, applies filters, uses Shin-debiased true probabilities
to simulate outcomes. 300,000 Monte Carlo trials.
"""

import json
import urllib.request
import ssl
import time
import numpy as np
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def shin_debiasing(p_market, question=""):
    q_lower = question.lower()
    if any(
        w in q_lower
        for w in ["bitcoin", "ethereum", "solana", "xrp", "crypto", "btc", "eth"]
    ):
        gamma = 1.30
    elif any(
        w in q_lower
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
        gamma = 1.20
    elif any(w in q_lower for w in ["temperature", "weather", "snow", "rain"]):
        gamma = 1.15
    elif any(w in q_lower for w in ["trump", "election", "cabinet", "strike", "war"]):
        gamma = 1.05
    else:
        gamma = 1.18
    return (p_market**gamma) / ((p_market**gamma) + ((1.0 - p_market) ** gamma))


def fetch_active_markets():
    console.print("[cyan]Fetching active markets from Gamma API...[/cyan]")
    all_markets = []
    offset = 0
    total = 0

    while True:
        url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit=1000&offset={offset}"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
                events = json.loads(resp.read().decode())
                if not events:
                    break
                for event in events:
                    for m in event.get("markets", []):
                        all_markets.append(m)
                total += len(events)
                console.print(f"  {total:,} events ({len(all_markets):,} markets)...")
                offset += 1000
                time.sleep(0.3)
        except Exception as e:
            console.print(f"[yellow]Fetch error: {e}[/yellow]")
            break

    return all_markets


def run_backtest(starting_capital=10000.0):
    console.print(
        Panel(
            "[bold green]POLY-ALPHA LIVE BACKTEST[/bold green]\n"
            "[white]Scanning ALL active markets. Applying ALL strategy filters.[/white]\n"
            "[white]Using Shin-debiased true probabilities for outcome simulation.[/white]\n"
            "[white]300,000 Monte Carlo trials.[/white]"
        )
    )

    all_markets = fetch_active_markets()
    console.print(f"\n[green]Total: {len(all_markets):,} markets[/green]")

    # Filter
    console.print("\n[cyan]Applying strategy filters...[/cyan]")
    candidates = []
    rejected = {}
    long_term_patterns = [
        "win the",
        "finish in",
        "relegated",
        "champion",
        "championship",
        "finals",
        "premier league",
        "la liga",
        "serie a",
        "bundesliga",
    ]

    for m in all_markets:
        try:
            question = m.get("question", "")
            q_lower = question.lower()

            if any(p in q_lower for p in long_term_patterns):
                rejected["long_term"] = rejected.get("long_term", 0) + 1
                continue

            tokens = json.loads(m.get("outcomePrices", "[]"))
            if len(tokens) < 2:
                rejected["no_prices"] = rejected.get("no_prices", 0) + 1
                continue

            outcomes = json.loads(m.get("outcomes", "[]"))
            if len(outcomes) != 2:
                rejected["not_binary"] = rejected.get("not_binary", 0) + 1
                continue

            yes_price = float(tokens[0])
            no_price = 1.0 - yes_price

            if yes_price < 0.05 or yes_price > 0.15:
                rejected["outside_bracket"] = rejected.get("outside_bracket", 0) + 1
                continue

            volume = float(m.get("volume", 0))
            liquidity = float(m.get("liquidity", volume * 0.05))
            if liquidity < 250:
                rejected["low_liq"] = rejected.get("low_liq", 0) + 1
                continue

            vol_24h = float(m.get("volume24hr", 0) or 0)
            if liquidity > 0 and (vol_24h / liquidity) > 15.0:
                rejected["hft_spike"] = rejected.get("hft_spike", 0) + 1
                continue

            shin_no = shin_debiasing(no_price, question)
            edge = shin_no - no_price
            if edge < 0.03:
                rejected["low_edge"] = rejected.get("low_edge", 0) + 1
                continue

            candidates.append(
                {
                    "id": m.get("id", ""),
                    "question": question,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "liquidity": liquidity,
                    "shin_edge": edge,
                    "shin_no": shin_no,
                    "volume": volume,
                }
            )
        except Exception:
            rejected["parse_error"] = rejected.get("parse_error", 0) + 1

    for reason, count in sorted(rejected.items(), key=lambda x: -x[1]):
        console.print(f"  [yellow]{reason}:[/yellow] {count:,}")
    console.print(f"  [green]PASSED ALL FILTERS:[/green] {len(candidates):,}")

    if not candidates:
        console.print("[red]No markets passed filters.[/red]")
        return

    # Dedup
    diversified = []
    for m in candidates:
        dup = False
        for e in diversified:
            s1 = set(m["question"].lower().split())
            s2 = set(e["question"].lower().split())
            u = s1.union(s2)
            if u and len(s1.intersection(s2)) / len(u) > 0.3:
                dup = True
                break
        if not dup:
            diversified.append(m)

    console.print(f"  [green]After dedup: {len(diversified):,}[/green]")

    diversified.sort(key=lambda m: m["shin_edge"] * m["liquidity"], reverse=True)

    # Show top markets
    console.print(f"\n[cyan]Top markets that passed:[/cyan]")
    for m in diversified[:15]:
        console.print(
            f"  Yes={m['yes_price'] * 100:.1f}¢ | No={m['no_price'] * 100:.1f}¢ | Edge={m['shin_edge'] * 100:.1f}¢ | Liq=${m['liquidity']:,.0f} | {m['question'][:60]}"
        )

    # 300,000 trial Monte Carlo
    n_markets = len(diversified)
    n_trials = 300000
    position_size_pct = 0.02
    max_positions = min(n_markets, 50)

    console.print(
        f"\n[cyan]Running {n_trials:,} Monte Carlo trials ({max_positions} positions each)...[/cyan]"
    )

    np.random.seed(42)
    win_probs = np.array([m["shin_no"] for m in diversified[:max_positions]])
    no_prices = np.array([m["no_price"] for m in diversified[:max_positions]])

    wins = np.random.rand(n_trials, max_positions) < win_probs

    bankrolls = np.full(n_trials, starting_capital)
    for pos_idx in range(max_positions):
        size = bankrolls * position_size_pct
        payout_if_win = size / no_prices[pos_idx]
        payout = np.where(wins[:, pos_idx], payout_if_win, 0.0)
        bankrolls = bankrolls - size + payout

    # Stats
    median = np.median(bankrolls)
    mean = np.mean(bankrolls)
    p1 = np.percentile(bankrolls, 1)
    p5 = np.percentile(bankrolls, 5)
    p25 = np.percentile(bankrolls, 25)
    p75 = np.percentile(bankrolls, 75)
    p95 = np.percentile(bankrolls, 95)
    p99 = np.percentile(bankrolls, 99)
    min_val = np.min(bankrolls)
    max_val = np.max(bankrolls)
    profitable_pct = np.mean(bankrolls > starting_capital) * 100

    wins_per_trial = wins.sum(axis=1)
    avg_wins = np.mean(wins_per_trial)
    avg_losses = max_positions - avg_wins

    console.print(Panel("[bold cyan]BACKTEST RESULTS[/bold cyan]"))
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right", style="yellow")
    t.add_row("Starting Capital", f"${starting_capital:,.2f}")
    t.add_row("Markets in Pool", f"{n_markets}")
    t.add_row("Positions Per Trial", f"{max_positions}")
    t.add_row("Position Size", f"{position_size_pct * 100:.0f}% of bankroll")
    t.add_row("Trials", f"{n_trials:,}")
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
    t.add_row("Best Case", f"${max_val:,.2f}")
    t.add_row("Worst Case", f"${min_val:,.2f}")
    t.add_row("", "")
    t.add_row("Probability of Profit", f"{profitable_pct:.1f}%")
    t.add_row("Avg Wins Per Trial", f"{avg_wins:.1f}")
    t.add_row("Avg Losses Per Trial", f"{avg_losses:.1f}")
    t.add_row("Avg Win Rate", f"{avg_wins / max_positions * 100:.1f}%")
    console.print(t)

    # Distribution
    console.print(f"\n[bold]Outcome Distribution:[/bold]")
    bins = [
        (0, 0.5, "Wiped Out"),
        (0.5, 0.75, "Lost 25-50%"),
        (0.75, 0.9, "Lost 10-25%"),
        (0.9, 1.0, "Lost 0-10%"),
        (1.0, 1.05, "Flat to +5%"),
        (1.05, 1.15, "+5% to +15%"),
        (1.15, 1.3, "+15% to +30%"),
        (1.3, 1.5, "+30% to +50%"),
        (1.5, 10.0, "+50%+"),
    ]
    for lo_x, hi_x, label in bins:
        lo = starting_capital * lo_x
        hi = starting_capital * hi_x
        count = int(np.sum((bankrolls >= lo) & (bankrolls < hi)))
        pct = count / n_trials * 100
        bar = "#" * max(0, int(pct / 0.5))
        console.print(
            f"  {label:18s} ({lo_x * 100:.0f}%-{hi_x * 100:.0f}x): {pct:5.1f}% {count:6d} {bar}"
        )

    # Monthly compounding
    per_cycle_median = median / starting_capital
    per_cycle_mean = mean / starting_capital
    per_cycle_p5 = p5 / starting_capital
    per_cycle_p95 = p95 / starting_capital
    per_cycle_p1 = p1 / starting_capital

    console.print(f"\n[bold]Monthly Compounding Projection (20 cycles/month):[/bold]")
    console.print(f"  Per-cycle median: {per_cycle_median:.4f}x")
    console.print(f"  Per-cycle mean:   {per_cycle_mean:.4f}x")
    console.print(f"  Per-cycle 5th:    {per_cycle_p5:.4f}x")

    mt = Table(show_header=True, header_style="bold green")
    mt.add_column("Months", style="cyan")
    mt.add_column("Cycles", style="yellow")
    mt.add_column("1st %ile", justify="right", style="red")
    mt.add_column("5th %ile", justify="right", style="red")
    mt.add_column("Median", justify="right", style="green")
    mt.add_column("Mean", justify="right", style="green")
    mt.add_column("95th %ile", justify="right", style="green")

    for mo in [1, 2, 3, 6, 12]:
        c = mo * 20
        c1 = starting_capital * max(0, per_cycle_p1**c)
        c5 = starting_capital * max(0, per_cycle_p5**c)
        c50 = starting_capital * (per_cycle_median**c)
        cm = starting_capital * (per_cycle_mean**c)
        c95 = starting_capital * (per_cycle_p95**c)
        mt.add_row(
            str(mo),
            str(c),
            f"${c1:,.0f}",
            f"${c5:,.0f}",
            f"${c50:,.0f}",
            f"${cm:,.0f}",
            f"${c95:,.0f}",
        )
    console.print(mt)


if __name__ == "__main__":
    run_backtest(starting_capital=10000.0)
