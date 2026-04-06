import sqlite3
import json
import urllib.request
import urllib.error
import time
import ssl
import re
import numpy as np
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import sys
import os

console = Console()

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

DB_FILE = os.environ.get(
    "POLY_ALPHA_DB", os.path.expanduser("~/.poly_alpha/paper_wallet.sqlite")
)

# AGGRESSIVE EARLY LIFECYCLE STRATEGY
# Based on Reichenbach & Walther (2025) — 124M trades
# Edge exists ONLY in first 20-30% of lifecycle
# We enter early, exit before resolution

MIN_YES_PRICE = 0.03
MAX_YES_PRICE = 0.17
MIN_LIQUIDITY = 200
MIN_VOLUME = 50
MAX_DAYS = 14.0
MIN_DAYS = 0.1
MAX_LIFECYCLE_PCT = 0.30  # First 30% of lifecycle
MIN_SHIN_EDGE = 0.015
MAX_VOL_LIQ_RATIO = 15.0
POSITION_SIZE_PCT = 0.02
MAX_POSITIONS = 50
MAX_PORTFOLIO_DEPLOY = 0.60
JACCARD_THRESHOLD = 0.3

CATEGORY_LIMITS = {
    "politics": 15,
    "crypto": 15,
    "sports": 10,
    "weather": 15,
    "esports": 8,
    "other": 15,
}

SHIN_GAMMA = {
    "politics": 1.05,
    "crypto": 1.30,
    "weather": 1.15,
    "esports": 1.18,
    "sports": 1.20,
    "other": 1.18,
}

LONG_TERM_PATTERNS = re.compile(
    r"(win the|finish in|relegated|champion|championship|finals|"
    r"premier league|la liga|serie a|bundesliga)",
    re.IGNORECASE,
)


def classify_category(question):
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
            "white house",
            "balance of power",
            "fidesz",
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
            "bnb",
            "hyperliquid",
            "palantir",
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
            "penta",
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
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/15.0"})
            with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
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
            time.sleep(0.2)
        except Exception as e:
            console.print(f"[yellow]Fetch error at offset {offset}: {e}[/yellow]")
            break

    return all_markets


def init_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute(
        """CREATE TABLE IF NOT EXISTS wallet (id INTEGER PRIMARY KEY, free_capital REAL)"""
    )
    c.execute("""CREATE TABLE IF NOT EXISTS positions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT,
        question TEXT,
        entry_time REAL,
        entry_no_price REAL,
        investment REAL,
        shares REAL,
        status TEXT,
        payout REAL,
        pnl REAL
    )""")

    c.execute("SELECT COUNT(*) FROM wallet")
    if c.fetchone()[0] == 0:
        c.execute("INSERT INTO wallet (id, free_capital) VALUES (1, 1000.0)")

    conn.commit()
    console.print("[green]Paper wallet initialized with $1,000.00.[/green]")


def get_wallet():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute("SELECT free_capital FROM wallet WHERE id=1")
    return c.fetchone()[0]


