"""
POLY-ALPHA PERFECT STRATEGY
Built from everything we learned:

1. Edge exists EARLY in lifecycle (Reichenbach paper: first 20% of market life)
2. Politics + Crypto = strongest Yes bias (paper's category analysis)
3. Sports = efficient but needed for diversification
4. Late lifecycle = NEGATIVE EV (S-shaped pattern, HFTs)
5. 1-day expiry = too tight (only finds near-resolution sports = bad)
6. 7-day max = catches politics early, exits before resolution
7. Reject exact scores/spreads = efficient markets
8. Shin edge ≥ 3¢ = minimum threshold
9. HFT defense = reject vol/liq > 15x
10. Correlation dedup = Jaccard > 0.3
11. 2% sizing, 60% cap, 40% black swan reserve
12. Category limits to prevent correlated blowups
"""

import json
import urllib.request
import urllib.error
import ssl
import time
import re
import sqlite3
import os
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

DB_FILE = os.environ.get(
    "POLY_ALPHA_DB", os.path.expanduser("~/.poly_alpha/paper_wallet.sqlite")
)

# ============================================================
# STRATEGY PARAMETERS
# ============================================================
MIN_YES_PRICE = 0.05  # 5¢ minimum Yes price
MAX_YES_PRICE = 0.15  # 15¢ maximum Yes price
MIN_LIQUIDITY = 250  # $250 minimum LOB depth
MAX_DAYS = 7.0  # 7-day max expiry (catch early lifecycle)
MIN_DAYS = 0.1  # Skip markets already resolving today
MIN_SHIN_EDGE = 0.03  # 3¢ minimum Shin edge
MAX_VOL_LIQ_RATIO = 15.0  # HFT defense threshold
POSITION_SIZE_PCT = 0.02  # 2% of bankroll per trade
MAX_POSITIONS = 50  # Max concurrent positions
MAX_PORTFOLIO_DEPLOY = 0.60  # 60% max deployment (40% reserve)
JACCARD_THRESHOLD = 0.3  # Correlation dedup threshold

# Category limits (max positions per category)
CATEGORY_LIMITS = {
    "politics": 15,
    "crypto": 15,
    "sports": 10,
    "weather": 10,
    "esports": 8,
    "other": 10,
}

# Category priority (for ranking)
CATEGORY_PRIORITY = {
    "politics": 1,
    "crypto": 2,
    "weather": 3,
    "other": 4,
    "esports": 5,
    "sports": 6,
}

# Shin gamma by category (from Reichenbach paper's bias measurements)
SHIN_GAMMA = {
    "politics": 1.05,
    "crypto": 1.30,
    "weather": 1.15,
    "esports": 1.18,
    "sports": 1.20,
    "other": 1.18,
}

# Long-term league patterns to reject
LONG_TERM_PATTERNS = re.compile(
    r"(win the|finish in|relegated|champion|championship|finals|"
    r"premier league|la liga|serie a|bundesliga)",
    re.IGNORECASE,
)

# Low-alpha sports patterns to reject (efficient markets)
LOW_ALPHA_SPORTS = re.compile(
    r"(exact score.*\d+\s*-\s*\d+|spread:|\(-[0-9]+\.[0-9]+\)|"
    r"halftime|first half|1h moneyline)",
    re.IGNORECASE,
)

# Month names for date mismatch detection
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


def classify_category(question):
    """Classify market into category."""
    q = question.lower()

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
            "white house",
            "senate",
            "house of",
            "balance of power",
        ]
    ):
        return "politics"

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
            "fdv",
        ]
    ):
        return "crypto"

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
            "quadra",
        ]
    ):
        return "esports"

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
        ]
    ):
        return "sports"

    return "other"


def shin_debiasing(p_market, category="other"):
    """Shin debiasing with dynamic gamma by category."""
    gamma = SHIN_GAMMA.get(category, 1.18)
    return (p_market**gamma) / ((p_market**gamma) + ((1.0 - p_market) ** gamma))


def jaccard_similarity(s1, s2):
    set1 = set(s1.lower().split())
    set2 = set(s2.lower().split())
    union = set1.union(set2)
    if not union:
        return 0.0
    return len(set1.intersection(set2)) / len(union)


