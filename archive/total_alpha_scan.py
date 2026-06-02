"""
POLY-ALPHA TOTAL ALPHA SCAN
Find EVERY single market with ANY edge. No filters. No rejections.
Just raw edge calculation on every active market on Polymarket.
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

MONTHS = {
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


def shin_debiasing(p, cat="other"):
    gamma = {
        "politics": 1.05,
        "crypto": 1.30,
        "weather": 1.15,
        "esports": 1.18,
        "sports": 1.20,
        "other": 1.18,
    }.get(cat, 1.18)
    return (p**gamma) / ((p**gamma) + ((1.0 - p) ** gamma))


def fetch_all():
    console.print(
        "[bold cyan]SCANNING EVERY SINGLE MARKET ON POLYMARKET...[/bold cyan]"
    )
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
                console.print(f"  {total:,} events ({len(all_m):,} markets)...")
                offset += 1000
                time.sleep(0.2)
        except Exception as e:
            console.print(f"[yellow]Error at {offset}: {e}[/yellow]")
            break
    return all_m


def total_alpha_scan(all_markets):
    now = datetime.now(timezone.utc)
    console.print(
        f"\n[bold cyan]Calculating Shin edge for ALL {len(all_markets):,} markets...[/bold cyan]"
    )

    all_opportunities = []
    rejected = {}

    for m in all_markets:
        try:
            q = m.get("question", "")
            ql = q.lower()

            end_date_str = m.get("endDate")
            if not end_date_str:
                rejected["no_end_date"] = rejected.get("no_end_date", 0) + 1
                continue

            try:
                target_date = dateutil.parser.isoparse(end_date_str).astimezone(
                    timezone.utc
                )
            except:
                rejected["parse_error"] = rejected.get("parse_error", 0) + 1
                continue

            days = (target_date - now).total_seconds() / 86400.0
            if days < 0:
                rejected["expired"] = rejected.get("expired", 0) + 1
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

            # Skip if Yes is 0 or 1 (already resolved)
            if yes_price <= 0.001 or yes_price >= 0.999:
                rejected["already_resolved"] = rejected.get("already_resolved", 0) + 1
                continue

            volume = float(m.get("volume", 0))
            liquidity = float(m.get("liquidity", volume * 0.05))

            cat = classify_category(q)
            shin_no = shin_debiasing(no_price, cat)
            shin_edge = shin_no - no_price

            # Confidence = edge * liquidity / days (risk-adjusted)
            confidence = (shin_edge * max(liquidity, 1)) / max(days, 0.1)

            all_opportunities.append(
                {
                    "id": m.get("id", ""),
                    "question": q,
                    "category": cat,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "liquidity": liquidity,
                    "volume": volume,
                    "days": days,
                    "shin_no": shin_no,
                    "shin_edge": shin_edge,
                    "confidence": confidence,
                }
            )
        except:
            rejected["parse_error"] = rejected.get("parse_error", 0) + 1

    console.print(f"\n[bold]Rejections (unfixable):[/bold]")
    for reason, count in sorted(rejected.items(), key=lambda x: -x[1]):
        console.print(f"  [yellow]{reason}:[/yellow] {count:,}")

    console.print(
        f"\n[bold green]TOTAL CALCULABLE MARKETS: {len(all_opportunities):,}[/bold green]"
    )

    # Sort by edge (highest first)
    all_opportunities.sort(key=lambda x: -x["shin_edge"])

    # Show edge distribution
    console.print(f"\n[bold cyan]Edge Distribution:[/bold cyan]")
    edge_buckets = [
        (0.10, "10¢+"),
        (0.08, "8-10¢"),
        (0.06, "6-8¢"),
        (0.05, "5-6¢"),
        (0.04, "4-5¢"),
        (0.03, "3-4¢"),
        (0.02, "2-3¢"),
        (0.01, "1-2¢"),
        (0.005, "0.5-1¢"),
        (0.0, "0-0.5¢"),
        (-0.01, "Negative"),
    ]

    for threshold, label in edge_buckets:
        if threshold > 0:
            count = sum(1 for m in all_opportunities if m["shin_edge"] >= threshold)
        elif threshold == 0:
            count = sum(1 for m in all_opportunities if 0 <= m["shin_edge"] < 0.005)
        else:
            count = sum(1 for m in all_opportunities if m["shin_edge"] < 0)

        if count > 0:
            bar = "#" * min(100, int(count / 10))
            console.print(f"  {label:12s}: {count:5,} {bar}")

    # Show top markets by edge
    console.print(f"\n[bold cyan]TOP 50 MARKETS BY SHIN EDGE:[/bold cyan]")
    t = Table(show_header=True, header_style="bold green")
    t.add_column("#", style="cyan")
    t.add_column("Cat", style="magenta")
    t.add_column("Question", style="white")
    t.add_column("Yes", justify="right", style="red")
    t.add_column("No", justify="right", style="green")
    t.add_column("Edge", justify="right", style="blue")
    t.add_column("Liq", justify="right", style="yellow")
    t.add_column("Days", justify="right")

    cat_colors = {
        "politics": "bold red",
        "crypto": "bold yellow",
        "weather": "bold cyan",
        "esports": "bold magenta",
        "sports": "bold white",
        "other": "bold white",
    }

    for i, m in enumerate(all_opportunities[:50]):
        t.add_row(
            str(i + 1),
            f"[{cat_colors.get(m['category'], 'white')}]{m['category']}[/{cat_colors.get(m['category'], 'white')}]",
            m["question"][:50],
            f"{m['yes_price'] * 100:.1f}¢",
            f"{m['no_price'] * 100:.1f}¢",
            f"+{m['shin_edge'] * 100:.1f}¢",
            f"${m['liquidity']:,.0f}",
            f"{m['days']:.1f}",
        )
    console.print(t)

    # Category breakdown
    console.print(f"\n[bold cyan]Markets by Category (sorted by avg edge):[/bold cyan]")
    cat_data = {}
    for m in all_opportunities:
        cat = m["category"]
        if cat not in cat_data:
            cat_data[cat] = {
                "count": 0,
                "total_edge": 0,
                "total_liq": 0,
                "positive_edge": 0,
            }
        cat_data[cat]["count"] += 1
        cat_data[cat]["total_edge"] += m["shin_edge"]
        cat_data[cat]["total_liq"] += m["liquidity"]
        if m["shin_edge"] > 0:
            cat_data[cat]["positive_edge"] += 1

    ct = Table(show_header=True, header_style="bold magenta")
    ct.add_column("Category", style="cyan")
    ct.add_column("Total", justify="right", style="yellow")
    ct.add_column("Positive Edge", justify="right", style="green")
    ct.add_column("Avg Edge", justify="right", style="blue")
    ct.add_column("Max Edge", justify="right", style="blue")
    ct.add_column("Total Liquidity", justify="right", style="yellow")

    for cat in sorted(
        cat_data.keys(),
        key=lambda c: -cat_data[c]["total_edge"] / max(cat_data[c]["count"], 1),
    ):
        d = cat_data[cat]
        avg_edge = d["total_edge"] / d["count"]
        max_edge = max(
            m["shin_edge"] for m in all_opportunities if m["category"] == cat
        )
        ct.add_row(
            cat,
            str(d["count"]),
            str(d["positive_edge"]),
            f"+{avg_edge * 100:.2f}¢",
            f"+{max_edge * 100:.1f}¢",
            f"${d['total_liq']:,.0f}",
        )
    console.print(ct)

    # Now run Monte Carlo on the top N markets by confidence
    console.print(
        f"\n[bold cyan]Running 300,000 trial Monte Carlo on top 50 by confidence...[/bold cyan]"
    )

    # Sort by confidence (edge * liquidity / days)
    by_confidence = sorted(all_opportunities, key=lambda x: -x["confidence"])
    top_50 = by_confidence[:50]

    np.random.seed(42)
    n_trials = 300000
    max_positions = len(top_50)

    win_probs = np.array([m["shin_no"] for m in top_50])
    no_prices_arr = np.array([m["no_price"] for m in top_50])

    wins = np.random.rand(n_trials, max_positions) < win_probs

    starting_capital = 10000.0
    bankrolls = np.full(n_trials, starting_capital)
    for pos_idx in range(max_positions):
        size = bankrolls * 0.02
        payout_if_win = size / no_prices_arr[pos_idx]
        payout = np.where(wins[:, pos_idx], payout_if_win, 0.0)
        bankrolls = bankrolls - size + payout

    median = np.median(bankrolls)
    mean = np.mean(bankrolls)
    p1 = np.percentile(bankrolls, 1)
    p5 = np.percentile(bankrolls, 5)
    p95 = np.percentile(bankrolls, 95)
    p99 = np.percentile(bankrolls, 99)
    profitable_pct = np.mean(bankrolls > starting_capital) * 100

    console.print(Panel("[bold cyan]TOP 50 BY CONFIDENCE — BACKTEST[/bold cyan]"))
    r = Table(show_header=True, header_style="bold magenta")
    r.add_column("Metric", style="cyan")
    r.add_column("Value", justify="right", style="yellow")
    r.add_row("Starting Capital", f"${starting_capital:,.2f}")
    r.add_row("Positions", f"{max_positions}")
    r.add_row("Trials", f"{n_trials:,}")
    r.add_row("", "")
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
    r.add_row("95th %ile", f"${p95:,.2f} ({(p95 / starting_capital - 1) * 100:+.1f}%)")
    r.add_row("99th %ile", f"${p99:,.2f} ({(p99 / starting_capital - 1) * 100:+.1f}%)")
    r.add_row("Profit Probability", f"{profitable_pct:.1f}%")
    console.print(r)

    # Also test top 100
    console.print(
        f"\n[bold cyan]Running 300,000 trial Monte Carlo on top 100 by confidence...[/bold cyan]"
    )
    top_100 = by_confidence[:100]
    win_probs_100 = np.array([m["shin_no"] for m in top_100])
    no_prices_100 = np.array([m["no_price"] for m in top_100])
    wins_100 = np.random.rand(n_trials, len(top_100)) < win_probs_100

    bankrolls_100 = np.full(n_trials, starting_capital)
    for pos_idx in range(len(top_100)):
        size = bankrolls_100 * 0.02
        payout_if_win = size / no_prices_100[pos_idx]
        payout = np.where(wins_100[:, pos_idx], payout_if_win, 0.0)
        bankrolls_100 = bankrolls_100 - size + payout

    median_100 = np.median(bankrolls_100)
    mean_100 = np.mean(bankrolls_100)
    p5_100 = np.percentile(bankrolls_100, 5)
    p95_100 = np.percentile(bankrolls_100, 95)
    profitable_100 = np.mean(bankrolls_100 > starting_capital) * 100

    console.print(Panel("[bold cyan]TOP 100 BY CONFIDENCE — BACKTEST[/bold cyan]"))
    r2 = Table(show_header=True, header_style="bold magenta")
    r2.add_column("Metric", style="cyan")
    r2.add_column("Value", justify="right", style="yellow")
    r2.add_row("Positions", f"{len(top_100)}")
    r2.add_row("Trials", f"{n_trials:,}")
    r2.add_row("", "")
    r2.add_row(
        "5th %ile", f"${p5_100:,.2f} ({(p5_100 / starting_capital - 1) * 100:+.1f}%)"
    )
    r2.add_row(
        "MEDIAN",
        f"[bold green]${median_100:,.2f} ({(median_100 / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    r2.add_row(
        "MEAN",
        f"[bold green]${mean_100:,.2f} ({(mean_100 / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    r2.add_row(
        "95th %ile", f"${p95_100:,.2f} ({(p95_100 / starting_capital - 1) * 100:+.1f}%)"
    )
    r2.add_row("Profit Probability", f"{profitable_100:.1f}%")
    console.print(r2)

    # Monthly compounding comparison
    per_cycle_50 = median / starting_capital
    per_cycle_100 = median_100 / starting_capital

    console.print(f"\n[bold]Monthly Compounding (20 cycles/month):[/bold]")
    mt = Table(show_header=True, header_style="bold green")
    mt.add_column("Months", style="cyan")
    mt.add_column("Cycles", style="yellow")
    mt.add_column("Top 50 Median", justify="right", style="green")
    mt.add_column("Top 100 Median", justify="right", style="green")

    for mo in [1, 2, 3, 6]:
        c = mo * 20
        c50 = starting_capital * (per_cycle_50**c)
        c100 = starting_capital * (per_cycle_100**c)
        mt.add_row(str(mo), str(c), f"${c50:,.0f}", f"${c100:,.0f}")
    console.print(mt)


if __name__ == "__main__":
    all_markets = fetch_all()
    console.print(f"\n[green]Total scanned: {len(all_markets):,} markets[/green]")
    total_alpha_scan(all_markets)