def settle_trades():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute(
        "SELECT id, market_id, investment, shares, question FROM positions WHERE status='OPEN'"
    )
    open_positions = c.fetchall()

    if not open_positions:
        console.print("[cyan]No open positions to settle.[/cyan]")
        return

    free_capital = get_wallet()
    settled_count = 0
    total_pnl = 0.0

    for pos in open_positions:
        pos_id, market_id, investment, shares, question = pos

        url = f"https://gamma-api.polymarket.com/markets/{market_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/5.0"})

        m_data = None
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
                    m_data = json.loads(resp.read().decode())
                break
            except urllib.error.HTTPError as e:
                if e.code == 429:
                    wait = 2 ** (attempt + 2)
                    console.print(
                        f"[yellow]Rate limited on settlement. Waiting {wait}s...[/yellow]"
                    )
                    time.sleep(wait)
                elif attempt < 2:
                    time.sleep(2**attempt)
                else:
                    console.print(
                        f"[bold red]SETTLEMENT FAILED (HTTP {e.code} after 3 retries): {question}[/bold red]"
                    )
            except Exception as e:
                if attempt < 2:
                    time.sleep(2**attempt)
                else:
                    console.print(
                        f"[bold red]SETTLEMENT FAILED (Error after 3 retries): {question} | {e}[/bold red]"
                    )

        if m_data is None:
            continue

        try:
            uma_status = m_data.get("umaResolutionStatus")
            is_resolved = m_data.get("resolvedBy") or (uma_status == "resolved")
            if not (m_data.get("closed") and is_resolved):
                continue

            prices = json.loads(m_data.get("outcomePrices", "[]"))
            clob_raw = m_data.get("clobTokenIds", "[]")
            if isinstance(clob_raw, str):
                clob_tokens = json.loads(clob_raw)
            else:
                clob_tokens = clob_raw

            if (
                len(prices) >= 2
                and len(clob_tokens) >= 2
                and (float(prices[0]) >= 0.999 or float(prices[1]) >= 0.999)
            ):
                outcomes = json.loads(m_data.get("outcomes", "[]"))

                is_loss = False

                if (
                    len(outcomes) == 2
                    and outcomes[0].lower() == "yes"
                    and outcomes[1].lower() == "no"
                ):
                    if float(prices[0]) >= 0.999:
                        is_loss = True
                elif (
                    len(outcomes) == 2
                    and outcomes[0].lower() == "no"
                    and outcomes[1].lower() == "yes"
                ):
                    if float(prices[1]) >= 0.999:
                        is_loss = True
                else:
                    if (
                        "Egypt vs. Spain end in a draw" in question
                        or "Meta (META) close above $560" in question
                    ):
                        is_loss = True

                if is_loss:
                    payout = 0.0
                    pnl = -investment
                    console.print(
                        f"[bold red]BLACK SWAN HIT (Lost 100%):[/bold red] {question} | PnL: ${pnl:.2f}"
                    )
                else:
                    payout = shares * 1.0
                    pnl = payout - investment
                    console.print(
                        f"[bold green]WIN (Alpha Secured):[/bold green] {question} | PnL: +${pnl:.2f}"
                    )

                free_capital += payout
                total_pnl += pnl
                settled_count += 1

                c.execute(
                    "UPDATE positions SET status='CLOSED', payout=?, pnl=? WHERE id=?",
                    (payout, pnl, pos_id),
                )

            elif (
                len(prices) >= 2 and float(prices[0]) == 0.5 and float(prices[1]) == 0.5
            ):
                payout = shares * 0.5
                pnl = payout - investment
                console.print(
                    f"[bold yellow]PUSH (50/50 Split):[/bold yellow] {question} | PnL: ${pnl:.2f}"
                )

                free_capital += payout
                total_pnl += pnl
                settled_count += 1

                c.execute(
                    "UPDATE positions SET status='CLOSED', payout=?, pnl=? WHERE id=?",
                    (payout, pnl, pos_id),
                )
        except Exception as e:
            console.print(
                f"[bold red]SETTLEMENT PARSE ERROR: {question} | {e}[/bold red]"
            )

    if settled_count > 0:
        c.execute("UPDATE wallet SET free_capital = ? WHERE id=1", (free_capital,))
        conn.commit()
        console.print(
            f"[bold yellow]Settlement Cycle Complete.[/bold yellow] Resolved {settled_count} trades. Net Cycle PnL: ${total_pnl:.2f}"
        )


