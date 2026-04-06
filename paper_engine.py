"""
POLY-ALPHA CONTINUOUS DEPLOYMENT ENGINE
- Find ALL markets with positive Shin edge
- Deploy up to 100 positions at $5 each
- As positions resolve, immediately reinvest
- Continuous compounding — no waiting for "cycles"
"""

import json
import urllib.request
import urllib.error
import time
import ssl
import re
import sqlite3
import os
import sys
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

DB_FILE = os.environ.get(
    "POLY_ALPHA_DB", os.path.expanduser("~/.poly_alpha/paper_wallet.sqlite")
)

# ============================================================
# STRATEGY PARAMETERS
# ============================================================
MIN_YES_PRICE = 0.01
MAX_YES_PRICE = 0.30
MIN_LIQUIDITY = 20
MIN_VOLUME = 10
MAX_DAYS = 30.0
MIN_DAYS = 0.1
MAX_LIFECYCLE_PCT = 0.30
MIN_SHIN_EDGE = 0.003
POSITION_SIZE = 5.0  # $5 per trade
MAX_POSITIONS = 100  # Max concurrent positions
MAX_PORTFOLIO_DEPLOY = 0.50  # 50% max deployed
JACCARD_THRESHOLD = 0.80

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
            offset += 1000
            time.sleep(0.2)
        except Exception:
            break
    return all_markets


