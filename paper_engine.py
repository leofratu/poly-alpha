import sqlite3
import json
import urllib.request
import time
import numpy as np
from datetime import datetime, timezone
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import sys
import os
import re

from ultimate_executor import fetch_fast_liquid_markets, ai_risk_and_clustering

console = Console()
DB_FILE = os.environ.get(
    "POLY_ALPHA_DB", os.path.expanduser("~/.poly_alpha/paper_wallet.sqlite")
)


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


def update_wallet(new_balance):
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute("UPDATE wallet SET free_capital = ? WHERE id=1", (new_balance,))
    conn.commit()


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
                with urllib.request.urlopen(req) as resp:
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
                        f"[bold red]SETTLEMENT FAILED (HTTP {e.code} after 3 retries): {question} | Market ID: {market_id}[/bold red]"
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


def jaccard_similarity(s1, s2):
    set1 = set(s1.lower().split())
    set2 = set(s2.lower().split())
    union = set1.union(set2)
    if not union:
        return 0.0
    return len(set1.intersection(set2)) / len(union)


def classify_category(question):
    q_lower = question.lower()
    if any(
        w in q_lower
        for w in ["bitcoin", "ethereum", "solana", "xrp", "crypto", "btc", "eth"]
    ):
        return "crypto"
    elif any(
        w in q_lower
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
    elif any(
        w in q_lower
        for w in ["trump", "election", "cabinet", "strike", "war", "congress", "senate"]
    ):
        return "politics"
    elif any(
        w in q_lower for w in ["temperature", "weather", "snow", "rain", "hurricane"]
    ):
        return "weather"
    else:
        return "other"


def trade():
    import urllib.request, json

    def shin_debiasing(p_market, question_text):
        q_lower = question_text.lower()

        if any(
            w in q_lower for w in ["bitcoin", "ethereum", "solana", "xrp", "crypto"]
        ):
            gamma = 1.30
        elif any(
            w in q_lower for w in ["win on", "vs.", "o/u", "ncaa", "fc", "championship"]
        ):
            gamma = 1.20
        elif any(w in q_lower for w in ["temperature", "weather", "snow"]):
            gamma = 1.15
        elif any(
            w in q_lower for w in ["trump", "election", "cabinet", "strike", "war"]
        ):
            gamma = 1.05
        else:
            gamma = 1.18

        return (p_market**gamma) / ((p_market**gamma) + ((1.0 - p_market) ** gamma))

    free_capital = get_wallet()
    if free_capital < 10.0:
        console.print("[red]Insufficient free capital to trade.[/red]")
        return

    console.print(
        f"[cyan]Hunting for Alpha... Available Free Capital: ${free_capital:,.2f}[/cyan]"
    )

    raw_markets = fetch_fast_liquid_markets()
    if not raw_markets:
        return
    raw_markets.sort(key=lambda x: x["liquidity"], reverse=True)
    raw_markets = raw_markets[:1000]

    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute("SELECT market_id FROM positions WHERE status='OPEN'")
    active_ids = [r[0] for r in c.fetchall()]

    new_markets = [m for m in raw_markets if m["id"] not in active_ids]
    if not new_markets:
        console.print(
            "[yellow]No new safe markets available. Portfolio is fully deployed.[/yellow]"
        )
        return

    analyzed_markets = ai_risk_and_clustering(new_markets)
    safe_markets = [m for m in analyzed_markets if m.get("ai_risk", 1.0) <= 0.20]

    diversified_markets = []
    seen_clusters = set()
    for m in safe_markets:
        cluster = m.get("cluster", m["id"])
        if cluster not in seen_clusters:
            diversified_markets.append(m)
            seen_clusters.add(cluster)

    if not diversified_markets:
        console.print("[red]No uncorrelated markets passed the Tail-Risk filter.[/red]")
        return

    for m in diversified_markets:
        retail_no = m["no_price"]
        true_no_prob = shin_debiasing(retail_no, m["question"])
        m["shin_no_prob"] = true_no_prob
        m["shin_edge"] = true_no_prob - retail_no

    diversified_markets = [m for m in diversified_markets if m["shin_edge"] >= 0.03]

    diversified_markets.sort(
        key=lambda m: (m["shin_edge"] * m["liquidity"]) / max(m["days"], 0.1),
        reverse=True,
    )
    diversified_markets = diversified_markets[:10]

    if not diversified_markets:
        console.print("[red]No markets with sufficient Shin edge (>= 3¢).[/red]")
        return

    total_deployed = 0.0
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

    category_limits = {
        "sports": 8,
        "crypto": 8,
        "politics": 5,
        "weather": 5,
        "other": 10,
    }

    for m in diversified_markets:
        if active_count >= 50:
            console.print(
                "[yellow]Portfolio is fully deployed (50 positions max).[/yellow]"
            )
            break

        cat = classify_category(m["question"])
        if category_counts.get(cat, 0) >= category_limits.get(cat, 10):
            console.print(
                f"[yellow]Category limit reached for '{cat}' ({category_counts[cat]}/{category_limits.get(cat, 10)}). Skipping.[/yellow]"
            )
            continue

        duplicate_found = False
        c.execute("SELECT question FROM positions WHERE status='OPEN'")
        for row in c.fetchall():
            if jaccard_similarity(m["question"], row[0]) > 0.3:
                duplicate_found = True
                break
        if duplicate_found:
            continue

        target_size = total_portfolio_value * 0.02
        target_size = min(target_size, free_capital - total_deployed)

        if target_size >= 19.5:
            market_id = m["id"]

            url = f"https://gamma-api.polymarket.com/markets/{market_id}"
            req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
            try:
                with urllib.request.urlopen(req) as resp:
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
                    with urllib.request.urlopen(clob_req) as clob_resp:
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
                        max_shares_we_can_buy_here = capital_needed / price

                        shares_to_buy = min(size, max_shares_we_can_buy_here)
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
                        f"[green]DEPLOYED (L2 FILLED):[/green] {m['question'][:45]}... | Size: ${total_cost:.2f} | Avg Price: {actual_entry_no * 100:.1f}¢ | Edge: {m['shin_edge'] * 100:.1f}¢"
                    )

                    time.sleep(1.0)

            except Exception as e:
                console.print(f"[yellow]Skipped (API Error): {e}[/yellow]")
                continue

    if total_deployed > 0:
        console.print(
            f"[bold green]Successfully locked ${total_deployed:,.2f} into true L2-verified favorites.[/bold green]"
        )


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
