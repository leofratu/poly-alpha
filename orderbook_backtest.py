"""
ORDERBOOK BACKTEST — REAL HISTORICAL DATA
Uses actual Polymarket orderbook snapshots from parquet files.
For each market that had Yes bid 5-15¢ (No ask 85-95¢),
checks if it resolved and calculates actual PnL.
"""

import pyarrow.parquet as pq
import pandas as pd
import json
import os
import urllib.request
import ssl
import time
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

DATA_DIR = "/Users/main/Desktop/trades"


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


def load_orderbook_data():
    """Load all parquet files and extract markets in our target range."""
    console.print(Panel("[bold green]LOADING ORDERBOOK DATA[/bold green]"))

    files = sorted([f for f in os.listdir(DATA_DIR) if f.endswith(".parquet")])
    console.print(f"Found {len(files)} parquet files")

    target_markets = {}  # market_id -> {min_yes_bid, max_yes_bid, avg_yes_bid, timestamps}

    for i, f in enumerate(files):
        path = os.path.join(DATA_DIR, f)
        console.print(f"\n[{i + 1}/{len(files)}] Processing {f}...")

        pf = pq.ParquetFile(path)
        # Read in batches to avoid OOM
        for batch_idx in range(pf.metadata.num_row_groups):
            table = pf.read_row_group(
                batch_idx,
                columns=["timestamp_received", "market_id", "update_type", "data"],
            )
            df = table.to_pandas()

            # Filter to price_change events
            price_changes = df[df["update_type"] == "price_change"]

            if len(price_changes) == 0:
                continue

            # Parse data column
            parsed_data = []
            for _, row in price_changes.iterrows():
                try:
                    d = json.loads(row["data"])
                    parsed_data.append(
                        {
                            "market_id": row["market_id"],
                            "timestamp": row["timestamp_received"],
                            "side": d.get("side"),
                            "best_bid": float(d.get("best_bid", 0)),
                            "best_ask": float(d.get("best_ask", 0)),
                        }
                    )
                except:
                    continue

            if not parsed_data:
                continue

            df_parsed = pd.DataFrame(parsed_data)

            # Filter YES side with bid 5-15¢
            yes_target = df_parsed[
                (df_parsed["side"] == "YES")
                & (df_parsed["best_bid"] >= 0.05)
                & (df_parsed["best_bid"] <= 0.15)
            ]

            for mid in yes_target["market_id"].unique():
                m_data = yes_target[yes_target["market_id"] == mid]
                if mid not in target_markets:
                    target_markets[mid] = {
                        "min_yes_bid": float("inf"),
                        "max_yes_bid": 0,
                        "bids": [],
                        "timestamps": [],
                    }
                target_markets[mid]["min_yes_bid"] = min(
                    target_markets[mid]["min_yes_bid"], m_data["best_bid"].min()
                )
                target_markets[mid]["max_yes_bid"] = max(
                    target_markets[mid]["max_yes_bid"], m_data["best_bid"].max()
                )
                target_markets[mid]["bids"].extend(m_data["best_bid"].tolist())
                target_markets[mid]["timestamps"].extend(m_data["timestamp"].tolist())

            console.print(
                f"  Batch {batch_idx + 1}/{pf.metadata.num_row_groups}: {len(yes_target):,} target events, {len(target_markets)} unique markets so far"
            )

    console.print(
        f"\n[green]Total unique markets in target range: {len(target_markets)}[/green]"
    )
    return target_markets


def fetch_resolution(market_id):
    """Get resolution from Gamma API."""
    try:
        url = f"https://gamma-api.polymarket.com/condition/{market_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as resp:
            data = json.loads(resp.read().decode())
            markets = data.get("markets", [])
            for m in markets:
                uma = m.get("umaResolutionStatus", "")
                if m.get("closed") and (m.get("resolvedBy") or uma == "resolved"):
                    prices = json.loads(m.get("outcomePrices", "[]"))
                    outcomes = json.loads(m.get("outcomes", "[]"))
                    if len(prices) >= 2 and len(outcomes) >= 2:
                        return {
                            "resolved": True,
                            "yes_final": float(prices[0]),
                            "no_final": float(prices[1]),
                            "outcomes": outcomes,
                            "question": m.get("question", ""),
                            "volume": float(m.get("volume", 0)),
                            "liquidity": float(m.get("liquidity", 0)),
                        }
            return {"resolved": False}
    except Exception as e:
        return {"resolved": False, "error": str(e)}


