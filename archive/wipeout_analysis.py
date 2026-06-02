"""
WIPEOUT PREVENTION ANALYSIS
Test every combination of:
- Position sizes: 0.25%, 0.5%, 1.0%, 1.5%, 2.0%
- Market counts: 30, 50, 100, 200
Find the exact combo that maximizes returns while minimizing wipeout risk.
"""

import json
import urllib.request
import ssl
import time
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
            "°c",
            "°f",
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
    return "other"


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


def fetch_all():
    console.print("[cyan]Fetching ALL markets...[/cyan]")
    all_m = []
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
                for e in events:
                    for m in e.get("markets", []):
                        all_m.append(m)
                total += len(events)
                offset += 1000
                time.sleep(0.2)
        except:
            break
    return all_m


def run_wipeout_analysis():
    console.print(
        Panel(
            "[bold green]WIPEOUT PREVENTION ANALYSIS[/bold green]\n"
            "[white]Testing every combo of position size × market count.[/white]\n"
            "[white]Finding the sweet spot: max return, min wipeout risk.[/white]"
        )
    )

    all_markets = fetch_all()
    now = datetime.now(timezone.utc)

    # Build pool of all positive-edge markets
    pool = []
    for m in all_markets:
        try:
            q = m.get("question", "")
            end_date_str = m.get("endDate")
            if not end_date_str:
                continue
            target_date = dateutil.parser.isoparse(end_date_str).astimezone(
                timezone.utc
            )
            days = (target_date - now).total_seconds() / 86400.0
            if days < 0.1 or days > 30:
                continue
            tokens = json.loads(m.get("outcomePrices", "[]"))
            if len(tokens) < 2:
                continue
            outcomes = json.loads(m.get("outcomes", "[]"))
            if len(outcomes) != 2:
                continue
            yes_price = float(tokens[0])
            no_price = 1.0 - yes_price
            if yes_price < 0.01 or yes_price > 0.30:
                continue
            volume = float(m.get("volume", 0))
            liquidity = float(m.get("liquidity", volume * 0.05))
            if liquidity < 100:
                continue
            cat = classify_category(q)
            shin_no = shin_debiasing(no_price, cat)
            shin_edge = shin_no - no_price
            if shin_edge < 0.005:
                continue
            confidence = (shin_edge * max(liquidity, 1)) / max(days, 0.1)
            pool.append(
                {
                    "question": q,
                    "category": cat,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "liquidity": liquidity,
                    "days": days,
                    "shin_no": shin_no,
                    "shin_edge": shin_edge,
                    "confidence": confidence,
                }
            )
        except:
            continue

    pool.sort(key=lambda x: -x["confidence"])
    console.print(f"[green]Pool: {len(pool)} markets with positive Shin edge[/green]")

    # Test combos
    position_sizes = [0.0025, 0.005, 0.01, 0.015, 0.02]  # 0.25%, 0.5%, 1%, 1.5%, 2%
    market_counts = [30, 50, 100, 200]
    n_trials = 100000
    starting_capital = 1000.0

    np.random.seed(42)

    console.print(
        f"\n[cyan]Running {n_trials:,} trials × {len(position_sizes)} sizes × {len(market_counts)} market counts = {n_trials * len(position_sizes) * len(market_counts):,} simulations...[/cyan]"
    )

    results = []

    for size_pct in position_sizes:
        for n_markets in market_counts:
            if n_markets > len(pool):
                continue

            markets = pool[:n_markets]
            win_probs = np.array([m["shin_no"] for m in markets])
            no_prices = np.array([m["no_price"] for m in markets])

            wins = np.random.rand(n_trials, n_markets) < win_probs

            bankrolls = np.full(n_trials, starting_capital)
            for pos_idx in range(n_markets):
                size = bankrolls * size_pct
                shares = size / no_prices[pos_idx]
                payout = np.where(wins[:, pos_idx], shares, 0.0)
                bankrolls = bankrolls - size + payout

            median = np.median(bankrolls)
            mean = np.mean(bankrolls)
            p1 = np.percentile(bankrolls, 1)
            p5 = np.percentile(bankrolls, 5)
            p10 = np.percentile(bankrolls, 10)
            p25 = np.percentile(bankrolls, 25)
            p95 = np.percentile(bankrolls, 95)
            profitable = np.mean(bankrolls > starting_capital) * 100
            wiped = np.mean(bankrolls < starting_capital * 0.5) * 100  # Lost 50%+
            destroyed = np.mean(bankrolls < starting_capital * 0.1) * 100  # Lost 90%+

            per_cycle = median / starting_capital
            monthly_median = starting_capital * (per_cycle**20)
            monthly_p5 = starting_capital * ((p5 / starting_capital) ** 20)

            results.append(
                {
                    "size": size_pct,
                    "n_markets": n_markets,
                    "median": median,
                    "mean": mean,
                    "p1": p1,
                    "p5": p5,
                    "p10": p10,
                    "p25": p25,
                    "p95": p95,
                    "profitable": profitable,
                    "wiped": wiped,
                    "destroyed": destroyed,
                    "per_cycle": per_cycle,
                    "monthly_median": monthly_median,
                    "monthly_p5": monthly_p5,
                }
            )

    # Print master table
    console.print(Panel("[bold cyan]WIPEOUT RISK MATRIX (per cycle)[/bold cyan]"))
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Pos Size", style="cyan")
    t.add_column("Markets", justify="right", style="yellow")
    t.add_column("Median", justify="right", style="green")
    t.add_column("5th %ile", justify="right", style="red")
    t.add_column("Profit %", justify="right", style="green")
    t.add_column("Wiped 50%+", justify="right", style="red")
    t.add_column("Destroyed 90%+", justify="right", style="red")
    t.add_column("Monthly Median", justify="right", style="bold green")
    t.add_column("Monthly 5th", justify="right", style="red")

    for r in results:
        wiped_color = (
            "red" if r["wiped"] > 5 else "yellow" if r["wiped"] > 1 else "green"
        )
        t.add_row(
            f"{r['size'] * 100:.1f}%",
            str(r["n_markets"]),
            f"${r['median']:,.0f}",
            f"${r['p5']:,.0f}",
            f"{r['profitable']:.1f}%",
            f"[{wiped_color}]{r['wiped']:.1f}%[/{wiped_color}]",
            f"{r['destroyed']:.1f}%",
            f"${r['monthly_median']:,.0f}",
            f"${r['monthly_p5']:,.0f}",
        )
    console.print(t)

    # Find the optimal combo
    # Criteria: highest monthly median with wiped < 2% and destroyed < 0.1%
    console.print(
        f"\n[bold cyan]OPTIMAL COMBOS (ranked by monthly median, wipeout < 2%):[/bold cyan]"
    )
    safe_results = [r for r in results if r["wiped"] < 2.0 and r["destroyed"] < 0.5]
    safe_results.sort(key=lambda x: -x["monthly_median"])

    ot = Table(show_header=True, header_style="bold green")
    ot.add_column("Rank", style="cyan")
    ot.add_column("Pos Size", style="yellow")
    ot.add_column("Markets", justify="right", style="yellow")
    ot.add_column("Per Cycle", justify="right", style="green")
    ot.add_column("Monthly Median", justify="right", style="bold green")
    ot.add_column("Monthly 5th", justify="right", style="red")
    ot.add_column("Wiped 50%+", justify="right", style="red")
    ot.add_column("Destroyed 90%+", justify="right", style="red")

    for i, r in enumerate(safe_results[:10]):
        ot.add_row(
            str(i + 1),
            f"{r['size'] * 100:.1f}%",
            str(r["n_markets"]),
            f"+{(r['per_cycle'] - 1) * 100:.1f}%",
            f"${r['monthly_median']:,.0f}",
            f"${r['monthly_p5']:,.0f}",
            f"{r['wiped']:.1f}%",
            f"{r['destroyed']:.1f}%",
        )
    console.print(ot)

    # Monthly compounding for the #1 optimal
    if safe_results:
        best = safe_results[0]
        console.print(
            f"\n[bold green]=== RECOMMENDED: {best['size'] * 100:.1f}% × {best['n_markets']} markets ===[/bold green]"
        )
        console.print(f"  Per cycle: +{(best['per_cycle'] - 1) * 100:.1f}%")
        console.print(f"  Monthly median: ${best['monthly_median']:,.0f} from $1,000")
        console.print(f"  Monthly 5th: ${best['monthly_p5']:,.0f}")
        console.print(f"  Wipeout risk (50%+ loss): {best['wiped']:.1f}%")
        console.print(f"  Destroyed (90%+ loss): {best['destroyed']:.1f}%")

        console.print(f"\n[bold]Compounding over time:[/bold]")
        mt = Table(show_header=True, header_style="bold green")
        mt.add_column("Months", style="cyan")
        mt.add_column("Cycles", style="yellow")
        mt.add_column("1st %ile", justify="right", style="red")
        mt.add_column("5th %ile", justify="right", style="red")
        mt.add_column("Median", justify="right", style="green")
        mt.add_column("Mean", justify="right", style="green")
        mt.add_column("95th %ile", justify="right", style="green")

        per_cycle = best["per_cycle"]
        p1_cycle = best["p1"] / starting_capital
        p5_cycle = best["p5"] / starting_capital
        p95_cycle = best["p95"] / starting_capital
        mean_cycle = best["mean"] / starting_capital

        for mo in [1, 2, 3, 6, 12]:
            c = mo * 20
            c1 = starting_capital * max(0, p1_cycle**c)
            c5 = starting_capital * max(0, p5_cycle**c)
            c50 = starting_capital * (per_cycle**c)
            cm = starting_capital * (mean_cycle**c)
            c95 = starting_capital * (p95_cycle**c)
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
    run_wipeout_analysis()
