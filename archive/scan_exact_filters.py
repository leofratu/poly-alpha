"""
EXACT FILTER SCANNER — Matches ultimate_executor.py 1:1
Scans ALL active Polymarket markets, applies the exact 5 filters,
shows every market that passes, then backtests with empirical data.
"""

import json
import urllib.request
import ssl
import time
import re
import numpy as np
from datetime import datetime, timezone
import dateutil.parser
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE


def fetch_all_active_markets():
    console.print("[cyan]Scanning ALL active Polymarket markets...[/cyan]")
    all_markets = []
    offset = 0
    total_events = 0

    while True:
        url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit=1000&offset={offset}"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/15.0"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
                events = json.loads(resp.read().decode())
                if not events:
                    break
                for event in events:
                    for m in event.get("markets", []):
                        all_markets.append(m)
                total_events += len(events)
                console.print(
                    f"  {total_events:,} events ({len(all_markets):,} markets)..."
                )
                offset += 1000
                time.sleep(0.3)
        except Exception as e:
            console.print(f"[yellow]Fetch error at offset {offset}: {e}[/yellow]")
            break

    return all_markets


def scan_exact_filters(all_markets):
    """Apply the EXACT 5 filters from ultimate_executor.py"""
    console.print(
        "\n[bold cyan]Applying EXACT 5 filters from ultimate_executor.py...[/bold cyan]"
    )

    now = datetime.now(timezone.utc)
    passed = []
    rejected = {
        "expiry": 0,
        "price_bracket": 0,
        "liquidity": 0,
        "long_term_league": 0,
        "date_mismatch": 0,
        "parse_error": 0,
        "not_binary": 0,
        "no_prices": 0,
    }

    months = {
        "january": 1,
        "february": 2,
        "march": 3,
        "april": 4,
        "may": 5,
        "june": 6,
        "july": 7,
        "august": 8,
        "september": 9,
        "october": 10,
        "november": 11,
        "december": 12,
    }

    for m in all_markets:
        try:
            q = m.get("question", "")
            q_lower = q.lower()

            # === FILTER 4: Long-Term League Filter ===
            if re.search(
                r"(win the|finish in|relegated|champion|championship|finals|premier league|la liga|serie a|bundesliga)",
                q_lower,
            ):
                rejected["long_term_league"] += 1
                continue

            # Parse expiry date
            end_date_str = m.get("endDate")
            if not end_date_str:
                rejected["parse_error"] += 1
                continue

            try:
                target_date = dateutil.parser.isoparse(end_date_str).astimezone(
                    timezone.utc
                )
            except Exception:
                rejected["parse_error"] += 1
                continue

            days = (target_date - now).total_seconds() / 86400.0

            # === FILTER 5: Time-Travel Data Error Filter ===
            mismatch = False
            for m_name, m_num in months.items():
                if (
                    m_name in q_lower
                    and abs(target_date.month - m_num) > 2
                    and target_date.year == now.year
                ):
                    mismatch = True
                    break

            years = re.findall(r"202[4-9]", q_lower)
            if years:
                latest_year = max([int(y) for y in years])
                if target_date.year < latest_year:
                    mismatch = True

            if mismatch:
                rejected["date_mismatch"] += 1
                continue

            # === FILTER 2: Capital Velocity (< 24 hours) ===
            if days < 0 or days > 1.0:
                rejected["expiry"] += 1
                continue

            # Parse prices
            tokens = json.loads(m.get("outcomePrices", "[]"))
            if len(tokens) < 2:
                rejected["no_prices"] += 1
                continue

            outcomes = json.loads(m.get("outcomes", "[]"))
            if len(outcomes) != 2:
                rejected["not_binary"] += 1
                continue

            yes_price = float(tokens[0])
            no_price = 1.0 - yes_price

            # === FILTER 1: Probability/Mispricing Bracket (5-15¢ Yes) ===
            if yes_price < 0.05 or yes_price > 0.15:
                rejected["price_bracket"] += 1
                continue

            # === FILTER 3: Liquidity/Slippage Constraint ($250+) ===
            volume = float(m.get("volume", 0))
            liquidity = float(m.get("liquidity", volume * 0.05))
            if liquidity <= 250:
                rejected["liquidity"] += 1
                continue

            # ALL 5 FILTERS PASSED
            passed.append(
                {
                    "id": m.get("id", ""),
                    "question": q,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "liquidity": liquidity,
                    "days": days,
                    "volume": volume,
                }
            )

        except Exception:
            rejected["parse_error"] += 1
            continue

    console.print(f"\n[bold]Rejection Breakdown:[/bold]")
    for reason, count in sorted(rejected.items(), key=lambda x: -x[1]):
        if count > 0:
            console.print(f"  [yellow]{reason}:[/yellow] {count:,}")

    console.print(f"\n[bold green]PASSED ALL 5 FILTERS: {len(passed)}[/bold green]")
    return passed