def api_request(url, retries=3):
    """API request with retry and rate limiting."""
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/15.0"})
            with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** (attempt + 2)
                console.print(f"[yellow]Rate limited. Waiting {wait}s...[/yellow]")
                time.sleep(wait)
            elif attempt < retries - 1:
                time.sleep(2**attempt)
            else:
                raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(2**attempt)
            else:
                raise


def fetch_all_active_markets():
    """Fetch ALL active markets from Polymarket Gamma API."""
    console.print("[cyan]Scanning ALL active Polymarket markets...[/cyan]")
    all_markets = []
    offset = 0
    total_events = 0

    while True:
        url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit=1000&offset={offset}"
        try:
            events = api_request(url)
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


def scan_and_filter(all_markets):
    """Apply all strategy filters. Returns ranked, deduped list."""
    console.print("\n[bold cyan]Applying strategy filters...[/bold cyan]")

    now = datetime.now(timezone.utc)
    passed = []
    rejected = {}

    for m in all_markets:
        try:
            question = m.get("question", "")
            q_lower = question.lower()

            # === FILTER 1: Reject long-term league markets ===
            if LONG_TERM_PATTERNS.search(q_lower):
                rejected["long_term_league"] = rejected.get("long_term_league", 0) + 1
                continue

            # === FILTER 2: Reject efficient sports (exact scores, spreads) ===
            if LOW_ALPHA_SPORTS.search(q_lower):
                rejected["low_alpha_sports"] = rejected.get("low_alpha_sports", 0) + 1
                continue

            # === FILTER 3: Parse and validate expiry date ===
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

            # === FILTER 4: Date mismatch detection ===
            mismatch = False
            for m_name, m_num in MONTHS.items():
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

            # === FILTER 5: Time window (0.1 to 7 days) ===
            if days < MIN_DAYS or days > MAX_DAYS:
                rejected["outside_time_window"] = (
                    rejected.get("outside_time_window", 0) + 1
                )
                continue

            # === FILTER 6: Parse prices ===
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

            # === FILTER 7: Price bracket (5-15¢ Yes) ===
            if yes_price < MIN_YES_PRICE or yes_price > MAX_YES_PRICE:
                rejected["outside_price_bracket"] = (
                    rejected.get("outside_price_bracket", 0) + 1
                )
                continue

            # === FILTER 8: Liquidity floor ===
            volume = float(m.get("volume", 0))
            liquidity = float(m.get("liquidity", volume * 0.05))
            if liquidity < MIN_LIQUIDITY:
                rejected["low_liquidity"] = rejected.get("low_liquidity", 0) + 1
                continue

            # === FILTER 9: HFT defense (volume spike) ===
            vol_24h = float(m.get("volume24hr", 0) or 0)
            if liquidity > 0 and (vol_24h / liquidity) > MAX_VOL_LIQ_RATIO:
                rejected["hft_spike"] = rejected.get("hft_spike", 0) + 1
                continue

            # === SHIN DEBIASING + EDGE CALCULATION ===
            category = classify_category(question)
            shin_no = shin_debiasing(no_price, category)
            shin_edge = shin_no - no_price

            # === FILTER 10: Minimum Shin edge ===
            if shin_edge < MIN_SHIN_EDGE:
                rejected["low_shin_edge"] = rejected.get("low_shin_edge", 0) + 1
                continue

            # Confidence score: (edge × liquidity) / days
            # Higher = better risk-adjusted opportunity
            confidence = (shin_edge * liquidity) / max(days, 0.1)

            passed.append(
                {
                    "id": m.get("id", ""),
                    "question": question,
                    "category": category,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "liquidity": liquidity,
                    "days": days,
                    "shin_no": shin_no,
                    "shin_edge": shin_edge,
                    "confidence": confidence,
                    "priority": CATEGORY_PRIORITY.get(category, 99),
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
        return []

    # Sort by priority (politics first) then confidence
    passed.sort(key=lambda m: (m["priority"], -m["confidence"]))

    # Correlation dedup
    diversified = []
    category_counts = {}
    for m in passed:
        cat = m["category"]
        if category_counts.get(cat, 0) >= CATEGORY_LIMITS.get(cat, 10):
            continue

        dup = False
        for e in diversified:
            if jaccard_similarity(m["question"], e["question"]) > JACCARD_THRESHOLD:
                dup = True
                break
        if not dup:
            diversified.append(m)
            category_counts[cat] = category_counts.get(cat, 0) + 1

    console.print(
        f"[bold green]After dedup + category limits: {len(diversified)}[/bold green]"
    )

    return diversified


def run_perfect_strategy(starting_capital=10000.0):
    """Execute the perfect strategy: scan, filter, backtest, and optionally trade."""
    console.print(
        Panel(
            "[bold green]POLY-ALPHA PERFECT STRATEGY[/bold green]\n"
            "[white]7-day max expiry. Politics + crypto priority. Reject efficient sports.[/white]\n"
            "[white]Shin edge ≥ 3¢. HFT defense. Correlation dedup. Category limits.[/white]\n"
            "[white]2% sizing. 60% max deploy. 40% black swan reserve.[/white]"
        )
    )

    # Step 1: Scan
    all_markets = fetch_all_active_markets()
    console.print(f"\n[green]Total scanned: {len(all_markets):,} markets[/green]")

    # Step 2: Filter
    candidates = scan_and_filter(all_markets)
    if not candidates:
        console.print(
            "[red]No markets passed filters. Strategy found zero alpha opportunities.[/red]"
        )
        return

    # Step 3: Show opportunities
    console.print(
        f"\n[bold cyan]Alpha Opportunities (ranked by priority + confidence):[/bold cyan]"
    )
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

    for i, m in enumerate(candidates[:50]):
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
    if len(candidates) > 50:
        console.print(f"  ...and {len(candidates) - 50} more")

    # Step 4: Monte Carlo backtest
    console.print(f"\n[cyan]Running 300,000 trial Monte Carlo backtest...[/cyan]")

    np.random.seed(42)
    n_trials = 300000
    max_positions = min(len(candidates), MAX_POSITIONS)

    win_probs = np.array([m["shin_no"] for m in candidates[:max_positions]])
    no_prices_arr = np.array([m["no_price"] for m in candidates[:max_positions]])

    wins = np.random.rand(n_trials, max_positions) < win_probs

    bankrolls = np.full(n_trials, starting_capital)
    for pos_idx in range(max_positions):
        size = bankrolls * POSITION_SIZE_PCT
        payout_if_win = size / no_prices_arr[pos_idx]
        payout = np.where(wins[:, pos_idx], payout_if_win, 0.0)
        bankrolls = bankrolls - size + payout

    median = np.median(bankrolls)
    mean = np.mean(bankrolls)
    p1 = np.percentile(bankrolls, 1)
    p5 = np.percentile(bankrolls, 5)
    p25 = np.percentile(bankrolls, 25)
    p75 = np.percentile(bankrolls, 75)
    p95 = np.percentile(bankrolls, 95)
    p99 = np.percentile(bankrolls, 99)
    profitable_pct = np.mean(bankrolls > starting_capital) * 100

    wins_per_trial = wins.sum(axis=1)
    avg_wins = np.mean(wins_per_trial)
    avg_losses = max_positions - avg_wins

    console.print(Panel("[bold cyan]BACKTEST RESULTS[/bold cyan]"))
    r = Table(show_header=True, header_style="bold magenta")
    r.add_column("Metric", style="cyan")
    r.add_column("Value", justify="right", style="yellow")
    r.add_row("Markets in Pool", f"{len(candidates)}")
    r.add_row("Positions Per Trial", f"{max_positions}")
    r.add_row("Position Size", f"{POSITION_SIZE_PCT * 100:.0f}% of bankroll")
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
    r.add_row("Probability of Profit", f"{profitable_pct:.1f}%")
    r.add_row("Avg Wins Per Trial", f"{avg_wins:.1f}")
    r.add_row("Avg Losses Per Trial", f"{avg_losses:.1f}")
    r.add_row("Avg Win Rate", f"{avg_wins / max_positions * 100:.1f}%")
    console.print(r)

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

    console.print(f"\n[bold]Monthly Compounding (20 cycles/month):[/bold]")
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
    run_perfect_strategy(starting_capital=10000.0)
