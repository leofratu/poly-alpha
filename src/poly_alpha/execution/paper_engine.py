"""Paper trading engine with SQLite persistence and continuous deployment."""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from datetime import UTC, datetime
from typing import Any

import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from poly_alpha.strategy import (
    StrategyConfig,
    acceleration_config,
    balanced_late_no_config,
    candidate_from_market,
    clean_late_no_config,
    expansion_late_no_config,
    jaccard_similarity,
    paper_reset_sports_core_config,
    quality_expansion_config,
    throughput_late_no_config,
)

console = Console()

DB_FILE = os.environ.get("POLY_ALPHA_DB", os.path.expanduser("~/.poly_alpha/paper_wallet.sqlite"))

GAMMA_API = "https://gamma-api.polymarket.com"
CLOB_API = "https://clob.polymarket.com"
USER_AGENT = "PolyAlpha/1.0"

PRESET = os.environ.get("POLY_ALPHA_PRESET", "strict").lower()

PRESET_MAP: dict[str, StrategyConfig] = {
    "balanced": balanced_late_no_config(),
    "paper_reset": paper_reset_sports_core_config(),
    "throughput": throughput_late_no_config(),
    "expansion": expansion_late_no_config(),
    "quality_expansion": quality_expansion_config(),
    "acceleration": acceleration_config(),
}

CFG = PRESET_MAP.get(PRESET, clean_late_no_config())
POSITION_SIZE_PCT = 0.025


def position_size_pct(candidate: dict[str, Any], deployed_count: int) -> float:
    """Dynamic position sizing based on preset, category, and portfolio fill."""
    market_type = str(candidate.get("market_type", ""))
    category = str(candidate.get("category", ""))
    edge = float(candidate.get("shin_edge", 0.0))

    if PRESET == "balanced":
        if category == "sports" and market_type in {"spread", "total"}:
            return POSITION_SIZE_PCT if deployed_count < 8 else 0.015
        return 0.01

    if PRESET == "throughput":
        return 0.01

    if PRESET == "paper_reset":
        if deployed_count < 10:
            return 0.025 if edge >= 0.035 else 0.02
        return 0.0175 if edge >= 0.03 else 0.015

    if PRESET == "expansion":
        if category == "sports" and market_type in {"spread", "total"}:
            return 0.0125
        return 0.0075

    if PRESET == "quality_expansion":
        if category == "sports" and market_type in {"spread", "total"}:
            return 0.015 if edge >= 0.025 else 0.0125
        if category == "sports" and market_type == "moneyline":
            return 0.0075
        if category in {"politics", "crypto"}:
            return 0.0075
        return 0.005

    if PRESET == "acceleration":
        if category == "sports" and market_type in {"spread", "total"}:
            if deployed_count >= 50:
                return 0.006
            if deployed_count < 25:
                return 0.0125 if edge >= 0.02 else 0.01
            return 0.008
        if category == "sports" and market_type == "moneyline":
            return 0.006 if deployed_count < 50 else 0.0045
        if category in {"politics", "crypto"}:
            return 0.005 if deployed_count < 50 else 0.004
        return 0.004 if deployed_count < 50 else 0.0035

    return POSITION_SIZE_PCT


def available_deploy_budget(
    total_portfolio: float,
    locked: float,
    total_deployed: float,
    free_capital: float,
    max_deploy: float,
) -> float:
    """Cash still deployable under the portfolio cap.

    ``locked`` is capital committed before this run and ``total_deployed`` is what
    this run has committed so far; both count against the cap, while
    ``free_capital`` is the hard cash limit. Subtracting ``total_deployed`` from an
    already-reduced ``free_capital`` would double-count the deployment.
    """
    cap_remaining = total_portfolio * max_deploy - locked - total_deployed
    return max(0.0, min(cap_remaining, free_capital))


def _api_get(url: str, retries: int = 3) -> Any:
    """GET request with retry logic."""
    session = requests.Session()
    session.headers["User-Agent"] = USER_AGENT

    for attempt in range(retries):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except requests.HTTPError as e:
            if e.response is not None and e.response.status_code == 429:
                time.sleep(2 ** (attempt + 2))
            elif attempt < retries - 1:
                time.sleep(2**attempt)
            else:
                raise
        except requests.RequestException:
            if attempt < retries - 1:
                time.sleep(2**attempt)
            else:
                raise
    return None