def scan_aggressive_early_markets(all_markets):
    """Find markets in EARLY lifecycle with real volume/liquidity."""
    now = datetime.now(timezone.utc)
    early_markets = []
    rejected = {}

    for m in all_markets:
        try:
            question = m.get("question", "")
            q_lower = question.lower()

            if LONG_TERM_PATTERNS.search(q_lower):
                rejected["long_term_league"] = rejected.get("long_term_league", 0) + 1
                continue

            end_date_str = m.get("endDate")
            created_str = m.get("createdAt")
            if not end_date_str:
                rejected["no_end_date"] = rejected.get("no_end_date", 0) + 1
                continue

            try:
                end_date = datetime.fromisoformat(end_date_str.replace("Z", "+00:00"))
            except Exception:
                rejected["parse_error"] = rejected.get("parse_error", 0) + 1
                continue

            days_remaining = (end_date - now).total_seconds() / 86400.0
            if days_remaining < MIN_DAYS or days_remaining > MAX_DAYS:
                rejected["outside_time_window"] = (
                    rejected.get("outside_time_window", 0) + 1
                )
                continue

            # Estimate lifecycle stage
            if created_str:
                try:
                    created = datetime.fromisoformat(created_str.replace("Z", "+00:00"))
                    total_duration = (end_date - created).total_seconds() / 86400.0
                    pct_elapsed = (
                        1.0 - (days_remaining / total_duration)
                        if total_duration > 0
                        else 1.0
                    )
                except Exception:
                    pct_elapsed = 0.5
            else:
                pct_elapsed = 0.0 if days_remaining > 7 else 0.5

            # EARLY LIFECYCLE FILTER: first 30%
            if pct_elapsed > MAX_LIFECYCLE_PCT:
                rejected["not_early_lifecycle"] = (
                    rejected.get("not_early_lifecycle", 0) + 1
                )
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

            if yes_price < MIN_YES_PRICE or yes_price > MAX_YES_PRICE:
                rejected["outside_price_bracket"] = (
                    rejected.get("outside_price_bracket", 0) + 1
                )
                continue

            volume = float(m.get("volume", 0))
            liquidity = float(m.get("liquidity", volume * 0.05))
            if volume < MIN_VOLUME:
                rejected["low_volume"] = rejected.get("low_volume", 0) + 1
                continue
            if liquidity < MIN_LIQUIDITY:
                rejected["low_liquidity"] = rejected.get("low_liquidity", 0) + 1
                continue

            vol_24h = float(m.get("volume24hr", 0) or 0)
            if liquidity > 0 and (vol_24h / liquidity) > MAX_VOL_LIQ_RATIO:
                rejected["hft_spike"] = rejected.get("hft_spike", 0) + 1
                continue

            category = classify_category(question)
            shin_no = shin_debiasing(no_price, category)
            shin_edge = shin_no - no_price

            if shin_edge < MIN_SHIN_EDGE:
                rejected["low_shin_edge"] = rejected.get("low_shin_edge", 0) + 1
                continue

            # Confidence: (edge × volume) / days — prioritizes high-volume, high-edge, short-duration
            confidence = (shin_edge * volume) / max(days_remaining, 0.1)

            early_markets.append(
                {
                    "id": m.get("id", ""),
                    "question": question,
                    "category": category,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "liquidity": liquidity,
                    "volume": volume,
                    "days": days_remaining,
                    "pct_elapsed": pct_elapsed * 100,
                    "shin_no": shin_no,
                    "shin_edge": shin_edge,
                    "confidence": confidence,
                }
            )

        except Exception:
            rejected["parse_error"] = rejected.get("parse_error", 0) + 1
            continue

    console.print(f"\n[bold]Rejection Breakdown:[/bold]")
    for reason, count in sorted(rejected.items(), key=lambda x: -x[1]):
        if count > 0:
            console.print(f"  [yellow]{reason}:[/yellow] {count:,}")

    console.print(
        f"\n[bold green]AGGRESSIVE EARLY LIFECYCLE MARKETS FOUND: {len(early_markets)}[/bold green]"
    )

    if not early_markets:
        return []

    # Sort by confidence
    early_markets.sort(key=lambda x: -x["confidence"])

    # Correlation dedup + category limits
    diversified = []
    category_counts = {}
    for m in early_markets:
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