def scan_markets(all_markets):
    """Find ALL markets with positive Shin edge in first 30% lifecycle."""
    now = datetime.now(timezone.utc)
    all_with_edge = []
    rejected = {}

    for m in all_markets:
        try:
            question = m.get("question", "")
            q_lower = question.lower()

            if LONG_TERM_PATTERNS.search(q_lower):
                rejected["long_term"] = rejected.get("long_term", 0) + 1
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
                rejected["outside_time"] = rejected.get("outside_time", 0) + 1
                continue

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
                pct_elapsed = 0.0 if days_remaining > 10 else 0.5

            if pct_elapsed > MAX_LIFECYCLE_PCT:
                rejected["not_early"] = rejected.get("not_early", 0) + 1
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
                rejected["outside_price"] = rejected.get("outside_price", 0) + 1
                continue

            volume = float(m.get("volume", 0))
            liquidity = float(m.get("liquidity", volume * 0.05))
            if volume < MIN_VOLUME:
                rejected["low_volume"] = rejected.get("low_volume", 0) + 1
                continue
            if liquidity < MIN_LIQUIDITY:
                rejected["low_liquidity"] = rejected.get("low_liquidity", 0) + 1
                continue

            category = classify_category(question)
            shin_no = shin_debiasing(no_price, category)
            shin_edge = shin_no - no_price

            if shin_edge < MIN_SHIN_EDGE:
                rejected["low_edge"] = rejected.get("low_edge", 0) + 1
                continue

            all_with_edge.append(
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
                }
            )

        except Exception:
            rejected["parse_error"] = rejected.get("parse_error", 0) + 1
            continue

    # Sort by edge (highest first)
    all_with_edge.sort(key=lambda x: -x["shin_edge"])

    # Minimal dedup
    diversified = []
    for m in all_with_edge:
        dup = False
        for e in diversified:
            if jaccard_similarity(m["question"], e["question"]) > JACCARD_THRESHOLD:
                dup = True
                break
        if not dup:
            diversified.append(m)

    return diversified, rejected


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
    """Check and settle resolved positions."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute(
        "SELECT id, market_id, investment, shares, question FROM positions WHERE status='OPEN'"
    )
    open_positions = c.fetchall()

    if not open_positions:
        conn.close()
        return 0, 0.0

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
            except Exception:
                if attempt < 2:
                    time.sleep(2**attempt)
                else:
                    pass

        if m_data is None:
            continue

        try:
            uma_status = m_data.get("umaResolutionStatus")
            is_resolved = m_data.get("resolvedBy") or (uma_status == "resolved")
            if not (m_data.get("closed") and is_resolved):
                continue

            prices = json.loads(m_data.get("outcomePrices", "[]"))
            if len(prices) >= 2:
                yes_final = float(prices[0])
                no_final = float(prices[1])

                if no_final >= 0.999:
                    payout = shares * 1.0
                    pnl = payout - investment
                    outcome = "WIN"
                elif yes_final >= 0.999:
                    payout = 0.0
                    pnl = -investment
                    outcome = "LOSS"
                else:
                    continue

                free_capital += payout
                total_pnl += pnl
                settled_count += 1

                c.execute(
                    "UPDATE positions SET status='CLOSED', payout=?, pnl=? WHERE id=?",
                    (payout, pnl, pos_id),
                )
        except Exception:
            continue

    if settled_count > 0:
        c.execute("UPDATE wallet SET free_capital = ? WHERE id=1", (free_capital,))
        conn.commit()

    conn.close()
    return settled_count, total_pnl


def deploy_trades():
    """Deploy new trades up to MAX_POSITIONS."""
    console.print(
        Panel(
            "[bold green]POLY-ALPHA CONTINUOUS DEPLOYMENT[/bold green]\n"
            "[white]Scanning ALL markets, deploying top 100 by edge.[/white]\n"
            "[white]Continuous reinvestment as positions resolve.[/white]"
        )
    )

    # Settle first
    settled, pnl = settle_trades()
    if settled > 0:
        console.print(f"[green]Settled {settled} trades. PnL: ${pnl:+,.2f}[/green]")

    # Scan for new markets
    console.print("[cyan]Scanning ALL active markets...[/cyan]")
    all_markets = fetch_all_active_markets()
    console.print(f"[green]Scanned {len(all_markets):,} markets[/green]")

    candidates, rejected = scan_markets(all_markets)
    console.print(f"[green]Found {len(candidates)} markets with positive edge[/green]")

    if not candidates:
        console.print("[red]No markets found.[/red]")
        return

    # Show top 20
    console.print(f"\n[bold cyan]Top 20 Alpha Opportunities:[/bold cyan]")
    t = Table(show_header=True, header_style="bold green")
    t.add_column("#", style="cyan")
    t.add_column("Cat", style="magenta")
    t.add_column("Question", style="white")
    t.add_column("Yes", justify="right", style="red")
    t.add_column("No", justify="right", style="green")
    t.add_column("Edge", justify="right", style="blue")
    t.add_column("Days", justify="right")

    cat_colors = {
        "politics": "bold red",
        "crypto": "bold yellow",
        "weather": "bold cyan",
        "esports": "bold magenta",
        "sports": "bold white",
        "other": "bold white",
    }

    for i, m in enumerate(candidates[:20]):
        t.add_row(
            str(i + 1),
            f"[{cat_colors.get(m['category'], 'white')}]{m['category']}[/{cat_colors.get(m['category'], 'white')}]",
            m["question"][:50],
            f"{m['yes_price'] * 100:.1f}¢",
            f"{m['no_price'] * 100:.1f}¢",
            f"+{m['shin_edge'] * 100:.1f}¢",
            f"{m['days']:.1f}",
        )
    console.print(t)

    # Get current state
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute("SELECT market_id FROM positions WHERE status='OPEN'")
    active_ids = set(r[0] for r in c.fetchall())
    c.execute("SELECT COUNT(*) FROM positions WHERE status='OPEN'")
    active_count = c.fetchone()[0]
    c.execute("SELECT SUM(investment) FROM positions WHERE status='OPEN'")
    res = c.fetchone()
    locked = res[0] if res and res[0] else 0.0

    free_capital = get_wallet()
    total_portfolio = free_capital + locked

    console.print(f"\n[bold]Current state:[/bold]")
    console.print(f"  Active positions: {active_count}/{MAX_POSITIONS}")
    console.print(f"  Free capital: ${free_capital:,.2f}")
    console.print(f"  Locked: ${locked:,.2f}")

    # Deploy new trades
    total_deployed = 0.0
    deployed_count = 0

    for m in candidates[:MAX_POSITIONS]:
        if active_count >= MAX_POSITIONS:
            break

        if m["id"] in active_ids:
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

        # Check capital
        if total_deployed + POSITION_SIZE > free_capital * MAX_PORTFOLIO_DEPLOY:
            break

        target_size = POSITION_SIZE

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

                    if price > retail_no * 1.03:
                        break

                    capital_needed = target_size - total_cost
                    max_shares = capital_needed / price
                    shares_to_buy = min(size, max_shares)
                    total_cost += shares_to_buy * price
                    total_shares += shares_to_buy

                    if total_cost >= target_size * 0.99:
                        break

                # Handle thin books
                if total_cost < target_size * 0.50:
                    if len(asks) > 0:
                        best_ask = float(asks[0]["price"])
                        best_size = float(asks[0]["size"])
                        if best_ask <= retail_no * 1.05:
                            total_cost = best_ask * min(
                                best_size, target_size / best_ask
                            )
                            total_shares = min(best_size, target_size / best_ask)
                            if total_cost < 3:
                                continue
                        else:
                            continue
                    else:
                        continue

                actual_entry_no = (
                    total_cost / total_shares if total_shares > 0 else retail_no
                )

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
                deployed_count += 1
                console.print(
                    f"[green]DEPLOYED #{deployed_count}:[/green] {m['question'][:45]}... | ${total_cost:.2f} | No: {actual_entry_no * 100:.1f}¢ | Edge: +{m['shin_edge'] * 100:.1f}¢"
                )

                time.sleep(0.5)

        except Exception as e:
            console.print(f"[yellow]Skipped: {e}[/yellow]")
            continue

    if total_deployed > 0:
        console.print(
            f"\n[bold green]Deployed ${total_deployed:.2f} into {deployed_count} positions.[/bold green]"
        )
    else:
        console.print("[yellow]No new positions deployed.[/yellow]")

    conn.close()


def status():
    """Show current portfolio status."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    c.execute("SELECT free_capital FROM wallet WHERE id=1")
    free_capital = c.fetchone()[0]

    c.execute(
        "SELECT investment, shares, question, entry_no_price FROM positions WHERE status='OPEN'"
    )
    open_positions = c.fetchall()

    locked = sum(p[0] for p in open_positions)
    total_value = free_capital + locked

    c.execute("SELECT SUM(pnl) FROM positions WHERE status='CLOSED'")
    res = c.fetchone()
    realized = res[0] if res and res[0] else 0.0

    conn.close()

    console.print(Panel("[bold cyan]PORTFOLIO STATUS[/bold cyan]"))
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right", style="yellow")
    t.add_row("Total Value", f"[bold green]${total_value:,.2f}[/bold green]")
    t.add_row("Free Capital", f"${free_capital:,.2f}")
    t.add_row("Locked", f"${locked:,.2f}")
    t.add_row("Active Positions", f"{len(open_positions)}/{MAX_POSITIONS}")
    t.add_row(
        "Realized PnL",
        f"[{'green' if realized >= 0 else 'red'}]${realized:+,.2f}[/{'green' if realized >= 0 else 'red'}]",
    )
    console.print(t)


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("Usage: python paper_engine.py [init|deploy|status|step]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init_db()
    elif cmd == "deploy":
        deploy_trades()
    elif cmd == "status":
        status()
    elif cmd == "step":
        settle_trades()
        deploy_trades()
        status()