def fetch_all_active_markets() -> list[dict[str, Any]]:
    """Paginate through all active Polymarket events."""
    all_markets: list[dict[str, Any]] = []
    offset = 0
    while True:
        url = f"{GAMMA_API}/events?closed=false&active=true&limit=1000&offset={offset}"
        events = _api_get(url)
        if not events:
            break
        for event in events:
            all_markets.extend(event.get("markets", []))
        offset += 1000
        time.sleep(0.2)
    return all_markets


def scan_markets(
    all_markets: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Filter and diversify markets using the strategy config."""
    now = datetime.now(UTC)
    all_with_edge: list[dict[str, Any]] = []
    rejected: dict[str, int] = {}

    for m in all_markets:
        candidate, reason = candidate_from_market(m, now, CFG)
        if candidate is None:
            key = reason or "parse_error"
            rejected[key] = rejected.get(key, 0) + 1
        else:
            all_with_edge.append(candidate)

    all_with_edge.sort(key=lambda x: (x["priority"], -x["confidence"]))

    diversified: list[dict[str, Any]] = []
    category_counts: dict[str, int] = {}
    for m in all_with_edge:
        cat = m["category"]
        if category_counts.get(cat, 0) >= CFG.category_limits.get(cat, 10):
            continue
        is_dup = any(
            jaccard_similarity(m["question"], e["question"]) > CFG.jaccard_threshold
            for e in diversified
        )
        if not is_dup:
            diversified.append(m)
            category_counts[cat] = category_counts.get(cat, 0) + 1

    return diversified, rejected


def init_db() -> None:
    """Initialize the SQLite paper wallet database."""
    os.makedirs(os.path.dirname(DB_FILE), exist_ok=True)
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute("CREATE TABLE IF NOT EXISTS wallet (id INTEGER PRIMARY KEY, free_capital REAL)")
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
    conn.close()
    console.print("[green]Paper wallet initialized with $1,000.00.[/green]")


def get_wallet() -> float:
    """Get current free capital."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute("SELECT free_capital FROM wallet WHERE id=1")
    result = c.fetchone()[0]
    conn.close()
    return float(result)


def settle_trades() -> tuple[int, float]:
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

    for pos_id, market_id, investment, shares, _question in open_positions:
        url = f"{GAMMA_API}/markets/{market_id}"
        try:
            m_data = _api_get(url)
        except requests.RequestException:
            continue

        if m_data is None:
            continue

        try:
            uma_status = m_data.get("umaResolutionStatus")
            is_resolved = m_data.get("resolvedBy") or (uma_status == "resolved")
            if not (m_data.get("closed") and is_resolved):
                continue

            prices = json.loads(m_data.get("outcomePrices", "[]"))
            if len(prices) < 2:
                continue

            yes_final = float(prices[0])
            no_final = float(prices[1])

            if no_final >= 0.999:
                payout = shares * 1.0
                pnl = payout - investment
            elif yes_final >= 0.999:
                payout = 0.0
                pnl = -investment
            else:
                continue

            free_capital += payout
            total_pnl += pnl
            settled_count += 1

            c.execute(
                "UPDATE positions SET status='CLOSED', payout=?, pnl=? WHERE id=?",
                (payout, pnl, pos_id),
            )
        except (json.JSONDecodeError, ValueError, KeyError):
            continue

    if settled_count > 0:
        c.execute("UPDATE wallet SET free_capital = ? WHERE id=1", (free_capital,))
        conn.commit()

    conn.close()
    return settled_count, total_pnl


def deploy_trades() -> None:
    """Deploy new trades up to the configured maximum slot count."""
    console.print(
        Panel(
            f"[bold green]POLY-ALPHA CONTINUOUS DEPLOYMENT[/bold green]\n"
            f"[white]Preset: {PRESET} | max slots: {CFG.max_positions} "
            f"| deploy cap: {CFG.max_portfolio_deploy:.0%}[/white]"
        )
    )

    settled, pnl = settle_trades()
    if settled > 0:
        console.print(f"[green]Settled {settled} trades. PnL: ${pnl:+,.2f}[/green]")

    console.print("[cyan]Scanning ALL active markets...[/cyan]")
    all_markets = fetch_all_active_markets()
    console.print(f"[green]Scanned {len(all_markets):,} markets[/green]")

    candidates, _rejected = scan_markets(all_markets)
    console.print(f"[green]Found {len(candidates)} markets with positive edge[/green]")

    if not candidates:
        console.print("[red]No markets found.[/red]")
        return

    _display_top_candidates(candidates[:20])

    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()
    c.execute("SELECT market_id FROM positions WHERE status='OPEN'")
    active_ids = {r[0] for r in c.fetchall()}
    c.execute("SELECT COUNT(*) FROM positions WHERE status='OPEN'")
    active_count: int = c.fetchone()[0]
    c.execute("SELECT COALESCE(SUM(investment), 0) FROM positions WHERE status='OPEN'")
    locked: float = c.fetchone()[0]

    free_capital = get_wallet()
    total_portfolio = free_capital + locked

    console.print("\n[bold]Current state:[/bold]")
    console.print(f"  Active positions: {active_count}/{CFG.max_positions}")
    console.print(f"  Free capital: ${free_capital:,.2f}")
    console.print(f"  Locked: ${locked:,.2f}")

    total_deployed = 0.0
    deployed_count = 0

    for m in candidates[: CFG.max_positions]:
        if active_count >= CFG.max_positions:
            break
        if m["id"] in active_ids:
            continue

        c.execute("SELECT question FROM positions WHERE status='OPEN'")
        is_dup = any(
            jaccard_similarity(m["question"], row[0]) > CFG.jaccard_threshold
            for row in c.fetchall()
        )
        if is_dup:
            continue

        target_size = max(
            CFG.min_trade_size,
            total_portfolio * position_size_pct(m, deployed_count),
        )
        budget = available_deploy_budget(
            total_portfolio,
            locked,
            total_deployed,
            free_capital,
            CFG.max_portfolio_deploy,
        )
        target_size = min(target_size, budget)
        if target_size < CFG.min_trade_size:
            break

        fill = _simulate_clob_fill(m, target_size)
        if fill is None:
            continue

        total_cost, total_shares, actual_entry_no = fill

        c.execute(
            """INSERT INTO positions
               (market_id, question, entry_time, entry_no_price, investment, shares, status, payout, pnl)
               VALUES (?, ?, ?, ?, ?, ?, 'OPEN', 0.0, 0.0)""",
            (
                m["id"],
                m["question"],
                datetime.now(UTC).timestamp(),
                actual_entry_no,
                total_cost,
                total_shares,
            ),
        )
        free_capital -= total_cost
        c.execute("UPDATE wallet SET free_capital = ? WHERE id=1", (free_capital,))
        conn.commit()
        total_deployed += total_cost
        active_count += 1
        deployed_count += 1
        console.print(
            f"[green]DEPLOYED #{deployed_count}:[/green] {m['question'][:45]}... "
            f"| ${total_cost:.2f} | No: {actual_entry_no * 100:.1f}c "
            f"| Edge: +{m['shin_edge'] * 100:.1f}c"
        )
        time.sleep(0.5)

    conn.close()

    if total_deployed > 0:
        console.print(
            f"\n[bold green]Deployed ${total_deployed:.2f} into {deployed_count} positions.[/bold green]"
        )
    else:
        console.print("[yellow]No new positions deployed.[/yellow]")


def _simulate_clob_fill(
    candidate: dict[str, Any], target_size: float
) -> tuple[float, float, float] | None:
    """Walk the L2 order book to simulate a fill. Returns (cost, shares, avg_price) or None."""
    market_id = candidate["id"]
    try:
        m_data = _api_get(f"{GAMMA_API}/markets/{market_id}")
        if not m_data:
            return None

        prices = json.loads(m_data.get("outcomePrices", "[]"))
        clob_raw = m_data.get("clobTokenIds", "[]")
        clob_tokens = json.loads(clob_raw) if isinstance(clob_raw, str) else clob_raw

        if len(prices) < 2 or len(clob_tokens) < 2:
            return None

        idx = 0 if float(prices[0]) > float(prices[1]) else 1
        token_id = clob_tokens[idx]
        retail_no = float(prices[idx])

        ob_data = _api_get(f"{CLOB_API}/book?token_id={token_id}")
        if not ob_data:
            return None

        asks = sorted(ob_data.get("asks", []), key=lambda x: float(x["price"]))

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

        if total_cost < target_size * 0.50:
            if asks:
                best_ask = float(asks[0]["price"])
                best_size = float(asks[0]["size"])
                if best_ask <= retail_no * 1.05:
                    total_cost = best_ask * min(best_size, target_size / best_ask)
                    total_shares = min(best_size, target_size / best_ask)
                    if total_cost < CFG.min_trade_size:
                        return None
                elif CFG.allow_synthetic_retail_fill:
                    total_cost = target_size
                    total_shares = target_size / max(retail_no, 0.01)
                else:
                    return None
            elif CFG.allow_synthetic_retail_fill:
                total_cost = target_size
                total_shares = target_size / max(retail_no, 0.01)
            else:
                return None

        actual_entry_no = total_cost / total_shares if total_shares > 0 else retail_no
        return total_cost, total_shares, actual_entry_no

    except (requests.RequestException, json.JSONDecodeError, ValueError, KeyError):
        return None


def status() -> None:
    """Display current portfolio status."""
    conn = sqlite3.connect(DB_FILE, timeout=10)
    c = conn.cursor()

    c.execute("SELECT free_capital FROM wallet WHERE id=1")
    free_capital: float = c.fetchone()[0]

    c.execute("SELECT investment FROM positions WHERE status='OPEN'")
    open_positions = c.fetchall()
    locked = sum(p[0] for p in open_positions)
    total_value = free_capital + locked

    c.execute("SELECT COALESCE(SUM(pnl), 0) FROM positions WHERE status='CLOSED'")
    realized: float = c.fetchone()[0]
    conn.close()

    console.print(Panel("[bold cyan]PORTFOLIO STATUS[/bold cyan]"))
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Metric", style="cyan")
    t.add_column("Value", justify="right", style="yellow")
    t.add_row("Total Value", f"[bold green]${total_value:,.2f}[/bold green]")
    t.add_row("Free Capital", f"${free_capital:,.2f}")
    t.add_row("Locked", f"${locked:,.2f}")
    t.add_row("Active Positions", f"{len(open_positions)}/{CFG.max_positions}")
    color = "green" if realized >= 0 else "red"
    t.add_row("Realized PnL", f"[{color}]${realized:+,.2f}[/{color}]")
    console.print(t)


def _display_top_candidates(candidates: list[dict[str, Any]]) -> None:
    """Print a Rich table of top candidates."""
    console.print("\n[bold cyan]Top Alpha Opportunities:[/bold cyan]")
    t = Table(show_header=True, header_style="bold green")
    t.add_column("#", style="cyan")
    t.add_column("Cat", style="magenta")
    t.add_column("Question", style="white")
    t.add_column("Yes", justify="right", style="red")
    t.add_column("No", justify="right", style="green")
    t.add_column("Edge", justify="right", style="blue")
    t.add_column("Days", justify="right")

    for i, m in enumerate(candidates):
        t.add_row(
            str(i + 1),
            m["category"],
            m["question"][:50],
            f"{m['yes_price'] * 100:.1f}c",
            f"{m['no_price'] * 100:.1f}c",
            f"+{m['shin_edge'] * 100:.1f}c",
            f"{m['days']:.1f}",
        )
    console.print(t)


def main() -> None:
    """CLI entry point."""
    if len(sys.argv) < 2:
        console.print(
            "Usage: python -m poly_alpha.execution.paper_engine [init|deploy|status|step]"
        )
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
    else:
        console.print(f"[red]Unknown command: {cmd}[/red]")
        sys.exit(1)


if __name__ == "__main__":
    main()