def trade():
    console.print(
        Panel(
            "[bold green]AGGRESSIVE EARLY LIFECYCLE STRATEGY[/bold green]\n"
            "[white]Entering markets in first 30% of lifecycle with real volume.[/white]\n"
            "[white]Based on Reichenbach & Walther (2025) — 124M trades.[/white]"
        )
    )

    all_markets = fetch_all_active_markets()
    console.print(f"\n[green]Total scanned: {len(all_markets):,} markets[/green]")

    candidates = scan_aggressive_early_markets(all_markets)
    if not candidates:
        console.print("[red]No early lifecycle markets found.[/red]")
        return

    # Show opportunities
    console.print(
        f"\n[bold cyan]Aggressive Early Lifecycle Alpha Opportunities:[/bold cyan]"
    )
    t = Table(show_header=True, header_style="bold green")
    t.add_column("#", style="cyan")
    t.add_column("Cat", style="magenta")
    t.add_column("Question", style="white")
    t.add_column("Yes", justify="right", style="red")
    t.add_column("No", justify="right", style="green")
    t.add_column("Edge", justify="right", style="blue")
    t.add_column("Volume", justify="right", style="yellow")
    t.add_column("Days", justify="right")
    t.add_column("Elapsed", justify="right")

    cat_colors = {
        "politics": "bold red",
        "crypto": "bold yellow",
        "weather": "bold cyan",
        "esports": "bold magenta",
        "sports": "bold white",
        "other": "bold white",
    }

    for i, m in enumerate(candidates[:25]):
        t.add_row(
            str(i + 1),
            f"[{cat_colors.get(m['category'], 'white')}]{m['category']}[/{cat_colors.get(m['category'], 'white')}]",
            m["question"][:45],
            f"{m['yes_price'] * 100:.1f}¢",
            f"{m['no_price'] * 100:.1f}¢",
            f"+{m['shin_edge'] * 100:.1f}¢",
            f"${m['volume']:,.0f}",
            f"{m['days']:.1f}",
            f"{m['pct_elapsed']:.0f}%",
        )
    console.print(t)
    if len(candidates) > 25:
        console.print(f"  ...and {len(candidates) - 25} more")

    # Execute trades
    free_capital = get_wallet()
    if free_capital < 10.0:
        console.print("[red]Insufficient free capital to trade.[/red]")
        return

    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute("SELECT market_id FROM positions WHERE status='OPEN'")
    active_ids = set(r[0] for r in c.fetchall())
    c.execute("SELECT SUM(investment) FROM positions WHERE status='OPEN'")
    res = c.fetchone()
    locked_capital = res[0] if res and res[0] else 0.0
    total_portfolio_value = free_capital + locked_capital
    c.execute("SELECT COUNT(*) FROM positions WHERE status='OPEN'")
    active_count = c.fetchone()[0]

    category_counts = {}
    c.execute("SELECT question FROM positions WHERE status='OPEN'")
    for row in c.fetchall():
        cat = classify_category(row[0])
        category_counts[cat] = category_counts.get(cat, 0) + 1

    total_deployed = 0.0

    for m in candidates:
        if active_count >= MAX_POSITIONS:
            console.print(
                "[yellow]Portfolio fully deployed (50 positions max).[/yellow]"
            )
            break

        if m["id"] in active_ids:
            continue

        cat = m["category"]
        if category_counts.get(cat, 0) >= CATEGORY_LIMITS.get(cat, 10):
            continue

        # Correlation check
        dup = False
        c.execute("SELECT question FROM positions WHERE status='OPEN'")
        for row in c.fetchall():
            if jaccard_similarity(m["question"], row[0]) > JACCARD_THRESHOLD:
                dup = True
                break
        if dup:
            continue

        target_size = total_portfolio_value * POSITION_SIZE_PCT
        target_size = min(target_size, free_capital - total_deployed)

        if target_size < 19.5:
            continue

        # L2 walk
        market_id = m["id"]
        url = f"https://gamma-api.polymarket.com/markets/{market_id}"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=15, context=ssl_ctx) as resp:
                m_data = json.loads(resp.read().decode())
                prices = json.loads(m_data.get("outcomePrices", "[]"))
                clob_raw = m_data.get("clobTokenIds", "[]")
                if isinstance(clob_raw, str):
                    clob_tokens = json.loads(clob_raw)
                else:
                    clob_tokens = clob_raw

                if len(prices) < 2 or len(clob_tokens) < 2:
                    continue

                idx = 0 if float(prices[0]) > float(prices[1]) else 1
                token_id = clob_tokens[idx]
                retail_no = float(prices[idx])
                true_no_prob = shin_debiasing(retail_no, m["question"])

                clob_url = f"https://clob.polymarket.com/book?token_id={token_id}"
                clob_req = urllib.request.Request(
                    clob_url, headers={"User-Agent": "PolyAlpha/1.0"}
                )
                with urllib.request.urlopen(
                    clob_req, timeout=15, context=ssl_ctx
                ) as clob_resp:
                    ob_data = json.loads(clob_resp.read().decode())

                asks = ob_data.get("asks", [])
                asks.sort(key=lambda x: float(x["price"]))

                total_cost = 0.0
                total_shares = 0.0

                for ask in asks:
                    price = float(ask["price"])
                    size = float(ask["size"])

                    if price >= true_no_prob:
                        break

                    capital_needed = target_size - total_cost
                    max_shares = capital_needed / price
                    shares_to_buy = min(size, max_shares)
                    total_cost += shares_to_buy * price
                    total_shares += shares_to_buy

                    if total_cost >= target_size * 0.99:
                        break

                if total_cost < target_size * 0.95:
                    console.print(
                        f"[red]REJECTED (L2 Liquidity):[/red] {m['question'][:45]}... | Max Safe L2 Depth: ${total_cost:.2f}"
                    )
                    continue

                actual_entry_no = total_cost / total_shares

                c.execute(
                    """INSERT INTO positions (market_id, question, entry_time, entry_no_price, investment, shares, status, payout, pnl)
                     VALUES (?, ?, ?, ?, ?, ?, 'OPEN', 0.0, 0.0)""",
                    (
                        m["id"],
                        m["question"],
                        datetime.now(timezone.utc).timestamp(),
                        actual_entry_no,
                        total_cost,
                        total_shares,
                    ),
                )
                free_capital -= total_cost
                c.execute(
                    "UPDATE wallet SET free_capital = ? WHERE id=1", (free_capital,)
                )
                conn.commit()
                total_deployed += total_cost
                active_count += 1
                category_counts[cat] = category_counts.get(cat, 0) + 1
                console.print(
                    f"[green]DEPLOYED (EARLY LIFECYCLE):[/green] {m['question'][:45]}... | Size: ${total_cost:.2f} | No: {actual_entry_no * 100:.1f}¢ | Edge: {m['shin_edge'] * 100:.1f}¢ | Elapsed: {m['pct_elapsed']:.0f}%"
                )

                time.sleep(1.0)

        except Exception as e:
            console.print(f"[yellow]Skipped (API Error): {e}[/yellow]")
            continue

    if total_deployed > 0:
        console.print(
            f"[bold green]Successfully locked ${total_deployed:,.2f} into early lifecycle favorites.[/bold green]"
        )

    conn.close()


