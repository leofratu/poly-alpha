from __future__ import annotations

import argparse
import json
import math
import os
import ssl
import time
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from paper_alpha import (
    DEFAULT_PAPER_ALPHA,
    estimate_paper_true_no,
    is_paper_candidate,
)
from strategy_core import (
    CATEGORY_PRIORITY,
    classify_category,
    jaccard_similarity,
)

console = Console()

ssl_ctx = ssl.create_default_context()
ssl_ctx.check_hostname = False
ssl_ctx.verify_mode = ssl.CERT_NONE

SNAPSHOT_DIR = Path("data/agent/snapshots")
HISTORY_FILE = Path("data/agent/history.jsonl")


@dataclass(frozen=True)
class AgentConfig:
    capital: float = 1000.0
    model: str = "paper"
    min_days: float = 0.0
    max_days: float = 14.0
    min_liquidity: float = 500.0
    min_volume: float = 100.0
    min_edge: float = 0.05
    max_position_pct: float = 0.02
    kelly_fraction: float = 0.25
    cash_reserve_pct: float = 0.25
    max_category_pct: float = 0.20
    correlation_threshold: float = 0.55
    max_markets_per_cluster: int = 1
    top_n: int = 15
    max_events_per_page: int = 1000
    max_pages: int = 20
    fetch_pause_s: float = 0.15
    price_improvement_ticks: float = 0.01
    min_order_size: float = 5.0
    max_order_size: float = 50.0
    max_size_as_pct_of_liquidity: float = 0.05


@dataclass
class MarketView:
    market_id: str
    event_id: str
    question: str
    category: str
    outcomes: list[str]
    probs: list[float]
    est_probs: list[float]
    chosen_index: int
    side_label: str
    market_prob: float
    est_prob: float
    edge: float
    ev_stake: float
    kelly_fraction: float
    limit_price: float
    expected_fill_price: float
    liquidity: float
    volume: float
    volume24hr: float
    days_remaining: float
    pct_elapsed: float
    confidence: float
    token_ids: list[str]


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def api_request(url: str, retries: int = 3) -> Any:
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "PolyAlphaAgent/1.0"})
            with urllib.request.urlopen(req, timeout=30, context=ssl_ctx) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as exc:
            if exc.code == 429 and attempt < retries - 1:
                time.sleep(2 ** (attempt + 1))
                continue
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(2**attempt)
                continue
            raise


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def normalize_probs(values: list[float]) -> list[float]:
    total = sum(max(v, 0.0) for v in values)
    if total <= 0:
        return []
    return [max(v, 0.0) / total for v in values]


def power_debias(probs: list[float], gamma: float) -> list[float]:
    adjusted = [p**gamma for p in probs]
    return normalize_probs(adjusted)


def category_gamma(category: str) -> float:
    return {
        "politics": 1.04,
        "crypto": 1.18,
        "weather": 1.10,
        "esports": 1.12,
        "sports": 1.10,
        "other": 1.12,
    }.get(category, 1.10)


def lifecycle_bias(pct_elapsed: float) -> float:
    if pct_elapsed <= 20.0:
        return 0.020
    if pct_elapsed <= 50.0:
        return 0.010
    if pct_elapsed <= 85.0:
        return 0.000
    return -0.010


def froth_penalty(volume24hr: float, liquidity: float) -> float:
    if liquidity <= 0:
        return 0.0
    ratio = volume24hr / liquidity
    return clamp(max(ratio - 3.0, 0.0) * 0.0025, 0.0, 0.02)


def estimate_true_probs(
    market_probs: list[float],
    category: str,
    pct_elapsed: float,
    volume24hr: float,
    liquidity: float,
) -> list[float]:
    base = power_debias(market_probs, category_gamma(category))
    if not base:
        return []
    favorite_idx = max(range(len(base)), key=base.__getitem__)
    bonus = lifecycle_bias(pct_elapsed) - froth_penalty(volume24hr, liquidity)
    adjusted = base[:]
    adjusted[favorite_idx] = clamp(adjusted[favorite_idx] + bonus, 0.01, 0.99)
    remainder = 1.0 - adjusted[favorite_idx]
    other_total = sum(base[i] for i in range(len(base)) if i != favorite_idx)
    if other_total <= 0:
        return normalize_probs(adjusted)
    for idx, base_prob in enumerate(base):
        if idx == favorite_idx:
            continue
        adjusted[idx] = remainder * (base_prob / other_total)
    return normalize_probs(adjusted)


def expected_value_on_stake(true_prob: float, price: float) -> float:
    if price <= 0 or price >= 1:
        return -1.0
    return (true_prob / price) - 1.0


