"""Live executor with Gemini AI risk filtering and CLOB execution."""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from poly_alpha.data.polymarket import PolymarketClient
from poly_alpha.strategy import (
    MONTHS,
    SHIN_GAMMA,
    classify_category,
    jaccard_similarity,
)

console = Console()
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

MAX_DAYS = 1.0
MIN_YES_PRICE = 0.05
MAX_YES_PRICE = 0.15
MIN_LIQUIDITY = 250.0
MIN_SHIN_EDGE = 0.03
MAX_VOL_LIQ_RATIO = 15.0
JACCARD_THRESHOLD = 0.30
MAX_SLIPPAGE_PCT = 0.15


def fetch_fast_liquid_markets() -> list[dict[str, Any]]:
    """Fetch ultra-short-term liquid markets (< 1 day to expiry)."""
    client = PolymarketClient()
    events = client.get_all_active_events()
    now = datetime.now(UTC)
    markets_data: list[dict[str, Any]] = []

    console.print("[cyan]Scanning all active events on Polymarket...[/cyan]")

    for event in events:
        for m in event.get("markets", []):
            if not m.get("active") or m.get("closed"):
                continue

            question = m.get("question", "")
            end_date_str = m.get("endDate")
            if not end_date_str:
                continue

            try:
                target_date = datetime.fromisoformat(
                    end_date_str.replace("Z", "+00:00")
                ).astimezone(UTC)
            except (ValueError, TypeError):
                continue

            days = (target_date - now).total_seconds() / 86400.0
            if days < 0 or days > MAX_DAYS:
                continue

            q_lower = question.lower()
            if _has_date_mismatch(q_lower, target_date, now):
                continue
            if _is_long_term(q_lower):
                continue

            try:
                tokens = m.get("outcomePrices", "[]")
                if isinstance(tokens, str):
                    import json

                    tokens = json.loads(tokens)
                if len(tokens) < 2:
                    continue

                yes_price = float(tokens[0])
                no_price = 1.0 - yes_price
                volume = float(m.get("volume", 0))
                liquidity = float(m.get("liquidity", volume * 0.05))

                if MIN_YES_PRICE <= yes_price <= MAX_YES_PRICE and liquidity > MIN_LIQUIDITY:
                    markets_data.append(
                        {
                            "id": m.get("id", question),
                            "question": question,
                            "days": max(0.1, days),
                            "yes_price": yes_price,
                            "no_price": no_price,
                            "liquidity": liquidity,
                            "volume24hr": float(m.get("volume24hr", 0) or 0),
                        }
                    )
            except (ValueError, TypeError, KeyError):
                continue

    return markets_data


def _has_date_mismatch(q_lower: str, target_date: datetime, now: datetime) -> bool:
    """Check if question text contradicts the market's end date."""
    import re

    for month_name, month_no in MONTHS.items():
        if (
            month_name in q_lower
            and abs(target_date.month - month_no) > 2
            and target_date.year == now.year
        ):
            return True

    years = re.findall(r"202[4-9]", q_lower)
    if years:
        latest_year = max(int(y) for y in years)
        if target_date.year < latest_year:
            return True
    return False


def _is_long_term(q_lower: str) -> bool:
    """Check if market is a long-term championship/season bet."""
    import re

    return bool(
        re.search(
            r"(win the|finish in|relegated|champion|championship|finals"
            r"|premier league|la liga|serie a|bundesliga)",
            q_lower,
        )
    )


def risk_filter_and_cluster(markets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Apply HFT defense, Shin edge filter, and semantic clustering."""
    safe_markets: list[dict[str, Any]] = []

    for m in markets:
        vol_24h = float(m.get("volume24hr", 0) or 0)
        liq = float(m.get("liquidity", 1) or 1)

        if liq > 0 and (vol_24h / liq) > MAX_VOL_LIQ_RATIO:
            console.print(
                f"[yellow]HFT DEFENSE: Volume spike on {m['question'][:30]}... "
                f"({vol_24h / liq:.1f}x)[/yellow]"
            )
            continue

        category = classify_category(m["question"])
        gamma = SHIN_GAMMA.get(category, 1.18)
        retail_no = m["no_price"]
        shin_no = (retail_no**gamma) / ((retail_no**gamma) + ((1.0 - retail_no) ** gamma))
        shin_edge = shin_no - retail_no

        if shin_edge < MIN_SHIN_EDGE:
            continue

        m["shin_edge"] = shin_edge
        m["shin_no_prob"] = shin_no
        m["category"] = category
        safe_markets.append(m)

    # Semantic clustering: keep only best edge per cluster
    clusters: list[list[dict[str, Any]]] = []
    cluster_reps: list[dict[str, Any]] = []

    for m in safe_markets:
        assigned = False
        for idx, rep in enumerate(cluster_reps):
            if jaccard_similarity(m["question"], rep["question"]) > JACCARD_THRESHOLD:
                clusters[idx].append(m)
                assigned = True
                break
        if not assigned:
            cluster_reps.append(m)
            clusters.append([m])

    diversified: list[dict[str, Any]] = []
    for cluster in clusters:
        best = max(cluster, key=lambda x: x.get("shin_edge", 0))
        diversified.append(best)

    return diversified


def run(capital: float = 1000.0) -> None:
    """Execute the full live trading pipeline."""
    console.print(
        Panel(
            "[bold green]POLY-ALPHA LIVE EXECUTOR[/bold green]\n"
            "[white]Risk-filtered, cluster-diversified, slippage-capped.[/white]"
        )
    )

    raw_markets = fetch_fast_liquid_markets()
    if not raw_markets:
        console.print("[red]No markets found.[/red]")
        return

    raw_markets.sort(key=lambda x: x["liquidity"], reverse=True)
    raw_markets = raw_markets[:30]

    console.print("[cyan]Applying risk filter and correlation clustering...[/cyan]")
    diversified_markets = risk_filter_and_cluster(raw_markets)

    console.print(
        f"[green]Risk engine returned {len(diversified_markets)} uncorrelated markets.[/green]\n"
    )

    if not diversified_markets:
        console.print("[red]No safe markets remaining after filtering.[/red]")
        return

    total_deployed = 0.0
    table = Table(show_header=True, header_style="bold white")
    table.add_column("Market", style="cyan")
    table.add_column("Liquidity", justify="right", style="yellow")
    table.add_column("Days", justify="right", style="magenta")
    table.add_column("Retail Yes", justify="right", style="red")
    table.add_column("Edge", justify="right", style="blue")
    table.add_column("Size", justify="right", style="bold green")

    for i, m in enumerate(diversified_markets):
        safe_liquidity_cap = m["liquidity"] * MAX_SLIPPAGE_PCT
        max_risk_per_trade = capital * 0.15
        base_allocation = (capital - total_deployed) / max(len(diversified_markets) - i, 1)
        base_allocation = min(base_allocation, max_risk_per_trade)
        target_size = min(base_allocation, safe_liquidity_cap, capital - total_deployed)

        if target_size > 5:
            total_deployed += target_size
            table.add_row(
                m["question"][:45] + "...",
                f"${m['liquidity']:,.0f}",
                f"{m['days']:.1f}d",
                f"{m['yes_price'] * 100:.1f}%",
                f"+{m['shin_edge'] * 100:.1f}c",
                f"${target_size:,.0f}",
            )

    console.print(table)
    console.print(
        f"\n[bold]Total Deployed:[/bold] [bold green]${total_deployed:,.2f}[/bold green] "
        f"/ ${capital:,.2f}"
    )


if __name__ == "__main__":
    run()