def status():
    free_capital = get_wallet()
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute(
        "SELECT market_id, investment, shares, question, entry_no_price FROM positions WHERE status='OPEN'"
    )
    open_positions = c.fetchall()

    locked_capital = sum(p[1] for p in open_positions)
    total_value = free_capital + locked_capital

    c.execute("SELECT SUM(pnl) FROM positions WHERE status='CLOSED'")
    res = c.fetchone()
    realized_pnl = res[0] if res and res[0] else 0.0

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Account Metric", style="cyan")
    table.add_column("Value", justify="right", style="yellow")

    table.add_row(
        "Total Account Value", f"[bold green]${total_value:,.2f}[/bold green]"
    )
    table.add_row("Free Capital (Dry Powder)", f"${free_capital:,.2f}")
    table.add_row("Locked Margin (Active Trades)", f"${locked_capital:,.2f}")
    table.add_row("Active Positions", f"{len(open_positions)}")
    table.add_row(
        "Realized PnL (All Time)",
        f"{'+' if realized_pnl >= 0 else ''}${realized_pnl:,.2f}",
    )

    console.print(Panel("[bold cyan]LIVE PAPER WALLET STATUS[/bold cyan]"))
    console.print(table)

    if open_positions:
        pos_table = Table(show_header=True, header_style="bold white")
        pos_table.add_column("Market", style="cyan")
        pos_table.add_column("Entry Price", justify="right", style="yellow")
        pos_table.add_column("Investment", justify="right", style="red")
        pos_table.add_column("Shares (Max Payout)", justify="right", style="green")

        for p in open_positions:
            pos_table.add_row(
                p[3][:50] + "...", f"{p[4] * 100:.1f}¢", f"${p[1]:.2f}", f"{p[2]:.2f}"
            )
        console.print("\n[bold]Active Order Book:[/bold]")
        console.print(pos_table)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("Usage: python paper_engine.py [init|settle|trade|status|step]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init_db()
    elif cmd == "settle":
        settle_trades()
    elif cmd == "trade":
        trade()
    elif cmd == "status":
        status()
    elif cmd == "step":
        settle_trades()
        trade()
        status()
