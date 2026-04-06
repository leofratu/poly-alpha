"""
POLY-ALPHA PAPER TRADING LOGGER
Records every trade, tracks real outcomes, calculates actual PnL.
This is the ONLY way to verify if the edge is real.

Usage:
  python paper_logger.py scan    # Scan and record new opportunities
  python paper_logger.py settle  # Check resolved positions
  python paper_logger.py status  # Show current portfolio
  python paper_logger.py report  # Full PnL report
"""

import json
import urllib.request
import urllib.error
import ssl
import time
import sqlite3
import os
import sys
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

DB_FILE = os.environ.get(
    "POLY_ALPHA_LOGGER_DB", os.path.expanduser("~/.poly_alpha/paper_logger.sqlite")
)

# Strategy parameters
MIN_YES_PRICE = 0.05
MAX_YES_PRICE = 0.15
MIN_LIQUIDITY = 250
MAX_DAYS = 7.0
MIN_DAYS = 0.1
MIN_SHIN_EDGE = 0.03
MAX_VOL_LIQ_RATIO = 15.0
POSITION_SIZE = 20.0  # $20 per position
MAX_POSITIONS = 200

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

LONG_TERM = re.compile(
    r"(win the|finish in|relegated|champion|championship|finals|premier league|la liga|serie a|bundesliga)",
    re.IGNORECASE,
)
LOW_ALPHA = re.compile(
    r"(exact score.*\d+\s*-\s*\d+|spread:|\(-[0-9]+\.[0-9]+\)|halftime|first half|1h moneyline)",
    re.IGNORECASE,
)


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


def init_db():
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute("""CREATE TABLE IF NOT EXISTS trades (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT UNIQUE,
        question TEXT,
        category TEXT,
        entry_time REAL,
        entry_yes_price REAL,
        entry_no_price REAL,
        shin_no_prob REAL,
        shin_edge REAL,
        position_size REAL,
        shares REAL,
        status TEXT DEFAULT 'OPEN',
        exit_time REAL,
        exit_yes_price REAL,
        exit_no_price REAL,
        outcome TEXT,
        payout REAL,
        pnl REAL,
        days_held REAL
    )""")
    c.execute("""CREATE TABLE IF NOT EXISTS wallet (
        id INTEGER PRIMARY KEY,
        starting_capital REAL,
        current_capital REAL,
        total_deployed REAL,
        total_pnl REAL
    )""")
    c.execute("SELECT COUNT(*) FROM wallet")
    if c.fetchone()[0] == 0:
        c.execute(
            "INSERT INTO wallet (id, starting_capital, current_capital, total_deployed, total_pnl) VALUES (1, 1000.0, 1000.0, 0.0, 0.0)"
        )
    conn.commit()
    conn.close()
    console.print("[green]Paper logger database initialized with $1,000.[/green]")