def fractional_kelly(true_prob: float, price: float, fraction: float, cap: float) -> float:
    if price <= 0 or price >= 1 or true_prob <= 0 or true_prob >= 1:
        return 0.0
    b = (1.0 - price) / price
    raw = ((b * true_prob) - (1.0 - true_prob)) / b
    return clamp(max(0.0, raw) * fraction, 0.0, cap)


def load_token_ids(market: dict[str, Any]) -> list[str]:
    raw = market.get("clobTokenIds", [])
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except Exception:
            return []
        return [str(x) for x in parsed]
    if isinstance(raw, list):
        return [str(x) for x in raw]
    return []


def parse_market(market: dict[str, Any], now: datetime, cfg: AgentConfig) -> MarketView | None:
    if market.get("closed") or not market.get("active"):
        return None

    question = market.get("question", "")
    end_date = parse_dt(market.get("endDate"))
    if not question or end_date is None:
        return None

    created_at = parse_dt(market.get("createdAt"))
    days_remaining = (end_date - now).total_seconds() / 86400.0
    if days_remaining < cfg.min_days or days_remaining > cfg.max_days:
        return None

    try:
        outcomes = json.loads(market.get("outcomes", "[]"))
        raw_probs = json.loads(market.get("outcomePrices", "[]"))
    except Exception:
        return None

    if len(outcomes) != 2 or len(raw_probs) != 2:
        return None

    try:
        probs = normalize_probs([float(raw_probs[0]), float(raw_probs[1])])
    except Exception:
        return None

    if len(probs) != 2 or min(probs) <= 0.0:
        return None

    volume = float(market.get("volume", 0) or 0)
    liquidity = float(market.get("liquidity", 0) or 0)
    volume24hr = float(market.get("volume24hr", 0) or 0)
    if volume < cfg.min_volume or liquidity < cfg.min_liquidity:
        return None

    if created_at is not None and end_date > created_at:
        total_life = (end_date - created_at).total_seconds()
        pct_elapsed = clamp(
            (now - created_at).total_seconds() / total_life * 100.0,
            0.0,
            100.0,
        )
    else:
        pct_elapsed = 50.0

    category = classify_category(question)
    if cfg.model == "paper":
        yes_price = probs[0]
        no_price = probs[1]
        if not is_paper_candidate(
            yes_price=yes_price,
            no_price=no_price,
            pct_elapsed=pct_elapsed / 100.0,
            days_remaining=days_remaining,
            liquidity=liquidity,
            volume=volume,
            volume_24h=volume24hr,
            spec=DEFAULT_PAPER_ALPHA,
        ):
            return None
        true_no = estimate_paper_true_no(no_price, category, pct_elapsed / 100.0)
        est_probs = [1.0 - true_no, true_no]
        chosen_index = 1
        edge = est_probs[1] - probs[1]
        ev_stake = expected_value_on_stake(est_probs[1], probs[1])
        kelly = fractional_kelly(est_probs[1], probs[1], cfg.kelly_fraction, cfg.max_position_pct)
        if edge < cfg.min_edge or ev_stake <= 0 or kelly <= 0:
            return None
    else:
        est_probs = estimate_true_probs(probs, category, pct_elapsed, volume24hr, liquidity)
        if len(est_probs) != 2:
            return None

        candidates = []
        for idx in range(2):
            edge = est_probs[idx] - probs[idx]
            ev_stake = expected_value_on_stake(est_probs[idx], probs[idx])
            kelly = fractional_kelly(est_probs[idx], probs[idx], cfg.kelly_fraction, cfg.max_position_pct)
            if edge >= cfg.min_edge and ev_stake > 0 and kelly > 0:
                candidates.append((idx, edge, ev_stake, kelly))

        if not candidates:
            return None

        chosen_index, edge, ev_stake, kelly = max(candidates, key=lambda item: (item[2], item[1]))

    market_prob = probs[chosen_index]
    est_prob = est_probs[chosen_index]
    confidence = edge * math.sqrt(max(liquidity, 1.0)) / max(days_remaining, 0.25)
    limit_price = clamp(market_prob - cfg.price_improvement_ticks, 0.01, 0.99)

    return MarketView(
        market_id=str(market.get("id", "")),
        event_id=str(market.get("eventId", market.get("event_id", ""))),
        question=question,
        category=category,
        outcomes=[str(outcomes[0]), str(outcomes[1])],
        probs=probs,
        est_probs=est_probs,
        chosen_index=chosen_index,
        side_label=str(outcomes[chosen_index]),
        market_prob=market_prob,
        est_prob=est_prob,
        edge=edge,
        ev_stake=ev_stake,
        kelly_fraction=kelly,
        limit_price=limit_price,
        expected_fill_price=market_prob,
        liquidity=liquidity,
        volume=volume,
        volume24hr=volume24hr,
        days_remaining=days_remaining,
        pct_elapsed=pct_elapsed,
        confidence=confidence,
        token_ids=load_token_ids(market),
    )


