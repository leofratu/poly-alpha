"""
POLY-ALPHA FORWARD TEST TRACKER
Records 1,136 markets expiring within 7 days.
Checks resolutions daily. Calculates REAL PnL.
No simulations. No assumptions. Real outcomes.
"""

import json
import urllib.request
import urllib.error
import ssl
import time
import sqlite3
import os
import sys
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
    "POLY_ALPHA_TRACKER_DB", os.path.expanduser("~/.poly_alpha/forward_test.sqlite")
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
    c.execute("""CREATE TABLE IF NOT EXISTS tracked_markets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        market_id TEXT UNIQUE,
        condition_id TEXT,
        question TEXT,
        category TEXT,
        recorded_time REAL,
        expiry_time REAL,
        days_to_expiry REAL,
        yes_price REAL,
        no_price REAL,
        shin_no_prob REAL,
        shin_edge REAL,
        volume REAL,
        liquidity REAL,
        status TEXT DEFAULT 'TRACKING',
        resolved_time REAL,
        final_yes_price REAL,
        final_no_price REAL,
        outcome TEXT,
        pnl REAL
    )""")
    conn.commit()
    conn.close()


def record_markets(markets):
    """Record markets for forward tracking."""
    init_db()
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    now = datetime.now(timezone.utc).timestamp()
    recorded = 0

    for m in markets:
        try:
            cat = classify_category(m["question"])
            shin_no = shin_debiasing(m["no_price"], cat)
            shin_edge = shin_no - m["no_price"]

            expiry_ts = None
            if m.get("days") is not None:
                expiry_ts = now + (m["days"] * 86400)

            c.execute(
                """INSERT OR IGNORE INTO tracked_markets 
                (market_id, condition_id, question, category, recorded_time, 
                 expiry_time, days_to_expiry, yes_price, no_price, 
                 shin_no_prob, shin_edge, volume, liquidity, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'TRACKING')""",
                (
                    m["id"],
                    m.get("condition_id", ""),
                    m["question"],
                    cat,
                    now,
                    expiry_ts,
                    m.get("days"),
                    m["yes_price"],
                    m["no_price"],
                    shin_no,
                    shin_edge,
                    m.get("volume", 0),
                    m.get("liquidity", 0),
                ),
            )

            if c.rowcount > 0:
                recorded += 1
        except:
            continue

    conn.commit()
    conn.close()
    return recorded


import concurrent.futures