def backtest_passed_markets(passed_markets, starting_capital=10000.0):
    """Backtest the exact markets that passed using empirical win rates."""
    if not passed_markets:
        console.print("[red]No markets passed filters. Nothing to backtest.[/red]")
        return

    console.print(
        f"\n[bold cyan]Backtesting {len(passed_markets)} markets that passed all 5 filters...[/bold cyan]"
    )

    # Show all passed markets
    console.print(f"\n[bold]Markets that passed:[/bold]")
    t = Table(show_header=True, header_style="bold green")
    t.add_column("#", style="cyan")
    t.add_column("Question", style="white")
    t.add_column("Yes", justify="right", style="red")
    t.add_column("No", justify="right", style="green")
    t.add_column("Liquidity", justify="right", style="yellow")
    t.add_column("Days", justify="right", style="magenta")

    for i, m in enumerate(passed_markets):
        t.add_row(
            str(i + 1),
            m["question"][:55],
            f"{m['yes_price'] * 100:.1f}¢",
            f"{m['no_price'] * 100:.1f}¢",
            f"${m['liquidity']:,.0f}",
            f"{m['days']:.2f}",
        )
    console.print(t)

    # Empirical backtest
    # Since these are <24h expiry markets, they're in the "late" lifecycle stage
    # (close to resolution) — which the paper says has NEGATIVE edge
    # But if they're newly created AND expiring soon, they might be "early"
    # We'll test both scenarios

    np.random.seed(42)
    n_trials = 300000
    n_markets = len(passed_markets)
    max_positions = min(n_markets, 50)

    # Scenario A: These are EARLY lifecycle (new markets that happen to expire soon)
    # Scenario B: These are LATE lifecycle (old markets near resolution)

    for scenario_name, lifecycle in [
        ("EARLY (new markets, fast expiry)", "early"),
        ("LATE (near resolution)", "late"),
    ]:
        console.print(f"\n[bold cyan]=== SCENARIO: {scenario_name} ===[/bold cyan]")

        # Get empirical win rates for each market
        EMPIRICAL = {
            "early": {0.80: 0.86, 0.85: 0.89, 0.90: 0.93, 0.95: 0.97},
            "late": {0.80: 0.78, 0.85: 0.83, 0.90: 0.88, 0.95: 0.94},
        }

        win_rates = []
        for m in passed_markets[:max_positions]:
            no_p = m["no_price"]
            bucket = EMPIRICAL[lifecycle]
            nearest = min(bucket.keys(), key=lambda p: abs(p - no_p))
            win_rates.append(bucket[nearest])

        win_rates = np.array(win_rates)
        no_prices = np.array([m["no_price"] for m in passed_markets[:max_positions]])

        # Monte Carlo
        n_pos = len(win_rates)
        wins = np.random.rand(n_trials, n_pos) < win_rates

        bankrolls = np.full(n_trials, starting_capital)
        for pos in range(n_pos):
            size = bankrolls * 0.02
            shares = size / no_prices[pos]
            bankrolls = bankrolls - size + np.where(wins[:, pos], shares, 0.0)

        median = np.median(bankrolls)
        mean = np.mean(bankrolls)
        p1 = np.percentile(bankrolls, 1)
        p5 = np.percentile(bankrolls, 5)
        p95 = np.percentile(bankrolls, 95)
        p99 = np.percentile(bankrolls, 99)
        profitable = np.mean(bankrolls > starting_capital) * 100

        r = Table(show_header=True, header_style="bold magenta")
        r.add_column("Metric", style="cyan")
        r.add_column("Value", justify="right", style="yellow")
        r.add_row("Positions", f"{n_pos}")
        r.add_row("Trials", f"{n_trials:,}")
        r.add_row("1st %ile", f"${p1:,.2f} ({(p1 / starting_capital - 1) * 100:+.1f}%)")
        r.add_row("5th %ile", f"${p5:,.2f} ({(p5 / starting_capital - 1) * 100:+.1f}%)")
        r.add_row(
            "MEDIAN",
            f"[bold green]${median:,.2f} ({(median / starting_capital - 1) * 100:+.1f}%)[/bold green]",
        )
        r.add_row(
            "MEAN",
            f"[bold green]${mean:,.2f} ({(mean / starting_capital - 1) * 100:+.1f}%)[/bold green]",
        )
        r.add_row(
            "95th %ile", f"${p95:,.2f} ({(p95 / starting_capital - 1) * 100:+.1f}%)"
        )
        r.add_row(
            "99th %ile", f"${p99:,.2f} ({(p99 / starting_capital - 1) * 100:+.1f}%)"
        )
        r.add_row("Profit Prob", f"{profitable:.1f}%")
        console.print(r)


if __name__ == "__main__":
    all_markets = fetch_all_active_markets()
    console.print(f"\n[green]Total scanned: {len(all_markets):,} markets[/green]")

    passed = scan_exact_filters(all_markets)
    backtest_passed_markets(passed, starting_capital=10000.0)