def fetch_all_active_markets(cfg: AgentConfig) -> list[dict[str, Any]]:
    all_markets: list[dict[str, Any]] = []
    offset = 0
    for _ in range(cfg.max_pages):
        url = (
            "https://gamma-api.polymarket.com/events"
            f"?closed=false&active=true&limit={cfg.max_events_per_page}&offset={offset}"
        )
        events = api_request(url)
        if not events:
            break
        for event in events:
            event_id = str(event.get("id", ""))
            for market in event.get("markets", []):
                market = dict(market)
                market.setdefault("eventId", event_id)
                all_markets.append(market)
        offset += cfg.max_events_per_page
        time.sleep(cfg.fetch_pause_s)
    return all_markets


def estimate_fill_price(token_id: str, budget: float) -> float | None:
    if not token_id or budget <= 0:
        return None
    try:
        data = api_request(f"https://clob.polymarket.com/book?token_id={token_id}")
    except Exception:
        return None
    asks = data.get("asks", [])
    if not asks:
        return None
    total_cost = 0.0
    total_shares = 0.0
    for ask in sorted(asks, key=lambda item: float(item["price"])):
        price = float(ask["price"])
        size = float(ask["size"])
        if price <= 0 or size <= 0:
            continue
        remaining_budget = budget - total_cost
        if remaining_budget <= 0:
            break
        shares = min(size, remaining_budget / price)
        total_cost += shares * price
        total_shares += shares
        if total_cost >= budget * 0.99:
            break
    if total_shares <= 0:
        return None
    return total_cost / total_shares


def enrich_fill_prices(markets: list[MarketView], cfg: AgentConfig) -> None:
    target_budget = max(cfg.min_order_size, cfg.capital * cfg.max_position_pct)
    for market in markets:
        if market.chosen_index >= len(market.token_ids):
            continue
        fill = estimate_fill_price(market.token_ids[market.chosen_index], target_budget)
        if fill is None or fill <= 0 or fill >= 1:
            continue
        market.expected_fill_price = fill
        market.ev_stake = expected_value_on_stake(market.est_prob, fill)
        market.kelly_fraction = fractional_kelly(
            market.est_prob,
            fill,
            cfg.kelly_fraction,
            cfg.max_position_pct,
        )
        market.limit_price = clamp(fill - cfg.price_improvement_ticks, 0.01, 0.99)


def build_portfolio(markets: list[MarketView], cfg: AgentConfig) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    reserve = cfg.capital * cfg.cash_reserve_pct
    deployable = max(cfg.capital - reserve, 0.0)
    selected: list[dict[str, Any]] = []
    total_allocated = 0.0
    by_category: dict[str, float] = {}
    cluster_counts: dict[str, int] = {}

    ranked = sorted(
        markets,
        key=lambda m: (
            m.ev_stake,
            m.edge,
            -CATEGORY_PRIORITY.get(m.category, 99),
            m.confidence,
        ),
        reverse=True,
    )

    for market in ranked:
        if total_allocated >= deployable:
            break

        cluster_key = market.event_id or market.question.lower()
        if cluster_counts.get(cluster_key, 0) >= cfg.max_markets_per_cluster:
            continue

        if any(
            jaccard_similarity(market.question, existing["question"]) >= cfg.correlation_threshold
            for existing in selected
        ):
            continue

        category_room = (cfg.capital * cfg.max_category_pct) - by_category.get(market.category, 0.0)
        if category_room < cfg.min_order_size:
            continue

        liquidity_cap = market.liquidity * cfg.max_size_as_pct_of_liquidity
        size = min(
            cfg.capital * market.kelly_fraction,
            cfg.max_order_size,
            liquidity_cap,
            category_room,
            deployable - total_allocated,
        )
        if size < cfg.min_order_size:
            continue

        ev_dollars = size * market.ev_stake
        selected.append(
            {
                "market_id": market.market_id,
                "event_id": market.event_id,
                "question": market.question,
                "category": market.category,
                "side": market.side_label,
                "market_prob": market.market_prob,
                "estimated_prob": market.est_prob,
                "edge": market.edge,
                "ev_stake": market.ev_stake,
                "limit_price": market.limit_price,
                "expected_fill_price": market.expected_fill_price,
                "days_remaining": market.days_remaining,
                "liquidity": market.liquidity,
                "size": size,
                "expected_value_dollars": ev_dollars,
            }
        )
        total_allocated += size
        by_category[market.category] = by_category.get(market.category, 0.0) + size
        cluster_counts[cluster_key] = cluster_counts.get(cluster_key, 0) + 1

    summary = {
        "capital": cfg.capital,
        "cash_reserve": reserve,
        "deployable_capital": deployable,
        "allocated_capital": total_allocated,
        "cash_remaining": cfg.capital - total_allocated,
        "position_count": len(selected),
        "category_exposure": by_category,
        "largest_position_pct": (max((row["size"] for row in selected), default=0.0) / cfg.capital)
        if cfg.capital
        else 0.0,
        "gross_expected_value": sum(row["expected_value_dollars"] for row in selected),
        "weighted_avg_edge": (
            sum(row["edge"] * row["size"] for row in selected) / total_allocated if total_allocated else 0.0
        ),
    }
    return selected, summary


