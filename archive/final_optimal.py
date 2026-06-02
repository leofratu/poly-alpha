"""
FINAL OPTIMAL CONFIGURATION
Find the EXACT optimal:
1. How many markets have enough L2 depth for real position sizing?
2. What's the max position per market before slippage?
3. What's the optimal size × count combo given REAL liquidity constraints?
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


def get_l2_max_position(market_id, no_price, max_slippage=0.02):
    """Get max position size at given slippage tolerance from CLOB."""
    try:
        url = f"https://gamma-api.polymarket.com/markets/{market_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as resp:
            m_data = json.loads(resp.read().decode())

        clob_tokens = json.loads(m_data.get("clobTokenIds", "[]"))
        prices = json.loads(m_data.get("outcomePrices", "[]"))
        if len(clob_tokens) < 2 or len(prices) < 2:
            return 0

        no_idx = 0 if float(prices[0]) > float(prices[1]) else 1
        no_token = clob_tokens[no_idx]

        clob_url = f"https://clob.polymarket.com/book?token_id={no_token}"
        req2 = urllib.request.Request(clob_url, headers={"User-Agent": "PolyAlpha/1.0"})
        with urllib.request.urlopen(req2, timeout=15, context=ssl_context) as resp2:
            ob_data = json.loads(resp2.read().decode())

        asks = ob_data.get("asks", [])
        asks_sorted = sorted(asks, key=lambda x: float(x["price"]))

        cum_cost = 0.0
        cum_shares = 0.0
        for ask in asks_sorted[:50]:
            price = float(ask["price"])
            size = float(ask["size"])
            cost = price * size
            cum_cost += cost
            cum_shares += size
            avg_price = cum_cost / cum_shares
            slippage = (avg_price - no_price) / no_price
            if slippage > max_slippage:
                break

        return cum_cost
    except:
        return 0


def run_final_optimal():
    console.print(
        Panel(
            "[bold green]FINAL OPTIMAL CONFIGURATION[/bold green]\n"
            "[white]Finding: max markets with real L2 depth → optimal sizing → max safe return.[/white]"
        )
    )

    all_markets = fetch_all()
    now = datetime.now(timezone.utc)

    # Build pool
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
                    "id": m.get("id", ""),
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

    # Check L2 depth for top 200 markets
    console.print(
        f"\n[cyan]Checking L2 depth for top 200 markets (2% slippage tolerance)...[/cyan]"
    )

    l2_markets = []
    for i, m in enumerate(pool[:200]):
        max_pos = get_l2_max_position(m["id"], m["no_price"], max_slippage=0.02)
        m["l2_max_position"] = max_pos
        l2_markets.append(m)
        if (i + 1) % 20 == 0:
            console.print(
                f"  [{i + 1}/200] checked. Avg L2 max: ${np.mean([x['l2_max_position'] for x in l2_markets]):,.0f}"
            )
        time.sleep(0.3)

    # Show L2 depth distribution
    console.print(f"\n[bold cyan]L2 Depth Distribution (top 200 markets):[/bold cyan]")
    depth_buckets = [
        (1000000, "$1M+"),
        (500000, "$500K-$1M"),
        (100000, "$100K-$500K"),
        (50000, "$50K-$100K"),
        (10000, "$10K-$50K"),
        (1000, "$1K-$10K"),
        (100, "$100-$1K"),
        (0, "<$100"),
    ]
    for threshold, label in depth_buckets:
        if threshold > 0:
            count = sum(1 for m in l2_markets if m["l2_max_position"] >= threshold)
        else:
            count = sum(1 for m in l2_markets if m["l2_max_position"] < 100)
        if count > 0:
            bar = "#" * min(60, count)
            console.print(f"  {label:15s}: {count:3d} {bar}")

    # Now find optimal: for each market, position size = min(target, L2 max)
    # Test different target sizes
    console.print(
        f"\n[bold cyan]Testing optimal sizing with REAL L2 constraints...[/bold cyan]"
    )

    target_sizes = [2.5, 5, 10, 20, 50]  # $ per position
    n_trials = 100000
    starting_capital = 1000.0

    np.random.seed(42)

    results = []

    for target in target_sizes:
        # For each market, actual position = min(target, L2 max)
        # But we also can't exceed 2% of current bankroll
        # So: actual = min(target, L2 max, 2% of bankroll)

        # First pass: what's the achievable position per market?
        achievable = []
        for m in l2_markets:
            max_pos = min(target, m["l2_max_position"])
            if max_pos >= 1:  # At least $1
                achievable.append({**m, "achievable_position": max_pos})

        if not achievable:
            continue

        n = len(achievable)
        win_probs = np.array([m["shin_no"] for m in achievable])
        no_prices = np.array([m["no_price"] for m in achievable])
        max_positions = np.array([m["achievable_position"] for m in achievable])

        wins = np.random.rand(n_trials, n) < win_probs

        bankrolls = np.full(n_trials, starting_capital)
        for pos_idx in range(n):
            # Position = min(achievable L2 max, 2% of current bankroll)
            target_size = bankrolls * 0.02
            actual_size = np.minimum(target_size, max_positions[pos_idx])
            actual_size = np.maximum(actual_size, 0)

            shares = actual_size / no_prices[pos_idx]
            payout = np.where(wins[:, pos_idx], shares, 0.0)
            bankrolls = bankrolls - actual_size + payout

        median = np.median(bankrolls)
        mean = np.mean(bankrolls)
        p1 = np.percentile(bankrolls, 1)
        p5 = np.percentile(bankrolls, 5)
        p10 = np.percentile(bankrolls, 10)
        p25 = np.percentile(bankrolls, 25)
        p95 = np.percentile(bankrolls, 95)
        profitable = np.mean(bankrolls > starting_capital) * 100
        wiped = np.mean(bankrolls < starting_capital * 0.5) * 100
        destroyed = np.mean(bankrolls < starting_capital * 0.1) * 100

        per_cycle = median / starting_capital
        monthly_median = starting_capital * (per_cycle**20)
        monthly_p5 = starting_capital * ((p5 / starting_capital) ** 20)

        results.append(
            {
                "target": target,
                "n_markets": n,
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

    # Print results
    console.print(
        Panel("[bold cyan]OPTIMAL SIZING WITH REAL L2 CONSTRAINTS[/bold cyan]")
    )
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Target/Pos", style="cyan")
    t.add_column("Markets", justify="right", style="yellow")
    t.add_column("Median", justify="right", style="green")
    t.add_column("5th %ile", justify="right", style="red")
    t.add_column("Profit %", justify="right", style="green")
    t.add_column("Wiped 50%+", justify="right", style="red")
    t.add_column("Monthly Median", justify="right", style="bold green")
    t.add_column("Monthly 5th", justify="right", style="red")

    for r in results:
        wiped_color = (
            "red" if r["wiped"] > 5 else "yellow" if r["wiped"] > 1 else "green"
        )
        t.add_row(
            f"${r['target']:.0f}",
            str(r["n_markets"]),
            f"${r['median']:,.0f}",
            f"${r['p5']:,.0f}",
            f"{r['profitable']:.1f}%",
            f"[{wiped_color}]{r['wiped']:.1f}%[/{wiped_color}]",
            f"${r['monthly_median']:,.0f}",
            f"${r['monthly_p5']:,.0f}",
        )
    console.print(t)

    # Find the best
    safe = [r for r in results if r["wiped"] < 2.0]
    if safe:
        best = max(safe, key=lambda x: x["monthly_median"])
        console.print(
            f"\n[bold green]=== OPTIMAL: ${best['target']:.0f}/position × {best['n_markets']} markets ===[/bold green]"
        )
        console.print(f"  Per cycle: +{(best['per_cycle'] - 1) * 100:.1f}%")
        console.print(f"  Monthly median: ${best['monthly_median']:,.0f} from $1,000")
        console.print(f"  Monthly 5th: ${best['monthly_p5']:,.0f}")
        console.print(f"  Wipeout risk: {best['wiped']:.1f}%")

        # Monthly compounding
        console.print(f"\n[bold]Compounding over time:[/bold]")
        mt = Table(show_header=True, header_style="bold green")
        mt.add_column("Months", style="cyan")
        mt.add_column("Cycles", style="yellow")
        mt.add_column("1st %ile", justify="right", style="red")
        mt.add_column("5th %ile", justify="right", style="red")
        mt.add_column("Median", justify="right", style="green")
        mt.add_column("Mean", justify="right", style="green")
        mt.add_column("95th %ile", justify="right", style="green")

        pc = best["per_cycle"]
        p1c = best["p1"] / starting_capital
        p5c = best["p5"] / starting_capital
        p95c = best["p95"] / starting_capital
        mc = best["mean"] / starting_capital

        for mo in [1, 2, 3, 6, 12]:
            c = mo * 20
            c1 = starting_capital * max(0, p1c**c)
            c5 = starting_capital * max(0, p5c**c)
            c50 = starting_capital * (pc**c)
            cm = starting_capital * (mc**c)
            c95 = starting_capital * (p95c**c)
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
    run_final_optimal()
