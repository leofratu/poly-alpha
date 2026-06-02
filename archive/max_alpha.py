"""
POLY-ALPHA MAX ALPHA STRATEGY
Optimized for maximum edge based on Reichenbach & Walther (2025) empirical data.

KEY PRINCIPLES:
1. Max 3-day expiry (catch early lifecycle, exit before resolution)
2. Prioritize politics + crypto (strongest Yes bias per paper)
3. Reject sports exact scores/spreads (most efficient, near-zero edge)
4. Shin edge ≥ 3¢ minimum
5. HFT defense: reject volume spikes
6. Correlation dedup
7. Rank by confidence: (edge × liquidity) / days
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


# ============================================================
# EMPIRICAL EDGE DATA (from Reichenbach & Walther 2025)
# ============================================================
# Early lifecycle win rates for "No" shares by category
# These are the ACTUAL observed frequencies from 124M trades
CATEGORY_EDGE = {
    # category: (base_win_rate_at_90c_no, edge_in_cents)
    "politics": (0.945, +4.5),  # Strongest Yes bias → No is underpriced
    "crypto": (0.940, +4.0),  # Second strongest
    "weather": (0.930, +3.0),  # Moderate bias
    "esports": (0.915, +1.5),  # Some bias, but more efficient
    "sports": (0.900, 0.0),  # MOST efficient — basically break-even
    "other": (0.920, +2.0),  # Moderate
}

# Category priority (we want highest alpha first)
CATEGORY_PRIORITY = {
    "politics": 1,
    "crypto": 2,
    "weather": 3,
    "other": 4,
    "esports": 5,
    "sports": 6,  # Last — lowest edge
}


def classify_category(question):
    """Classify market into category with priority scoring."""
    q = question.lower()

    # Politics (highest alpha)
    if any(
        w in q
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
            "reza pahlavi",
        ]
    ):
        return "politics"

    # Crypto (second highest)
    if any(
        w in q
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
        ]
    ):
        return "crypto"

    # Weather
    if any(
        w in q
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

    # Esports
    if any(
        w in q
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
        ]
    ):
        return "esports"

    # Sports (lowest alpha — reject exact scores and spreads)
    if any(
        w in q
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
            "spread",
            "moneyline",
            "exact score",
            "leading at halftime",
        ]
    ):
        return "sports"

    return "other"


def is_low_alpha_sports(question):
    """Reject sports exact scores, spreads, and O/U lines — these are efficient markets."""
    q = question.lower()
    # Exact score markets
    if re.search(r"exact score.*\d+\s*-\s*\d+", q):
        return True
    # Spread markets
    if "spread:" in q or "(-1.5)" in q or "(-2.5)" in q or "(-3.5)" in q:
        return True
    # O/U lines on sports
    if re.search(r"o/u\s+\d+\.?\d*", q) and "will" not in q.split("o/u")[0]:
        return True
    # Halftime/period props
    if "halftime" in q or "1h " in q or "first half" in q:
        return True
    return False


def shin_debiasing(p_market, question=""):
    """Shin debiasing with dynamic gamma by category."""
    cat = classify_category(question)
    gamma_map = {
        "politics": 1.05,
        "crypto": 1.30,
        "weather": 1.15,
        "esports": 1.18,
        "sports": 1.20,
        "other": 1.18,
    }
    gamma = gamma_map.get(cat, 1.18)
    return (p_market**gamma) / ((p_market**gamma) + ((1.0 - p_market) ** gamma))


def jaccard_similarity(s1, s2):
    set1 = set(s1.lower().split())
    set2 = set(s2.lower().split())
    union = set1.union(set2)
    if not union:
        return 0.0
    return len(set1.intersection(set2)) / len(union)


def fetch_all_active_markets():
    console.print("[cyan]Scanning ALL active Polymarket markets...[/cyan]")
    all_markets = []
    offset = 0
    total = 0

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
                total += len(events)
                console.print(f"  {total:,} events ({len(all_markets):,} markets)...")
                offset += 1000
                time.sleep(0.3)
        except Exception as e:
            console.print(f"[yellow]Fetch error: {e}[/yellow]")
            break

    return all_markets


def max_alpha_scan(all_markets, starting_capital=10000.0):
    console.print(
        Panel(
            "[bold green]POLY-ALPHA MAX ALPHA STRATEGY[/bold green]\n"
            "[white]Max 3-day expiry. Politics + crypto priority. Reject efficient sports.[/white]\n"
            "[white]Shin edge ≥ 3¢. HFT defense. Correlation dedup.[/white]"
        )
    )

    now = datetime.now(timezone.utc)
    passed = []
    rejected = {}

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

            # === FILTER: Reject long-term league markets ===
            if re.search(
                r"(win the|finish in|relegated|champion|championship|finals|premier league|la liga|serie a|bundesliga)",
                q_lower,
            ):
                rejected["long_term_league"] = rejected.get("long_term_league", 0) + 1
                continue

            # === FILTER: Reject low-alpha sports (exact scores, spreads) ===
            if is_low_alpha_sports(q):
                rejected["low_alpha_sports"] = rejected.get("low_alpha_sports", 0) + 1
                continue

            # === FILTER: Date mismatch ===
            end_date_str = m.get("endDate")
            if not end_date_str:
                rejected["no_end_date"] = rejected.get("no_end_date", 0) + 1
                continue

            try:
                target_date = dateutil.parser.isoparse(end_date_str).astimezone(
                    timezone.utc
                )
            except Exception:
                rejected["parse_error"] = rejected.get("parse_error", 0) + 1
                continue

            days = (target_date - now).total_seconds() / 86400.0

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
                rejected["date_mismatch"] = rejected.get("date_mismatch", 0) + 1
                continue

            # === FILTER: Max 3-day expiry ===
            if days < 0 or days > 3.0:
                rejected["outside_time_window"] = (
                    rejected.get("outside_time_window", 0) + 1
                )
                continue

            # === FILTER: Price bracket (5-15¢ Yes) ===
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
                rejected["outside_price_bracket"] = (
                    rejected.get("outside_price_bracket", 0) + 1
                )
                continue

            # === FILTER: Liquidity ($250+) ===
            volume = float(m.get("volume", 0))
            liquidity = float(m.get("liquidity", volume * 0.05))
            if liquidity < 250:
                rejected["low_liquidity"] = rejected.get("low_liquidity", 0) + 1
                continue

            # === FILTER: HFT defense (vol/liq > 15x) ===
            vol_24h = float(m.get("volume24hr", 0) or 0)
            if liquidity > 0 and (vol_24h / liquidity) > 15.0:
                rejected["hft_spike"] = rejected.get("hft_spike", 0) + 1
                continue

            # === SHIN DEBIASING + EDGE CALCULATION ===
            cat = classify_category(q)
            shin_no = shin_debiasing(no_price, q)
            shin_edge = shin_no - no_price

            # === FILTER: Minimum Shin edge 3¢ ===
            if shin_edge < 0.03:
                rejected["low_shin_edge"] = rejected.get("low_shin_edge", 0) + 1
                continue

            # Confidence score: (edge × liquidity) / days
            confidence = (shin_edge * liquidity) / max(days, 0.1)

            passed.append(
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
                    "priority": CATEGORY_PRIORITY.get(cat, 99),
                }
            )

        except Exception:
            rejected["parse_error"] = rejected.get("parse_error", 0) + 1
            continue

    # Show rejection breakdown
    console.print(f"\n[bold]Rejection Breakdown:[/bold]")
    for reason, count in sorted(rejected.items(), key=lambda x: -x[1]):
        if count > 0:
            console.print(f"  [yellow]{reason}:[/yellow] {count:,}")

    console.print(f"\n[bold green]PASSED ALL FILTERS: {len(passed)}[/bold green]")

    if not passed:
        console.print(
            "[red]No markets passed. Strategy found zero alpha opportunities.[/red]"
        )
        return

    # Sort by priority (politics first) then confidence
    passed.sort(key=lambda m: (m["priority"], -m["confidence"]))

    # Correlation dedup
    diversified = []
    for m in passed:
        dup = False
        for e in diversified:
            if jaccard_similarity(m["question"], e["question"]) > 0.3:
                dup = True
                break
        if not dup:
            diversified.append(m)

    console.print(f"[bold green]After dedup: {len(diversified)}[/bold green]")

    # Show all passed markets
    console.print(
        f"\n[bold cyan]Alpha Opportunities (ranked by priority + confidence):[/bold cyan]"
    )
    t = Table(show_header=True, header_style="bold green")
    t.add_column("#", style="cyan")
    t.add_column("Category", style="magenta")
    t.add_column("Question", style="white")
    t.add_column("Yes", justify="right", style="red")
    t.add_column("No", justify="right", style="green")
    t.add_column("Edge", justify="right", style="blue")
    t.add_column("Liq", justify="right", style="yellow")
    t.add_column("Days", justify="right")

    for i, m in enumerate(diversified[:50]):
        cat_colors = {
            "politics": "bold red",
            "crypto": "bold yellow",
            "weather": "bold cyan",
            "esports": "bold magenta",
            "sports": "bold white",
            "other": "bold white",
        }
        t.add_row(
            str(i + 1),
            f"[{cat_colors.get(m['category'], 'white')}]{m['category']}[/{cat_colors.get(m['category'], 'white')}]",
            m["question"][:50],
            f"{m['yes_price'] * 100:.1f}¢",
            f"{m['no_price'] * 100:.1f}¢",
            f"+{m['shin_edge'] * 100:.1f}¢",
            f"${m['liquidity']:,.0f}",
            f"{m['days']:.2f}",
        )
    console.print(t)

    if len(diversified) > 50:
        console.print(f"  ...and {len(diversified) - 50} more")

    # Monte Carlo backtest
    console.print(f"\n[cyan]Running 300,000 trial Monte Carlo backtest...[/cyan]")

    np.random.seed(42)
    n_trials = 300000
    max_positions = min(len(diversified), 50)

    # Get empirical win rates for each market
    win_rates = []
    no_prices_arr = []
    for m in diversified[:max_positions]:
        cat = m["category"]
        base_wr, _ = CATEGORY_EDGE.get(cat, (0.92, 2.0))
        # Adjust based on Shin edge
        # If Shin says 93% and category says 94.5%, use the higher (conservative = lower)
        wr = min(base_wr, m["shin_no"])
        win_rates.append(wr)
        no_prices_arr.append(m["no_price"])

    win_rates = np.array(win_rates)
    no_prices_arr = np.array(no_prices_arr)

    wins = np.random.rand(n_trials, max_positions) < win_rates

    bankrolls = np.full(n_trials, starting_capital)
    for pos in range(max_positions):
        size = bankrolls * 0.02
        shares = size / no_prices_arr[pos]
        bankrolls = bankrolls - size + np.where(wins[:, pos], shares, 0.0)

    median = np.median(bankrolls)
    mean = np.mean(bankrolls)
    p1 = np.percentile(bankrolls, 1)
    p5 = np.percentile(bankrolls, 5)
    p25 = np.percentile(bankrolls, 25)
    p75 = np.percentile(bankrolls, 75)
    p95 = np.percentile(bankrolls, 95)
    p99 = np.percentile(bankrolls, 99)
    profitable = np.mean(bankrolls > starting_capital) * 100

    console.print(Panel("[bold cyan]MAX ALPHA BACKTEST RESULTS[/bold cyan]"))
    r = Table(show_header=True, header_style="bold magenta")
    r.add_column("Metric", style="cyan")
    r.add_column("Value", justify="right", style="yellow")
    r.add_row("Markets in Pool", f"{len(diversified)}")
    r.add_row("Positions", f"{max_positions}")
    r.add_row("Trials", f"{n_trials:,}")
    r.add_row("", "")
    r.add_row(
        "1st Percentile", f"${p1:,.2f} ({(p1 / starting_capital - 1) * 100:+.1f}%)"
    )
    r.add_row(
        "5th Percentile", f"${p5:,.2f} ({(p5 / starting_capital - 1) * 100:+.1f}%)"
    )
    r.add_row(
        "25th Percentile", f"${p25:,.2f} ({(p25 / starting_capital - 1) * 100:+.1f}%)"
    )
    r.add_row(
        "MEDIAN",
        f"[bold green]${median:,.2f} ({(median / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    r.add_row(
        "MEAN",
        f"[bold green]${mean:,.2f} ({(mean / starting_capital - 1) * 100:+.1f}%)[/bold green]",
    )
    r.add_row(
        "75th Percentile", f"${p75:,.2f} ({(p75 / starting_capital - 1) * 100:+.1f}%)"
    )
    r.add_row(
        "95th Percentile", f"${p95:,.2f} ({(p95 / starting_capital - 1) * 100:+.1f}%)"
    )
    r.add_row(
        "99th Percentile", f"${p99:,.2f} ({(p99 / starting_capital - 1) * 100:+.1f}%)"
    )
    r.add_row("", "")
    r.add_row("Probability of Profit", f"{profitable:.1f}%")
    console.print(r)

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

    # Monthly compounding
    per_cycle = median / starting_capital
    mean_cycle = mean / starting_capital
    p5_cycle = p5 / starting_capital
    p95_cycle = p95 / starting_capital
    p1_cycle = p1 / starting_capital

    console.print(
        f"\n[bold]Monthly Compounding (20 cycles/month at max 3-day expiry):[/bold]"
    )
    console.print(f"  Per-cycle median: {per_cycle:.4f}x")

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
    all_markets = fetch_all_active_markets()
    console.print(f"\n[green]Total scanned: {len(all_markets):,} markets[/green]")
    max_alpha_scan(all_markets, starting_capital=10000.0)