def summarize_selected(selected: list[dict[str, Any]], cfg: AgentConfig) -> dict[str, Any]:
    by_category: dict[str, float] = {}
    allocated = 0.0
    weighted_edge_numerator = 0.0
    gross_ev = 0.0
    largest = 0.0
    for row in selected:
        size = row["size"]
        allocated += size
        gross_ev += row["expected_value_dollars"]
        largest = max(largest, size)
        weighted_edge_numerator += row["edge"] * size
        by_category[row["category"]] = by_category.get(row["category"], 0.0) + size
    reserve = cfg.capital * cfg.cash_reserve_pct
    return {
        "capital": cfg.capital,
        "cash_reserve": reserve,
        "deployable_capital": max(cfg.capital - reserve, 0.0),
        "allocated_capital": allocated,
        "cash_remaining": cfg.capital - allocated,
        "position_count": len(selected),
        "category_exposure": by_category,
        "largest_position_pct": (largest / cfg.capital) if cfg.capital else 0.0,
        "gross_expected_value": gross_ev,
        "weighted_avg_edge": (weighted_edge_numerator / allocated) if allocated else 0.0,
    }


def attach_history_metrics(summary: dict[str, Any]) -> dict[str, Any]:
    history_points = 0
    previous_allocated = None
    previous_gross_ev = None
    if HISTORY_FILE.exists():
        with HISTORY_FILE.open() as handle:
            rows = [json.loads(line) for line in handle if line.strip()]
        history_points = len(rows)
        if rows:
            previous_allocated = rows[-1].get("allocated_capital")
            previous_gross_ev = rows[-1].get("gross_expected_value")
    summary["history_points"] = history_points
    summary["previous_allocated_capital"] = previous_allocated
    summary["previous_gross_expected_value"] = previous_gross_ev
    return summary