def check_resolutions():
    """Check all tracking markets for resolution."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    c.execute(
        "SELECT id, market_id, condition_id, question, no_price, shin_no_prob FROM tracked_markets WHERE status='TRACKING'"
    )
    tracking = c.fetchall()

    if not tracking:
        console.print("[cyan]No markets currently tracking.[/cyan]")
        conn.close()
        return

    console.print(
        f"[cyan]Checking {len(tracking)} tracking markets for resolutions...[/cyan]"
    )

    def check_one(row):
        track_id, market_id, condition_id, question, no_price, shin_no = row
        for cid in [market_id, condition_id]:
            if not cid:
                continue
            try:
                url = f"https://gamma-api.polymarket.com/markets/{cid}"
                req = urllib.request.Request(
                    url, headers={"User-Agent": "PolyAlpha/1.0"}
                )
                with urllib.request.urlopen(
                    req, timeout=8, context=ssl_context
                ) as resp:
                    m = json.loads(resp.read().decode())
                    if isinstance(m, dict):
                        uma = m.get("umaResolutionStatus", "")
                        if m.get("closed") and (
                            m.get("resolvedBy") or uma == "resolved"
                        ):
                            prices = json.loads(m.get("outcomePrices", "[]"))
                            if len(prices) >= 2:
                                yes_final = float(prices[0])
                                no_final = float(prices[1])

                                if no_final >= 0.999:
                                    outcome = "WIN"
                                    shares = 20.0 / no_price
                                    pnl = shares * 1.0 - 20.0
                                elif yes_final >= 0.999:
                                    outcome = "LOSS"
                                    pnl = -20.0
                                else:
                                    return None

                                return (
                                    track_id,
                                    datetime.now(timezone.utc).timestamp(),
                                    yes_final,
                                    no_final,
                                    outcome,
                                    pnl,
                                )
            except:
                continue
        return None

    # Use thread pool for parallel resolution checks
    resolved_results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=30) as executor:
        future_to_row = {executor.submit(check_one, row): row for row in tracking}
        for future in concurrent.futures.as_completed(future_to_row):
            result = future.result()
            if result:
                resolved_results.append(result)

    # Update database
    for r in resolved_results:
        track_id, resolved_time, yes_final, no_final, outcome, pnl = r
        c.execute(
            """UPDATE tracked_markets SET 
            status='RESOLVED', resolved_time=?, 
            final_yes_price=?, final_no_price=?, 
            outcome=?, pnl=?
            WHERE id=?""",
            (resolved_time, yes_final, no_final, outcome, pnl, track_id),
        )

    conn.commit()
    conn.close()

    if resolved_results:
        console.print(f"[green]Resolved {len(resolved_results)} new markets![/green]")
        wins = sum(1 for r in resolved_results if r[4] == "WIN")
        losses = sum(1 for r in resolved_results if r[4] == "LOSS")
        pnl = sum(r[5] for r in resolved_results)
        console.print(f"  Wins: {wins}, Losses: {losses}, PnL: ${pnl:+,.2f}")
    else:
        console.print("[cyan]No new resolutions yet.[/cyan]")


def show_status():
    """Show tracking status."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    c.execute("SELECT COUNT(*) FROM tracked_markets WHERE status='TRACKING'")
    tracking = c.fetchone()[0]

    c.execute(
        "SELECT COUNT(*) FROM tracked_markets WHERE status='RESOLVED' AND outcome='WIN'"
    )
    wins = c.fetchone()[0]

    c.execute(
        "SELECT COUNT(*) FROM tracked_markets WHERE status='RESOLVED' AND outcome='LOSS'"
    )
    losses = c.fetchone()[0]

    c.execute("SELECT SUM(pnl) FROM tracked_markets WHERE status='RESOLVED'")
    total_pnl = c.fetchone()[0] or 0.0

    c.execute("SELECT AVG(shin_no_prob) FROM tracked_markets WHERE status='TRACKING'")
    avg_shin = c.fetchone()[0] or 0

    resolved = wins + losses
    win_rate = wins / resolved * 100 if resolved > 0 else 0

    console.print(Panel("[bold cyan]FORWARD TEST STATUS[/bold cyan]"))
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right", style="yellow")
    t.add_row("Tracking", str(tracking))
    t.add_row("Resolved", str(resolved))
    t.add_row("Wins", f"[green]{wins}[/green]")
    t.add_row("Losses", f"[red]{losses}[/red]")
    t.add_row("Win Rate", f"{win_rate:.1f}%" if resolved > 0 else "N/A")
    t.add_row(
        "Total PnL ($20/pos)",
        f"[{'green' if total_pnl >= 0 else 'red'}]${total_pnl:+,.2f}[/{'green' if total_pnl >= 0 else 'red'}]",
    )
    t.add_row("Avg Shin No Prob", f"{avg_shin * 100:.1f}%")
    console.print(t)

    # Show recent resolutions
    c.execute("""SELECT question, category, no_price, shin_no_prob, outcome, pnl 
                 FROM tracked_markets WHERE status='RESOLVED' ORDER BY resolved_time DESC LIMIT 20""")
    recent = c.fetchall()

    if recent:
        console.print(f"\n[bold]Recent Resolutions:[/bold]")
        rt = Table(show_header=True, header_style="bold white")
        rt.add_column("Question", style="cyan")
        rt.add_column("Cat", style="magenta")
        rt.add_column("No Entry", justify="right", style="green")
        rt.add_column("Shin", justify="right", style="blue")
        rt.add_column("Outcome", style="white")
        rt.add_column("PnL", justify="right", style="green")

        for r in recent:
            color = "green" if r[4] == "WIN" else "red"
            rt.add_row(
                r[0][:50],
                r[1],
                f"{r[2] * 100:.1f}¢",
                f"{r[3] * 100:.1f}%",
                f"[{color}]{r[4]}[/{color}]",
                f"${r[5]:+.2f}",
            )
        console.print(rt)

    conn.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        console.print("Usage: python tracker.py [init|record|check|status]")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "init":
        init_db()
        console.print("[green]Database initialized.[/green]")
    elif cmd == "record":
        # Load markets from the scan
        with open("/tmp/all_target_markets.json", "r") as fp:
            all_targets = json.load(fp)

        # Record all markets expiring within 7 days
        expiring_7d = [
            m for m in all_targets if m.get("days") is not None and 0 < m["days"] <= 7
        ]
        recorded = record_markets(expiring_7d)
        console.print(f"[green]Recorded {recorded} new markets for tracking.[/green]")
    elif cmd == "check":
        check_resolutions()
    elif cmd == "status":
        show_status()