def run_orderbook_backtest():
    console.print(
        Panel(
            "[bold green]ORDERBOOK BACKTEST — REAL HISTORICAL DATA[/bold green]\n"
            "[white]Using actual orderbook snapshots from April 3-5, 2026.[/white]\n"
            "[white]For each market with Yes bid 5-15¢, checks resolution and PnL.[/white]"
        )
    )

    # Step 1: Load orderbook data
    target_markets = load_orderbook_data()

    if not target_markets:
        console.print("[red]No markets found in target range.[/red]")
        return

    # Step 2: Get resolutions
    console.print(
        f"\n[cyan]Fetching resolutions for {len(target_markets)} markets...[/cyan]"
    )

    resolved_markets = []
    unresolved = 0
    errors = 0

    for i, (mid, data) in enumerate(target_markets.items()):
        res = fetch_resolution(mid)
        if res.get("resolved"):
            avg_bid = sum(data["bids"]) / len(data["bids"]) if data["bids"] else 0
            resolved_markets.append(
                {
                    "market_id": mid,
                    "question": res.get("question", ""),
                    "min_yes_bid": data["min_yes_bid"],
                    "max_yes_bid": data["max_yes_bid"],
                    "avg_yes_bid": avg_bid,
                    "yes_final": res["yes_final"],
                    "no_final": res["no_final"],
                    "outcomes": res["outcomes"],
                    "volume": res.get("volume", 0),
                    "liquidity": res.get("liquidity", 0),
                    "category": classify_category(res.get("question", "")),
                }
            )
        else:
            unresolved += 1

        if (i + 1) % 50 == 0:
            console.print(
                f"  Checked {i + 1}/{len(target_markets)}... ({len(resolved_markets)} resolved, {unresolved} unresolved)"
            )
        time.sleep(0.3)

    console.print(
        f"\n[green]Resolved: {len(resolved_markets)}, Unresolved: {unresolved}[/green]"
    )

    if not resolved_markets:
        console.print("[red]No resolved markets found.[/red]")
        return

    # Step 3: Calculate PnL
    console.print(
        f"\n[cyan]Calculating PnL for {len(resolved_markets)} resolved markets...[/cyan]"
    )

    # For each market, simulate buying "No" at the average observed bid price
    # No price = 1 - yes_bid
    # If No won (no_final >= 0.999): profit = (1 - no_entry) per share
    # If Yes won (yes_final >= 0.999): loss = no_entry per share

    results = []
    total_pnl = 0.0
    total_volume = 0.0
    wins = 0
    losses = 0
    category_pnl = {}
    price_bucket_stats = {}

    for m in resolved_markets:
        # Entry: buy No at (1 - avg_yes_bid)
        no_entry = 1.0 - m["avg_yes_bid"]
        # Simulate $20 position
        position_size = 20.0
        shares = position_size / no_entry

        yes_final = m["yes_final"]
        no_final = m["no_final"]

        if no_final >= 0.999:
            # No won
            payout = shares * 1.0
            pnl = payout - position_size
            wins += 1
            outcome = "WIN"
        elif yes_final >= 0.999:
            # Yes won
            pnl = -position_size
            losses += 1
            outcome = "LOSS"
        else:
            continue

        total_pnl += pnl
        total_volume += position_size
        category = m["category"]
        category_pnl[category] = category_pnl.get(category, 0) + pnl

        # Price bucket
        bucket = f"{int(m['avg_yes_bid'] * 100)}¢"
        if bucket not in price_bucket_stats:
            price_bucket_stats[bucket] = {"wins": 0, "losses": 0, "pnl": 0, "count": 0}
        price_bucket_stats[bucket]["count"] += 1
        price_bucket_stats[bucket]["pnl"] += pnl
        if outcome == "WIN":
            price_bucket_stats[bucket]["wins"] += 1
        else:
            price_bucket_stats[bucket]["losses"] += 1

        results.append(
            {
                "question": m["question"],
                "category": category,
                "avg_yes_bid": m["avg_yes_bid"],
                "min_yes_bid": m["min_yes_bid"],
                "max_yes_bid": m["max_yes_bid"],
                "no_entry": no_entry,
                "yes_final": yes_final,
                "no_final": no_final,
                "pnl": pnl,
                "outcome": outcome,
                "volume": m["volume"],
            }
        )

    total_trades = wins + losses
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0
    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
    roi = total_pnl / total_volume * 100 if total_volume > 0 else 0

    console.print(Panel("[bold cyan]ORDERBOOK BACKTEST RESULTS[/bold cyan]"))
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right", style="yellow")
    t.add_row(
        "Orderbook Files",
        f"{len([f for f in os.listdir(DATA_DIR) if f.endswith('.parquet')])}",
    )
    t.add_row("Markets in Target Range", f"{len(target_markets):,}")
    t.add_row("Resolved Markets", f"{len(resolved_markets):,}")
    t.add_row("Unresolved", f"{unresolved:,}")
    t.add_row("", "")
    t.add_row("Wins", f"[green]{wins}[/green]")
    t.add_row("Losses", f"[red]{losses}[/red]")
    t.add_row("Win Rate", f"{win_rate:.1f}%")
    t.add_row("Total Volume (simulated)", f"${total_volume:,.2f}")
    t.add_row(
        "Total PnL",
        f"[{'green' if total_pnl >= 0 else 'red'}]${total_pnl:+,.2f}[/{'green' if total_pnl >= 0 else 'red'}]",
    )
    t.add_row("Avg PnL/Trade", f"${avg_pnl:+.2f}")
    t.add_row("ROI", f"{roi:+.1f}%")
    console.print(t)

    # Price bucket analysis
    if price_bucket_stats:
        console.print(f"\n[bold cyan]Win Rate by Yes Bid Price:[/bold cyan]")
        bt = Table(show_header=True, header_style="bold magenta")
        bt.add_column("Yes Bid", style="cyan")
        bt.add_column("No Entry", style="green")
        bt.add_column("Trades", justify="right", style="yellow")
        bt.add_column("Wins", justify="right", style="green")
        bt.add_column("Losses", justify="right", style="red")
        bt.add_column("Win Rate", justify="right", style="bold green")
        bt.add_column("Total PnL", justify="right", style="yellow")

        for bucket in sorted(price_bucket_stats.keys()):
            s = price_bucket_stats[bucket]
            total = s["wins"] + s["losses"]
            wr = s["wins"] / total * 100 if total > 0 else 0
            no_entry = 1.0 - int(bucket.replace("¢", "")) / 100
            bt.add_row(
                bucket,
                f"{no_entry * 100:.0f}¢",
                str(total),
                str(s["wins"]),
                str(s["losses"]),
                f"{wr:.1f}%",
                f"${s['pnl']:+,.2f}",
            )
        console.print(bt)

    # Category breakdown
    if category_pnl:
        console.print(f"\n[bold]PnL by Category:[/bold]")
        ct = Table(show_header=True, header_style="bold magenta")
        ct.add_column("Category", style="cyan")
        ct.add_column("Net PnL", justify="right", style="yellow")
        ct.add_column("ROI", justify="right", style="blue")
        for cat, pnl in sorted(category_pnl.items(), key=lambda x: -x[1]):
            color = "green" if pnl >= 0 else "red"
            cat_roi = pnl / (sum(1 for r in results if r["category"] == cat) * 20) * 100
            ct.add_row(cat, f"[{color}]${pnl:+,.2f}[/{color}]", f"{cat_roi:+.1f}%")
        console.print(ct)

    # Show losses
    loss_results = [r for r in results if r["outcome"] == "LOSS"]
    if loss_results:
        console.print(f"\n[bold red]Losses ({len(loss_results)}):[/bold red]")
        lt = Table(show_header=True, header_style="bold red")
        lt.add_column("Question", style="cyan")
        lt.add_column("Cat", style="magenta")
        lt.add_column("Yes Bid", justify="right", style="yellow")
        lt.add_column("No Entry", justify="right", style="green")
        lt.add_column("Lost", justify="right", style="red")
        for r in loss_results[:20]:
            lt.add_row(
                r["question"][:50],
                r["category"],
                f"{r['avg_yes_bid'] * 100:.1f}¢",
                f"{r['no_entry'] * 100:.1f}¢",
                f"${r['pnl']:+.2f}",
            )
        console.print(lt)

    # Show wins
    win_results = [r for r in results if r["outcome"] == "WIN"]
    if win_results:
        console.print(f"\n[bold green]Wins ({len(win_results)}):[/bold green]")
        wt = Table(show_header=True, header_style="bold green")
        wt.add_column("Question", style="cyan")
        wt.add_column("Cat", style="magenta")
        wt.add_column("Yes Bid", justify="right", style="yellow")
        wt.add_column("No Entry", justify="right", style="green")
        wt.add_column("Profit", justify="right", style="green")
        for r in win_results[:20]:
            wt.add_row(
                r["question"][:50],
                r["category"],
                f"{r['avg_yes_bid'] * 100:.1f}¢",
                f"{r['no_entry'] * 100:.1f}¢",
                f"${r['pnl']:+.2f}",
            )
        console.print(wt)


if __name__ == "__main__":
    run_orderbook_backtest()