def render(markets: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    console.print(
        Panel(
            "[bold green]POLYMARKET AUTONOMOUS RESEARCH AGENT[/bold green]\n"
            "[white]Ranking EV-positive opportunities with capped fractional Kelly sizing and correlation limits.[/white]"
        )
    )

    table = Table(show_header=True, header_style="bold white")
    table.add_column("#", style="cyan", justify="right")
    table.add_column("Category", style="magenta")
    table.add_column("Market", style="white")
    table.add_column("Side", style="green")
    table.add_column("Mkt", justify="right", style="yellow")
    table.add_column("Est", justify="right", style="blue")
    table.add_column("Edge", justify="right", style="green")
    table.add_column("EV", justify="right", style="green")
    table.add_column("Size", justify="right", style="cyan")

    for idx, market in enumerate(markets, start=1):
        table.add_row(
            str(idx),
            market["category"],
            market["question"][:56],
            market["side"],
            f"{market['market_prob'] * 100:.1f}%",
            f"{market['estimated_prob'] * 100:.1f}%",
            f"{market['edge'] * 100:.1f}%",
            f"{market['ev_stake'] * 100:.1f}%",
            f"${market['size']:.2f}",
        )
    console.print(table)

    portfolio = Table(show_header=True, header_style="bold magenta")
    portfolio.add_column("Metric", style="cyan")
    portfolio.add_column("Value", style="yellow", justify="right")
    portfolio.add_row("Capital", f"${summary['capital']:.2f}")
    portfolio.add_row("Allocated", f"${summary['allocated_capital']:.2f}")
    portfolio.add_row("Cash reserve", f"${summary['cash_reserve']:.2f}")
    portfolio.add_row("Cash remaining", f"${summary['cash_remaining']:.2f}")
    portfolio.add_row("Positions", str(summary["position_count"]))
    portfolio.add_row("Largest position", f"{summary['largest_position_pct'] * 100:.2f}%")
    portfolio.add_row("Weighted avg edge", f"{summary['weighted_avg_edge'] * 100:.2f}%")
    portfolio.add_row("Gross expected value", f"${summary['gross_expected_value']:.2f}")
    console.print(portfolio)

    if summary["category_exposure"]:
        console.print("[bold]Category exposure[/bold]")
        for category, exposure in sorted(summary["category_exposure"].items(), key=lambda item: item[1], reverse=True):
            console.print(f"  {category}: ${exposure:.2f} ({(exposure / summary['capital']) * 100:.2f}%)")


def write_snapshot(markets: list[dict[str, Any]], summary: dict[str, Any], cfg: AgentConfig) -> Path:
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    HISTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    payload = {
        "generated_at": now.isoformat(),
        "config": asdict(cfg),
        "portfolio_summary": summary,
        "opportunities": markets,
    }
    snapshot_path = SNAPSHOT_DIR / f"agent_report_{now.strftime('%Y%m%dT%H%M%SZ')}.json"
    snapshot_path.write_text(json.dumps(payload, indent=2))
    with HISTORY_FILE.open("a") as handle:
        handle.write(
            json.dumps(
                {
                    "generated_at": payload["generated_at"],
                    "allocated_capital": summary["allocated_capital"],
                    "gross_expected_value": summary["gross_expected_value"],
                    "position_count": summary["position_count"],
                    "weighted_avg_edge": summary["weighted_avg_edge"],
                }
            )
            + "\n"
        )
    return snapshot_path


def run_agent(cfg: AgentConfig) -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    raw_markets = fetch_all_active_markets(cfg)
    parsed = [parse_market(market, now, cfg) for market in raw_markets]
    candidates = [market for market in parsed if market is not None]
    candidates.sort(key=lambda market: (market.ev_stake, market.edge, market.confidence), reverse=True)
    enrich_fill_prices(candidates[: max(cfg.top_n * 3, 20)], cfg)
    candidates = [market for market in candidates if market.ev_stake > 0 and market.kelly_fraction > 0]
    selected, _ = build_portfolio(candidates, cfg)
    selected = selected[: cfg.top_n]
    summary = summarize_selected(selected, cfg)
    summary["scanned_markets"] = len(raw_markets)
    summary["qualified_markets"] = len(candidates)
    return {"selected": selected, "summary": attach_history_metrics(summary)}


def main() -> None:
    parser = argparse.ArgumentParser(description="Autonomous Polymarket research and sizing agent")
    parser.add_argument("--capital", type=float, default=1000.0)
    parser.add_argument("--model", choices=["paper", "generic"], default="paper")
    parser.add_argument("--min-edge", type=float, default=0.05)
    parser.add_argument("--min-liquidity", type=float, default=500.0)
    parser.add_argument("--min-volume", type=float, default=100.0)
    parser.add_argument("--min-days", type=float, default=0.0)
    parser.add_argument("--max-days", type=float, default=14.0)
    parser.add_argument("--max-position-pct", type=float, default=0.02)
    parser.add_argument("--kelly-fraction", type=float, default=0.25)
    parser.add_argument("--cash-reserve-pct", type=float, default=0.25)
    parser.add_argument("--max-category-pct", type=float, default=0.20)
    parser.add_argument("--top", type=int, default=15)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    cfg = AgentConfig(
        capital=args.capital,
        model=args.model,
        min_edge=args.min_edge,
        min_liquidity=args.min_liquidity,
        min_volume=args.min_volume,
        min_days=args.min_days,
        max_days=args.max_days,
        max_position_pct=args.max_position_pct,
        kelly_fraction=args.kelly_fraction,
        cash_reserve_pct=args.cash_reserve_pct,
        max_category_pct=args.max_category_pct,
        top_n=args.top,
    )

    result = run_agent(cfg)
    snapshot_path = write_snapshot(result["selected"], result["summary"], cfg)

    if args.json:
        console.print_json(
            data={
                "snapshot_path": str(snapshot_path),
                "portfolio_summary": result["summary"],
                "opportunities": result["selected"],
            }
        )
        return

    render(result["selected"], result["summary"])
    console.print(f"\nSnapshot written to {snapshot_path}")


if __name__ == "__main__":
    main()
