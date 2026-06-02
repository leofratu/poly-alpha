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
import sqlite3
import os
import sys
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from strategy_core import (
    candidate_from_market,
    balanced_late_no_config,
    clean_late_no_config,
    paper_reset_sports_core_config,
    throughput_late_no_config,
    expansion_late_no_config,
    quality_expansion_config,
    acceleration_config,
    jaccard_similarity,
)

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
PRESET = os.environ.get("POLY_ALPHA_PRESET", "strict").lower()
if PRESET == "balanced":
    CFG = balanced_late_no_config()
elif PRESET == "paper_reset":
    CFG = paper_reset_sports_core_config()
elif PRESET == "throughput":
    CFG = throughput_late_no_config()
elif PRESET == "expansion":
    CFG = expansion_late_no_config()
elif PRESET == "quality_expansion":
    CFG = quality_expansion_config()
elif PRESET == "acceleration":
    CFG = acceleration_config()
else:
    CFG = clean_late_no_config()
POSITION_SIZE_PCT = 0.025


def position_size_pct(candidate: dict[str, object], deployed_count: int) -> float:
    """Use smaller overflow sizing in broader presets so throughput can increase without breaking bankroll math."""
    if PRESET == "balanced":
        market_type = str(candidate.get("market_type", ""))
        category = str(candidate.get("category", ""))
        if category == "sports" and market_type in {"spread", "total"} and deployed_count < 8:
            return POSITION_SIZE_PCT
        if category == "sports" and market_type in {"spread", "total"}:
            return 0.015
        return 0.01
    if PRESET == "throughput":
        return 0.01
    if PRESET == "paper_reset":
        edge = float(candidate.get("shin_edge", 0.0))
        if deployed_count < 10:
            return 0.025 if edge >= 0.035 else 0.02
        return 0.0175 if edge >= 0.03 else 0.015
    if PRESET == "expansion":
        market_type = str(candidate.get("market_type", ""))
        category = str(candidate.get("category", ""))
        if category == "sports" and market_type in {"spread", "total"}:
            return 0.0125
        return 0.0075
    if PRESET == "quality_expansion":
        market_type = str(candidate.get("market_type", ""))
        category = str(candidate.get("category", ""))
        edge = float(candidate.get("shin_edge", 0.0))
        if category == "sports" and market_type in {"spread", "total"}:
            return 0.015 if edge >= 0.025 else 0.0125
        if category == "sports" and market_type == "moneyline":
            return 0.0075
        if category in {"politics", "crypto"}:
            return 0.0075
        return 0.005
    if PRESET == "acceleration":
        market_type = str(candidate.get("market_type", ""))
        category = str(candidate.get("category", ""))
        edge = float(candidate.get("shin_edge", 0.0))
        if category == "sports" and market_type in {"spread", "total"}:
            if deployed_count >= 50:
                return 0.006
            if deployed_count < 25:
                return 0.0125 if edge >= 0.02 else 0.01
            return 0.008
        if category == "sports" and market_type == "moneyline":
            if deployed_count >= 50:
                return 0.0045
            return 0.006
        if category in {"politics", "crypto"}:
            if deployed_count >= 50:
                return 0.004
            return 0.005
        if deployed_count >= 50:
            return 0.0035
        return 0.004
    return POSITION_SIZE_PCT


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
    """Find filtered, diversified markets for the clean late-expiry No-side profile."""
    now = datetime.now(timezone.utc)
    all_with_edge = []
    rejected = {}

    for m in all_markets:
        candidate, reason = candidate_from_market(m, now, CFG)
        if candidate is None:
            rejected[reason or "parse_error"] = rejected.get(reason or "parse_error", 0) + 1
            continue
        all_with_edge.append(candidate)

    # Priority first, confidence second
    all_with_edge.sort(key=lambda x: (x["priority"], -x["confidence"]))

    # Dedup + category caps
    diversified = []
    category_counts = {}
    for m in all_with_edge:
        cat = m["category"]
        if category_counts.get(cat, 0) >= CFG.category_limits.get(cat, 10):
            continue
        dup = False
        for e in diversified:
            if jaccard_similarity(m["question"], e["question"]) > CFG.jaccard_threshold:
                dup = True
                break
        if not dup:
            diversified.append(m)
            category_counts[cat] = category_counts.get(cat, 0) + 1

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
    """Deploy new trades up to the configured maximum slot count."""
    console.print(
        Panel(
            "[bold green]POLY-ALPHA CONTINUOUS DEPLOYMENT[/bold green]\n"
            f"[white]Preset: {PRESET} | max slots: {CFG.max_positions} | deploy cap: {CFG.max_portfolio_deploy:.0%}[/white]\n"
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
    console.print(f"  Active positions: {active_count}/{CFG.max_positions}")
    console.print(f"  Free capital: ${free_capital:,.2f}")
    console.print(f"  Locked: ${locked:,.2f}")

    # Deploy new trades
    total_deployed = 0.0
    deployed_count = 0

    for m in candidates[: CFG.max_positions]:
        if active_count >= CFG.max_positions:
            break

        if m["id"] in active_ids:
            continue

        # Correlation check
        dup = False
        c.execute("SELECT question FROM positions WHERE status='OPEN'")
        for row in c.fetchall():
            if jaccard_similarity(m["question"], row[0]) > CFG.jaccard_threshold:
                dup = True
                break
        if dup:
            continue

        target_size = max(CFG.min_trade_size, total_portfolio * position_size_pct(m, deployed_count))
        available_budget = (free_capital * CFG.max_portfolio_deploy) - total_deployed
        target_size = min(target_size, available_budget, free_capital - total_deployed)
        if target_size < CFG.min_trade_size:
            break

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
                            if total_cost < CFG.min_trade_size:
                                continue
                        else:
                            if CFG.allow_synthetic_retail_fill:
                                total_cost = target_size
                                total_shares = target_size / max(retail_no, 0.01)
                            else:
                                continue
                    else:
                        if CFG.allow_synthetic_retail_fill:
                            total_cost = target_size
                            total_shares = target_size / max(retail_no, 0.01)
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
