"""
HISTORICAL BACKTEST — REAL TRADE DATA FROM POLYMARKET DATA API
Uses data-api.polymarket.com/trades endpoint.
Max 5000 trades (API limit). Filters for No buys at 80-96¢.
Checks actual resolution outcomes.
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
        "other": 1.18,
        "sports": 1.20,
    }.get(cat, 1.18)
    return (p**gamma) / ((p**gamma) + ((1.0 - p) ** gamma))


def fetch_trades(max_trades=5000):
    """Fetch trades from Polymarket Data API. Max offset is 5000."""
    console.print(
        f"[cyan]Fetching up to {max_trades:,} trades from Polymarket Data API...[/cyan]"
    )
    all_trades = []
    offset = 0
    limit = 1000

    while len(all_trades) < max_trades:
        url = f"https://data-api.polymarket.com/trades?limit={limit}&offset={offset}&takerOnly=true"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=60, context=ssl_context) as resp:
                trades = json.loads(resp.read().decode())
                if not trades:
                    break
                all_trades.extend(trades)
                oldest_ts = trades[-1].get("timestamp", 0)
                date = datetime.fromtimestamp(oldest_ts, tz=timezone.utc).strftime(
                    "%Y-%m-%d %H:%M"
                )
                console.print(f"  {len(all_trades):,} trades (oldest: {date})...")
                offset += limit
                time.sleep(0.5)
        except Exception as e:
            console.print(f"[yellow]Error at offset {offset}: {e}[/yellow]")
            break

    return all_trades


def fetch_market_resolution(condition_id):
    """Get resolution data for a market from Gamma API."""
    try:
        url = f"https://gamma-api.polymarket.com/condition/{condition_id}"
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
                        }
            return {"resolved": False}
    except:
        return {"resolved": False}


def run_real_backtest():
    console.print(
        Panel(
            "[bold green]HISTORICAL BACKTEST — REAL TRADE DATA[/bold green]\n"
            "[white]Polymarket Data API: actual trade prices, actual outcomes.[/white]"
        )
    )

    trades = fetch_trades(max_trades=5000)
    if not trades:
        console.print("[red]No trades fetched.[/red]")
        return

    console.print(f"\n[green]Total trades fetched: {len(trades):,}[/green]")

    # Filter to "No" BUY trades in our target price range
    console.print("\n[cyan]Filtering for 'No' BUY trades in 80-96¢ range...[/cyan]")

    our_trades = []
    rejected = {}

    for t in trades:
        try:
            price = float(t.get("price", 0))
            side = t.get("side", "")
            outcome = t.get("outcome", "")
            title = t.get("title", "")
            condition_id = t.get("conditionId", "")
            timestamp = t.get("timestamp", 0)
            size = float(t.get("size", 0))

            if side == "BUY" and outcome.lower() == "no" and 0.80 <= price <= 0.96:
                our_trades.append(
                    {
                        "condition_id": condition_id,
                        "title": title,
                        "outcome": "No",
                        "price": price,
                        "size": size,
                        "timestamp": timestamp,
                        "date": datetime.fromtimestamp(
                            timestamp, tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M"),
                    }
                )
            elif side == "SELL" and outcome.lower() == "yes" and 0.80 <= price <= 0.96:
                our_trades.append(
                    {
                        "condition_id": condition_id,
                        "title": title,
                        "outcome": "No",
                        "price": price,
                        "size": size,
                        "timestamp": timestamp,
                        "date": datetime.fromtimestamp(
                            timestamp, tz=timezone.utc
                        ).strftime("%Y-%m-%d %H:%M"),
                    }
                )
            else:
                rejected["outside_target"] = rejected.get("outside_target", 0) + 1
        except:
            rejected["parse_error"] = rejected.get("parse_error", 0) + 1

    for reason, count in sorted(rejected.items(), key=lambda x: -x[1]):
        console.print(f"  [yellow]{reason}:[/yellow] {count:,}")

    console.print(
        f"\n[bold green]MATCHING 'No' BUYS (80-96¢): {len(our_trades):,}[/bold green]"
    )

    if not our_trades:
        console.print("[red]No matching trades found.[/red]")
        return

    # Get unique markets and their resolutions
    unique_conditions = set(t["condition_id"] for t in our_trades)
    console.print(
        f"\n[cyan]Checking resolution for {len(unique_conditions):,} unique markets...[/cyan]"
    )

    resolutions = {}
    for i, cid in enumerate(unique_conditions):
        res = fetch_market_resolution(cid)
        resolutions[cid] = res
        if (i + 1) % 20 == 0:
            console.print(f"  Checked {i + 1}/{len(unique_conditions)}...")
        time.sleep(0.3)

    # Calculate PnL
    console.print(f"\n[cyan]Calculating PnL...[/cyan]")

    winning_trades = 0
    losing_trades = 0
    total_pnl = 0.0
    total_volume = 0.0
    resolved_count = 0
    unresolved_count = 0
    category_pnl = {}
    price_bucket_stats = {}

    trade_details = []

    for t in our_trades:
        cid = t["condition_id"]
        res = resolutions.get(cid, {})

        if not res.get("resolved"):
            unresolved_count += 1
            continue

        resolved_count += 1
        yes_final = res["yes_final"]
        no_final = res["no_final"]
        category = classify_category(t["title"])

        entry_price = t["price"]
        shares = t["size"]
        cost = shares * entry_price

        if no_final >= 0.999:
            payout = shares * 1.0
            pnl = payout - cost
            winning_trades += 1
            outcome_str = "WIN"
        elif yes_final >= 0.999:
            pnl = -cost
            losing_trades += 1
            outcome_str = "LOSS"
        else:
            continue

        total_pnl += pnl
        total_volume += cost
        category_pnl[category] = category_pnl.get(category, 0) + pnl

        # Price bucket
        bucket = f"{int(entry_price * 100)}¢"
        if bucket not in price_bucket_stats:
            price_bucket_stats[bucket] = {"wins": 0, "losses": 0, "pnl": 0, "volume": 0}
        price_bucket_stats[bucket]["volume"] += cost
        price_bucket_stats[bucket]["pnl"] += pnl
        if outcome_str == "WIN":
            price_bucket_stats[bucket]["wins"] += 1
        else:
            price_bucket_stats[bucket]["losses"] += 1

        trade_details.append(
            {
                "title": t["title"],
                "date": t["date"],
                "category": category,
                "entry_price": entry_price,
                "shares": shares,
                "cost": cost,
                "pnl": pnl,
                "outcome": outcome_str,
            }
        )

    total_trades = winning_trades + losing_trades
    win_rate = winning_trades / total_trades * 100 if total_trades > 0 else 0
    avg_pnl = total_pnl / total_trades if total_trades > 0 else 0
    roi = total_pnl / total_volume * 100 if total_volume > 0 else 0

    console.print(Panel("[bold cyan]REAL BACKTEST RESULTS[/bold cyan]"))
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right", style="yellow")
    t.add_row("Total Trades Fetched", f"{len(trades):,}")
    t.add_row("Matching 'No' Buys (80-96¢)", f"{len(our_trades):,}")
    t.add_row("Unique Markets", f"{len(unique_conditions):,}")
    t.add_row("Resolved", f"{resolved_count:,}")
    t.add_row("Unresolved", f"{unresolved_count:,}")
    t.add_row("", "")
    t.add_row("Wins", f"[green]{winning_trades:,}[/green]")
    t.add_row("Losses", f"[red]{losing_trades:,}[/red]")
    t.add_row("Win Rate", f"{win_rate:.1f}%")
    t.add_row("Total Volume", f"${total_volume:,.2f}")
    t.add_row(
        "Total PnL",
        f"[{'green' if total_pnl >= 0 else 'red'}]${total_pnl:+,.2f}[/{'green' if total_pnl >= 0 else 'red'}]",
    )
    t.add_row("Avg PnL/Trade", f"${avg_pnl:+.2f}")
    t.add_row(
        "ROI",
        f"[{'green' if total_volume > 0 else 'red'}]{roi:+.1f}%[/{'green' if total_volume > 0 else 'red'}]",
    )
    console.print(t)

    # Price bucket analysis
    if price_bucket_stats:
        console.print(f"\n[bold cyan]Win Rate by Entry Price:[/bold cyan]")
        bt = Table(show_header=True, header_style="bold magenta")
        bt.add_column("Entry Price", style="cyan")
        bt.add_column("Trades", justify="right", style="yellow")
        bt.add_column("Wins", justify="right", style="green")
        bt.add_column("Losses", justify="right", style="red")
        bt.add_column("Win Rate", justify="right", style="bold green")
        bt.add_column("Total PnL", justify="right", style="yellow")
        bt.add_column("ROI", justify="right", style="blue")

        for bucket in sorted(price_bucket_stats.keys()):
            s = price_bucket_stats[bucket]
            total = s["wins"] + s["losses"]
            wr = s["wins"] / total * 100 if total > 0 else 0
            roi_b = s["pnl"] / s["volume"] * 100 if s["volume"] > 0 else 0
            bt.add_row(
                bucket,
                str(total),
                str(s["wins"]),
                str(s["losses"]),
                f"{wr:.1f}%",
                f"${s['pnl']:+,.2f}",
                f"{roi_b:+.1f}%",
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
            ct.add_row(cat, f"[{color}]${pnl:+,.2f}[/{color}]", f"{roi:+.1f}%")
        console.print(ct)

    # Show losses
    losses = [d for d in trade_details if d["outcome"] == "LOSS"]
    if losses:
        console.print(f"\n[bold red]Losses ({len(losses)}):[/bold red]")
        lt = Table(show_header=True, header_style="bold red")
        lt.add_column("Title", style="cyan")
        lt.add_column("Date", style="white")
        lt.add_column("Entry", justify="right", style="yellow")
        lt.add_column("Lost", justify="right", style="red")
        for d in losses[:20]:
            lt.add_row(
                d["title"][:50],
                d["date"],
                f"{d['entry_price'] * 100:.1f}¢",
                f"${d['pnl']:+.2f}",
            )
        console.print(lt)

    wins = [d for d in trade_details if d["outcome"] == "WIN"]
    if wins:
        console.print(f"\n[bold green]Wins ({len(wins)}):[/bold green]")
        wt = Table(show_header=True, header_style="bold green")
        wt.add_column("Title", style="cyan")
        wt.add_column("Date", style="white")
        wt.add_column("Entry", justify="right", style="yellow")
        wt.add_column("Profit", justify="right", style="green")
        for d in wins[:20]:
            wt.add_row(
                d["title"][:50],
                d["date"],
                f"{d['entry_price'] * 100:.1f}¢",
                f"${d['pnl']:+.2f}",
            )
        console.print(wt)


if __name__ == "__main__":
    run_real_backtest()
