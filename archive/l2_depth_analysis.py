"""
L2 ORDER BOOK DEPTH ANALYSIS
For each market, hit the CLOB API to get REAL order book depth.
Calculate realistic position size based on actual liquidity at each price level.
Then re-run backtest with L2-adjusted sizing.
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


def fetch_all_markets():
    console.print("[cyan]Fetching ALL active markets...[/cyan]")
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
        except Exception as e:
            break
    return all_m


def get_l2_depth(market_id, no_price):
    """Hit CLOB order book to get REAL depth for buying No shares."""
    try:
        # Get the market details to find the No token ID
        url = f"https://gamma-api.polymarket.com/markets/{market_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
        with urllib.request.urlopen(req, timeout=15, context=ssl_context) as resp:
            m_data = json.loads(resp.read().decode())

        clob_tokens = json.loads(m_data.get("clobTokenIds", "[]"))
        prices = json.loads(m_data.get("outcomePrices", "[]"))
        outcomes = json.loads(m_data.get("outcomes", "[]"))

        if len(clob_tokens) < 2 or len(prices) < 2:
            return None, None

        # Find the No token (higher price = No)
        no_idx = 0 if float(prices[0]) > float(prices[1]) else 1
        no_token = clob_tokens[no_idx]

        # Get order book for the No token
        # We're buying No, so we look at ASKS (sellers of No)
        clob_url = f"https://clob.polymarket.com/book?token_id={no_token}"
        req2 = urllib.request.Request(clob_url, headers={"User-Agent": "PolyAlpha/1.0"})
        with urllib.request.urlopen(req2, timeout=15, context=ssl_context) as resp2:
            ob_data = json.loads(resp2.read().decode())

        asks = ob_data.get("asks", [])
        bids = ob_data.get("bids", [])

        # Calculate L2 walk: how much can we buy before price moves against us?
        # We want to buy No at current price or better
        asks_sorted = sorted(asks, key=lambda x: float(x["price"]))

        levels = []
        cumulative_cost = 0.0
        cumulative_shares = 0.0

        for ask in asks_sorted[:20]:  # Top 20 levels
            price = float(ask["price"])
            size = float(ask["size"])
            cost = price * size
            cumulative_cost += cost
            cumulative_shares += size
            levels.append(
                {
                    "price": price,
                    "size": size,
                    "cost": cost,
                    "cum_cost": cumulative_cost,
                    "cum_shares": cumulative_shares,
                    "avg_price": cumulative_cost / cumulative_shares
                    if cumulative_shares > 0
                    else 0,
                }
            )

        return levels, {
            "best_ask": asks_sorted[0]["price"] if asks_sorted else None,
            "best_bid": bids[0]["price"] if bids else None,
            "spread": (float(asks_sorted[0]["price"]) - float(bids[0]["price"]))
            if asks_sorted and bids
            else None,
            "total_ask_depth": sum(
                float(a["size"]) * float(a["price"]) for a in asks_sorted[:20]
            ),
            "total_ask_shares": sum(float(a["size"]) for a in asks_sorted[:20]),
        }

    except Exception as e:
        return None, None


def run_l2_analysis():
    console.print(
        Panel(
            "[bold green]L2 ORDER BOOK DEPTH ANALYSIS[/bold green]\n"
            "[white]Scanning ALL markets, then hitting CLOB API for REAL order book depth.[/white]"
        )
    )

    all_markets = fetch_all_markets()
    console.print(f"[green]Total: {len(all_markets):,} markets[/green]")

    # Filter to markets with positive Shin edge
    now = datetime.now(timezone.utc)
    candidates = []
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
            if shin_edge < 0.01:
                continue

            confidence = (shin_edge * max(liquidity, 1)) / max(days, 0.1)

            candidates.append(
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

    candidates.sort(key=lambda x: -x["confidence"])
    top_30 = candidates[:30]

    console.print(
        f"\n[cyan]Checking L2 order book depth for top {len(top_30)} markets...[/cyan]"
    )

    l2_data = []
    for i, m in enumerate(top_30):
        console.print(f"  [{i + 1}/{len(top_30)}] {m['question'][:50]}...")
        levels, summary = get_l2_depth(m["id"], m["no_price"])
        if levels and summary:
            # Calculate realistic position size based on L2 walk
            # We can buy up to where the avg price moves 2% above entry
            max_position = 0
            max_shares = 0
            for level in levels:
                slippage = (level["avg_price"] - m["no_price"]) / m["no_price"]
                if slippage > 0.02:  # More than 2% slippage = too much
                    break
                max_position = level["cum_cost"]
                max_shares = level["cum_shares"]

            l2_data.append(
                {
                    **m,
                    "l2_levels": levels,
                    "l2_summary": summary,
                    "max_position_2pct_slip": max_position,
                    "max_shares_2pct_slip": max_shares,
                }
            )
            console.print(
                f"    Best ask: {summary['best_ask']} | Spread: {summary['spread']:.4f} | Depth: ${summary['total_ask_depth']:,.0f} | Max pos (2% slip): ${max_position:,.0f}"
            )
        else:
            console.print(f"    [yellow]Could not fetch order book[/yellow]")
        time.sleep(0.5)

    # Show L2 analysis
    console.print(f"\n[bold cyan]L2 ORDER BOOK ANALYSIS:[/bold cyan]")
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("#", style="cyan")
    t.add_column("Question", style="white")
    t.add_column("No Price", justify="right", style="green")
    t.add_column("Best Ask", justify="right", style="yellow")
    t.add_column("Spread", justify="right", style="blue")
    t.add_column("L2 Depth", justify="right", style="yellow")
    t.add_column("Max Pos (2% slip)", justify="right", style="bold green")
    t.add_column("Edge", justify="right", style="blue")

    for i, d in enumerate(l2_data):
        s = d["l2_summary"]
        t.add_row(
            str(i + 1),
            d["question"][:40],
            f"{d['no_price'] * 100:.1f}¢",
            f"{float(s['best_ask']) * 100:.1f}¢" if s["best_ask"] else "N/A",
            f"{s['spread'] * 100:.2f}¢" if s["spread"] else "N/A",
            f"${s['total_ask_depth']:,.0f}",
            f"${d['max_position_2pct_slip']:,.0f}",
            f"+{d['shin_edge'] * 100:.1f}¢",
        )
    console.print(t)

    # Re-run backtest with L2-adjusted position sizes
    console.print(f"\n[bold cyan]L2-ADJUSTED BACKTEST (300,000 trials):[/bold cyan]")

    np.random.seed(42)
    n_trials = 300000
    starting_capital = 1000.0

    # Use L2-adjusted position sizes
    # Each position: min(2% of capital, L2 max position at 2% slippage)
    win_probs = np.array([d["shin_no"] for d in l2_data])
    no_prices = np.array([d["no_price"] for d in l2_data])
    l2_max_positions = np.array([d["max_position_2pct_slip"] for d in l2_data])

    wins = np.random.rand(n_trials, len(l2_data)) < win_probs

    bankrolls = np.full(n_trials, starting_capital)
    for pos_idx in range(len(l2_data)):
        # Position size = min(2% of current bankroll, L2 max at 2% slippage)
        target_size = bankrolls * 0.02
        actual_size = np.minimum(target_size, l2_max_positions[pos_idx])
        actual_size = np.maximum(actual_size, 0)  # Can't be negative

        shares = actual_size / no_prices[pos_idx]
        payout = np.where(wins[:, pos_idx], shares, 0.0)
        bankrolls = bankrolls - actual_size + payout

    median = np.median(bankrolls)
    mean = np.mean(bankrolls)
    p1 = np.percentile(bankrolls, 1)
    p5 = np.percentile(bankrolls, 5)
    p25 = np.percentile(bankrolls, 25)
    p75 = np.percentile(bankrolls, 75)
    p95 = np.percentile(bankrolls, 95)
    p99 = np.percentile(bankrolls, 99)
    profitable_pct = np.mean(bankrolls > starting_capital) * 100

    r = Table(show_header=True, header_style="bold magenta")
    r.add_column("Metric", style="cyan")
    r.add_column("Value", justify="right", style="yellow")
    r.add_row("Starting Capital", f"${starting_capital:,.2f}")
    r.add_row("Positions (L2-verified)", f"{len(l2_data)}")
    r.add_row("Trials", f"{n_trials:,}")
    r.add_row("", "")
    r.add_row("1st %ile", f"${p1:,.2f} ({(p1 / starting_capital - 1) * 100:+.1f}%)")
    r.add_row("5th %ile", f"${p5:,.2f} ({(p5 / starting_capital - 1) * 100:+.1f}%)")
    r.add_row("25th %ile", f"${p25:,.2f} ({(p25 / starting_capital - 1) * 100:+.1f}%)")
    r.add_row(
        "MEDIAN",
        f"[bold green]${median:,.2f} ({(median / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    r.add_row(
        "MEAN",
        f"[bold green]${mean:,.2f} ({(mean / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    r.add_row("75th %ile", f"${p75:,.2f} ({(p75 / starting_capital - 1) * 100:+.1f}%)")
    r.add_row("95th %ile", f"${p95:,.2f} ({(p95 / starting_capital - 1) * 100:+.1f}%)")
    r.add_row("99th %ile", f"${p99:,.2f} ({(p99 / starting_capital - 1) * 100:+.1f}%)")
    r.add_row("Profit Probability", f"{profitable_pct:.1f}%")
    console.print(r)

    # Monthly compounding
    per_cycle = median / starting_capital
    per_cycle_mean = mean / starting_capital
    per_cycle_p5 = p5 / starting_capital
    per_cycle_p95 = p95 / starting_capital

    console.print(f"\n[bold]Monthly Compounding (20 cycles/month):[/bold]")
    console.print(f"  Per-cycle median: {per_cycle:.4f}x")

    mt = Table(show_header=True, header_style="bold green")
    mt.add_column("Months", style="cyan")
    mt.add_column("Cycles", style="yellow")
    mt.add_column("1st %ile", justify="right", style="red")
    mt.add_column("5th %ile", justify="right", style="red")
    mt.add_column("Median", justify="right", style="green")
    mt.add_column("Mean", justify="right", style="green")
    mt.add_column("95th %ile", justify="right", style="green")

    for mo in [1, 2, 3, 6]:
        c = mo * 20
        c1 = starting_capital * max(0, (p1 / starting_capital) ** c)
        c5 = starting_capital * max(0, per_cycle_p5**c)
        c50 = starting_capital * (per_cycle**c)
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
    run_l2_analysis()