def api_request(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/15.0"})
            with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
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
    all_m = []
    offset = 0
    total = 0
    while True:
        url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit=1000&offset={offset}"
        try:
            events = api_request(url)
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


def scan_trades():
    """Scan for new markets that pass all filters and record them."""
    init_db()
    console.print(Panel("[bold green]SCANNING FOR NEW TRADES[/bold green]"))

    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    # Get already recorded markets
    c.execute("SELECT market_id FROM trades")
    recorded_ids = set(r[0] for r in c.fetchall())

    # Get wallet info
    c.execute("SELECT current_capital, total_deployed FROM wallet WHERE id=1")
    row = c.fetchone()
    current_capital = row[0]
    total_deployed = row[1]

    all_markets = fetch_all_active_markets()
    console.print(f"[green]Scanned {len(all_markets):,} markets[/green]")

    now = datetime.now(timezone.utc)
    new_trades = []
    rejected = {}

    for m in all_markets:
        try:
            mid = m.get("id", "")
            if mid in recorded_ids:
                continue

            q = m.get("question", "")
            ql = q.lower()

            if LONG_TERM.search(ql):
                rejected["long_term"] = rejected.get("long_term", 0) + 1
                continue
            if LOW_ALPHA.search(ql):
                rejected["low_alpha"] = rejected.get("low_alpha", 0) + 1
                continue

            end_date_str = m.get("endDate")
            if not end_date_str:
                rejected["no_date"] = rejected.get("no_date", 0) + 1
                continue

            try:
                target_date = dateutil.parser.isoparse(end_date_str).astimezone(
                    timezone.utc
                )
            except:
                rejected["parse_error"] = rejected.get("parse_error", 0) + 1
                continue

            days = (target_date - now).total_seconds() / 86400.0
            if days < MIN_DAYS or days > MAX_DAYS:
                rejected["outside_time"] = rejected.get("outside_time", 0) + 1
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
            if liquidity < MIN_LIQUIDITY:
                rejected["low_liq"] = rejected.get("low_liq", 0) + 1
                continue

            vol_24h = float(m.get("volume24hr", 0) or 0)
            if liquidity > 0 and (vol_24h / liquidity) > MAX_VOL_LIQ_RATIO:
                rejected["hft_spike"] = rejected.get("hft_spike", 0) + 1
                continue

            cat = classify_category(q)
            shin_no = shin_debiasing(no_price, cat)
            shin_edge = shin_no - no_price

            if shin_edge < MIN_SHIN_EDGE:
                rejected["low_edge"] = rejected.get("low_edge", 0) + 1
                continue

            # Check if we have capital
            if total_deployed + POSITION_SIZE > current_capital * 0.60:
                rejected["capital_limit"] = rejected.get("capital_limit", 0) + 1
                continue

            c.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'")
            open_count = c.fetchone()[0]
            if open_count >= MAX_POSITIONS:
                rejected["max_positions"] = rejected.get("max_positions", 0) + 1
                continue

            confidence = (shin_edge * liquidity) / max(days, 0.1)
            new_trades.append(
                {
                    "id": mid,
                    "question": q,
                    "category": cat,
                    "yes_price": yes_price,
                    "no_price": no_price,
                    "shin_no": shin_no,
                    "shin_edge": shin_edge,
                    "liquidity": liquidity,
                    "days": days,
                    "confidence": confidence,
                }
            )
        except:
            rejected["error"] = rejected.get("error", 0) + 1

    # Sort by confidence and take top ones
    new_trades.sort(key=lambda x: -x["confidence"])

    console.print(f"\n[bold]Rejections:[/bold]")
    for reason, count in sorted(rejected.items(), key=lambda x: -x[1]):
        console.print(f"  [yellow]{reason}:[/yellow] {count}")

    if not new_trades:
        console.print("[yellow]No new trades found.[/yellow]")
        conn.close()
        return

    console.print(
        f"\n[bold green]Found {len(new_trades)} new trades. Recording top {min(len(new_trades), 50)}...[/bold green]"
    )

    recorded = 0
    for t in new_trades[:50]:
        shares = POSITION_SIZE / t["no_price"]
        c.execute(
            """INSERT OR IGNORE INTO trades 
            (market_id, question, category, entry_time, entry_yes_price, entry_no_price,
             shin_no_prob, shin_edge, position_size, shares, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'OPEN')""",
            (
                t["id"],
                t["question"],
                t["category"],
                now.timestamp(),
                t["yes_price"],
                t["no_price"],
                t["shin_no"],
                t["shin_edge"],
                POSITION_SIZE,
                shares,
            ),
        )

        if c.rowcount > 0:
            total_deployed += POSITION_SIZE
            recorded += 1

    c.execute(
        "UPDATE wallet SET current_capital = ?, total_deployed = ? WHERE id=1",
        (current_capital, total_deployed),
    )
    conn.commit()
    conn.close()

    console.print(f"[green]Recorded {recorded} new trades.[/green]")

    # Show them
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

    for i, tr in enumerate(new_trades[:20]):
        t.add_row(
            str(i + 1),
            f"[{cat_colors.get(tr['category'], 'white')}]{tr['category']}[/{cat_colors.get(tr['category'], 'white')}]",
            tr["question"][:50],
            f"{tr['yes_price'] * 100:.1f}¢",
            f"{tr['no_price'] * 100:.1f}¢",
            f"+{tr['shin_edge'] * 100:.1f}¢",
            f"{tr['days']:.1f}",
        )
    console.print(t)


def settle_trades():
    """Check if any open positions have resolved."""
    init_db()
    console.print(Panel("[bold green]SETTLING RESOLVED TRADES[/bold green]"))

    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    c.execute(
        "SELECT id, market_id, question, position_size, shares FROM trades WHERE status='OPEN'"
    )
    open_trades = c.fetchall()

    if not open_trades:
        console.print("[cyan]No open positions to settle.[/cyan]")
        conn.close()
        return

    settled = 0
    total_pnl = 0.0

    for trade in open_trades:
        trade_id, market_id, question, position_size, shares = trade

        url = f"https://gamma-api.polymarket.com/markets/{market_id}"
        try:
            m_data = api_request(url)
            uma = m_data.get("umaResolutionStatus", "")
            is_resolved = m_data.get("resolvedBy") or (uma == "resolved")

            if not (m_data.get("closed") and is_resolved):
                continue

            prices = json.loads(m_data.get("outcomePrices", "[]"))
            outcomes = json.loads(m_data.get("outcomes", "[]"))

            if len(prices) >= 2 and len(outcomes) >= 2:
                yes_final = float(prices[0])
                no_final = float(prices[1])

                if yes_final >= 0.999:
                    # Yes won → we lose
                    outcome = "LOSS"
                    payout = 0.0
                    pnl = -position_size
                elif no_final >= 0.999:
                    # No won → we collect $1/share
                    outcome = "WIN"
                    payout = shares * 1.0
                    pnl = payout - position_size
                elif yes_final == 0.5 and no_final == 0.5:
                    outcome = "PUSH"
                    payout = shares * 0.5
                    pnl = payout - position_size
                else:
                    continue

                now = datetime.now(timezone.utc)
                c.execute("SELECT entry_time FROM trades WHERE id=?", (trade_id,))
                entry_time = c.fetchone()[0]
                days_held = (now.timestamp() - entry_time) / 86400.0

                c.execute(
                    """UPDATE trades SET 
                    status='CLOSED', exit_time=?, exit_yes_price=?, exit_no_price=?,
                    outcome=?, payout=?, pnl=?, days_held=?
                    WHERE id=?""",
                    (
                        now.timestamp(),
                        yes_final,
                        no_final,
                        outcome,
                        payout,
                        pnl,
                        days_held,
                        trade_id,
                    ),
                )

                total_pnl += pnl
                settled += 1

                color = (
                    "green"
                    if outcome == "WIN"
                    else "red"
                    if outcome == "LOSS"
                    else "yellow"
                )
                console.print(
                    f"[{color}]{outcome}:[/bold {color}] {question[:50]}... | PnL: ${pnl:+.2f} | Held {days_held:.1f} days"
                )

        except Exception as e:
            continue

    if settled > 0:
        c.execute("SELECT total_pnl FROM wallet WHERE id=1")
        old_pnl = c.fetchone()[0] or 0.0
        c.execute("UPDATE wallet SET total_pnl = ? WHERE id=1", (old_pnl + total_pnl,))
        conn.commit()
        console.print(
            f"\n[bold green]Settled {settled} trades. Cycle PnL: ${total_pnl:+.2f}[/bold green]"
        )
    else:
        console.print("[cyan]No trades resolved yet.[/cyan]")

    conn.close()


def show_status():
    """Show current portfolio status."""
    init_db()
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    c.execute(
        "SELECT starting_capital, current_capital, total_deployed, total_pnl FROM wallet WHERE id=1"
    )
    w = c.fetchone()

    c.execute("SELECT COUNT(*) FROM trades WHERE status='OPEN'")
    open_count = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND outcome='WIN'")
    wins = c.fetchone()[0]

    c.execute("SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND outcome='LOSS'")
    losses = c.fetchone()[0]

    c.execute("SELECT SUM(pnl) FROM trades WHERE status='CLOSED'")
    realized = c.fetchone()[0] or 0.0

    conn.close()

    console.print(Panel("[bold cyan]PAPER TRADING STATUS[/bold cyan]"))
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right", style="yellow")
    t.add_row("Starting Capital", f"${w[0]:,.2f}")
    t.add_row("Current Capital", f"${w[1]:,.2f}")
    t.add_row("Total Deployed", f"${w[2]:,.2f}")
    t.add_row("Open Positions", str(open_count))
    t.add_row("Wins", f"[green]{wins}[/green]")
    t.add_row("Losses", f"[red]{losses}[/red]")
    t.add_row(
        "Win Rate",
        f"{wins / (wins + losses) * 100:.1f}%" if (wins + losses) > 0 else "N/A",
    )
    t.add_row(
        "Realized PnL",
        f"[{'green' if realized >= 0 else 'red'}]${realized:+,.2f}[/{'green' if realized >= 0 else 'red'}]",
    )
    t.add_row(
        "Total PnL",
        f"[{'green' if w[3] >= 0 else 'red'}]${w[3]:+,.2f}[/{'green' if w[3] >= 0 else 'red'}]",
    )
    console.print(t)


def full_report():
    """Full PnL report with all settled trades."""
    init_db()
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    c.execute("""SELECT question, category, entry_no_price, shin_edge, position_size, 
                        outcome, pnl, days_held
                 FROM trades WHERE status='CLOSED' ORDER BY exit_time DESC""")
    trades = c.fetchall()

    if not trades:
        console.print(
            "[cyan]No settled trades yet. Run 'settle' to check for resolved positions.[/cyan]"
        )
        conn.close()
        return

    console.print(Panel("[bold cyan]FULL PnL REPORT[/bold cyan]"))

    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Question", style="white")
    t.add_column("Cat", style="magenta")
    t.add_column("Entry No", justify="right", style="green")
    t.add_column("Edge", justify="right", style="blue")
    t.add_column("Size", justify="right", style="yellow")
    t.add_column("Outcome", style="white")
    t.add_column("PnL", justify="right", style="green")
    t.add_column("Days", justify="right")

    for tr in trades[:50]:
        color = "green" if tr[5] == "WIN" else "red" if tr[5] == "LOSS" else "yellow"
        t.add_row(
            tr[0][:45],
            tr[1],
            f"{tr[2] * 100:.1f}¢",
            f"+{tr[3] * 100:.1f}¢",
            f"${tr[4]:.0f}",
            f"[{color}]{tr[5]}[/{color}]",
            f"${tr[6]:+.2f}",
            f"{tr[7]:.1f}" if tr[7] else "N/A",
        )
    console.print(t)

    if len(trades) > 50:
        console.print(f"  ...and {len(trades) - 50} more")

    # Summary stats
    wins = sum(1 for tr in trades if tr[5] == "WIN")
    losses = sum(1 for tr in trades if tr[5] == "LOSS")
    total = wins + losses
    total_pnl = sum(tr[6] for tr in trades)
    avg_pnl = total_pnl / total if total > 0 else 0

    console.print(f"\n[bold]Summary:[/bold]")
    console.print(f"  Total settled: {total}")
    console.print(f"  Wins: {wins} ({wins / total * 100:.1f}%)")
    console.print(f"  Losses: {losses} ({losses / total * 100:.1f}%)")
    console.print(f"  Total PnL: ${total_pnl:+,.2f}")
    console.print(f"  Avg PnL per trade: ${avg_pnl:+.2f}")

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("Usage: python paper_logger.py [init|scan|settle|status|report]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init_db()
    elif cmd == "scan":
        scan_trades()
    elif cmd == "settle":
        settle_trades()
    elif cmd == "status":
        show_status()
    elif cmd == "report":
        full_report()
