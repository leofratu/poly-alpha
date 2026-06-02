from __future__ import annotations

import json
import logging
import re
import typing
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from typing import Final, Any
from enum import Enum

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.logging import RichHandler

from tradfi import get_tradfi_implied_probability
from deribit import get_deribit_implied_volatility
from multi_leg import simulate_multi_leg

app = typer.Typer(
    name="poly-alpha",
    help="Professional Quantitative Strategy Runner for prediction market arbitrage",
)
console = Console()

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    datefmt="[%X]",
    handlers=[RichHandler(rich_tracebacks=True, console=console)],
)
logger = logging.getLogger("poly-alpha")

HOURS_48: Final[int] = 48
POLYMARKET_API: Final[str] = "https://gamma-api.polymarket.com"


class MarketStatus(Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    PENDING = "pending"


@dataclass(frozen=True, slots=True)
class PolymarketEvent:
    event_id: str
    question: str
    yes_price: float
    no_price: float
    created_at: datetime
    expiry: datetime | None
    volume: float
    liquidity: float


@dataclass(frozen=True, slots=True)
class ContangoOpportunity:
    event: PolymarketEvent
    apy: float
    tradfi_prob: float | None
    edge_bps: float


@dataclass(frozen=True, slots=True)
class StrikeMarket:
    question: str
    strike: int
    date: str
    yes_price: float
    asset: str


@dataclass(frozen=True, slots=True)
class CombinatorialArbitrage:
    lower_strike: StrikeMarket
    higher_strike: StrikeMarket
    spread_bps: float


def fetch_polymarket_events(limit: int = 500) -> list[dict[str, Any]]:
    logger.info(f"Fetching Polymarket events (limit={limit})...")
    url = f"{POLYMARKET_API}/events?closed=false&active=true&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode())
            logger.info(f"Fetched {len(data)} events")
            return data
    except Exception as e:
        logger.error(f"Failed to fetch Polymarket events: {e}")
        return []


def parse_market_created_at(event: dict[str, Any]) -> datetime | None:
    created_ts = event.get("createdAt")
    if created_ts:
        try:
            if isinstance(created_ts, (int, float)):
                return datetime.fromtimestamp(created_ts / 1000.0, tz=timezone.utc)
            elif isinstance(created_ts, str):
                return datetime.fromisoformat(created_ts.replace("Z", "+00:00"))
        except Exception:
            pass
    return None


def parse_market_expiry(market: dict[str, Any]) -> datetime | None:
    expiry_ts = market.get("conditionResolutions", [{}])[0].get("resolutionTs")
    if not expiry_ts:
        expiry_ts = market.get("endDate")
    if expiry_ts:
        try:
            if isinstance(expiry_ts, (int, float)):
                return datetime.fromtimestamp(expiry_ts / 1000.0, tz=timezone.utc)
            elif isinstance(expiry_ts, str):
                return datetime.fromisoformat(expiry_ts.replace("Z", "+00:00"))
        except Exception:
            pass
    return None


def extract_yes_no_prices(market: dict[str, Any]) -> tuple[float, float] | None:
    try:
        outcome_prices = market.get("outcomePrices")
        if outcome_prices:
            tokens = (
                json.loads(outcome_prices)
                if isinstance(outcome_prices, str)
                else outcome_prices
            )
            if isinstance(tokens, list) and len(tokens) >= 2:
                yes_price = float(tokens[0]) if tokens[0] else 0.0
                no_price = float(tokens[1]) if tokens[1] else 0.0
                return (yes_price, no_price)
    except Exception:
        pass
    return None


def is_market_fresh(created_at: datetime, max_age_hours: int = HOURS_48) -> bool:
    age = datetime.now(timezone.utc) - created_at
    return age <= timedelta(hours=max_age_hours)


def calculate_contango_apy(yes_price: float, days_to_expiry: int) -> float:
    if yes_price <= 0.50 or days_to_expiry <= 0:
        return 0.0
    no_price = 1.0 - yes_price
    profit_per_share = no_price
    holding_period_days = max(1, days_to_expiry)
    roi = profit_per_share / yes_price
    apy = roi * (365.0 / holding_period_days) * 100.0
    return apy


def hunt_contango(
    max_age_hours: int = HOURS_48, min_apy: float = 10.0
) -> list[ContangoOpportunity]:
    logger.info(
        f"Starting Contango Strangle hunt (markets < {max_age_hours}h old, APY > {min_apy}%)"
    )

    events = fetch_polymarket_events(limit=500)
    opportunities: list[ContangoOpportunity] = []

    now = datetime.now(timezone.utc)

    for event in events:
        for market in event.get("markets", []):
            question = market.get("question", "")
            if not question:
                continue

            created_at = parse_market_created_at(event)
            if not created_at or not is_market_fresh(created_at, max_age_hours):
                continue

            prices = extract_yes_no_prices(market)
            if not prices:
                continue
            yes_price, no_price = prices

            if yes_price <= 0.50:
                continue

            expiry = parse_market_expiry(market)
            if not expiry:
                continue

            days_to_expiry = max(1, (expiry - now).days)

            tradfi_prob = None
            try:
                tradfi_prob = get_tradfi_implied_probability(question, expiry)
            except Exception as e:
                logger.debug(f"Could not fetch TradFi probability: {e}")

            apy = calculate_contango_apy(yes_price, days_to_expiry)

            if apy < min_apy:
                continue

            edge_bps = 0.0
            if tradfi_prob is not None:
                edge_bps = abs(yes_price - tradfi_prob) * 10000

            pm_event = PolymarketEvent(
                event_id=event.get("id", ""),
                question=question,
                yes_price=yes_price,
                no_price=no_price,
                created_at=created_at,
                expiry=expiry,
                volume=float(market.get("volume", 0.0) or 0.0),
                liquidity=float(market.get("liquidity", 0.0) or 0.0),
            )

            opp = ContangoOpportunity(
                event=pm_event,
                apy=apy,
                tradfi_prob=tradfi_prob,
                edge_bps=edge_bps,
            )
            opportunities.append(opp)

    opportunities.sort(key=lambda x: x.apy, reverse=True)
    logger.info(f"Found {len(opportunities)} Contango Strangle opportunities")
    return opportunities


def extract_strike_from_question(
    question: str, asset_pattern: str
) -> tuple[int, str] | None:
    strike_match = re.search(r"\$(\d+)k", question, re.IGNORECASE)
    if not strike_match:
        strike_match = re.search(
            r"(\d+(?:,\d{3})*)\s*(?:dollars|USD)?", question, re.IGNORECASE
        )

    if strike_match:
        strike_str = strike_match.group(1).replace(",", "")
        try:
            strike = int(strike_str)
            if "k" in question.lower() or "K" in strike_match.group(0):
                strike = strike * 1000 if strike < 1000 else strike
            return (strike, asset_pattern)
        except ValueError:
            pass
    return None


def parse_crypto_strike_markets(
    events: list[dict[str, Any]],
) -> list[StrikeMarket]:
    crypto_assets_pattern = (
        r"\b(BTC|Bitcoin|ETH|Ethereum|SOL|Solana|XRP|Ripple|DOGE|Dogecoin)\b"
    )
    markets: list[StrikeMarket] = []

    for event in events:
        for market in event.get("markets", []):
            question = market.get("question", "")
            if not question:
                continue

            if "hit" not in question.lower() and "reach" not in question.lower():
                continue

            asset_match = re.search(crypto_assets_pattern, question, re.IGNORECASE)
            if not asset_match:
                continue

            asset = asset_match.group(1).upper()
            if asset in {"BITCOIN", "BTC"}:
                asset = "BTC"
            elif asset in {"ETHEREUM", "ETH"}:
                asset = "ETH"
            elif asset in {"SOLANA", "SOL"}:
                asset = "SOL"

            strike_result = extract_strike_from_question(question, asset)
            if not strike_result:
                continue
            strike, _ = strike_result

            date_match = re.search(r"by\s+([^?]+)", question, re.IGNORECASE)
            if not date_match:
                continue
            date_str = date_match.group(1).replace("?", "").strip()

            prices = extract_yes_no_prices(market)
            if not prices:
                continue
            yes_price, _ = prices

            markets.append(
                StrikeMarket(
                    question=question,
                    strike=strike,
                    date=date_str,
                    yes_price=yes_price,
                    asset=asset,
                )
            )

    return markets


def hunt_combinatorial() -> list[CombinatorialArbitrage]:
    logger.info(
        "Starting Combinatorial Arbitrage hunt (strike monotonicity violations)"
    )

    events = fetch_polymarket_events(limit=1000)
    all_markets = parse_crypto_strike_markets(events)

    logger.info(f"Found {len(all_markets)} crypto strike markets")

    grouped: dict[tuple[str, str], list[StrikeMarket]] = {}
    for market in all_markets:
        key = (market.asset, market.date)
        grouped.setdefault(key, []).append(market)

    arbitrages: list[CombinatorialArbitrage] = []

    for (asset, date), markets in grouped.items():
        if len(markets) < 2:
            continue

        markets_sorted = sorted(markets, key=lambda m: m.strike)

        for i in range(len(markets_sorted) - 1):
            lower = markets_sorted[i]
            higher = markets_sorted[i + 1]

            if higher.yes_price > lower.yes_price:
                spread_bps = (higher.yes_price - lower.yes_price) * 10000
                arbitrages.append(
                    CombinatorialArbitrage(
                        lower_strike=lower,
                        higher_strike=higher,
                        spread_bps=spread_bps,
                    )
                )

    arbitrages.sort(key=lambda x: x.spread_bps, reverse=True)
    logger.info(f"Found {len(arbitrages)} combinatorial arbitrage opportunities")
    return arbitrages


def display_contango_results(opportunities: list[ContangoOpportunity]) -> None:
    if not opportunities:
        console.print(
            Panel(
                "[yellow]No Contango Strangle opportunities found[/yellow]",
                title="[bold]Contango Hunt",
            )
        )
        return

    table = Table(
        title=f"[bold cyan]Contango Strangle Opportunities ({len(opportunities)} found)[/bold cyan]"
    )
    table.add_column("APY", style="bold green", justify="right")
    table.add_column("Yes Price", style="yellow", justify="right")
    table.add_column("TradFi Prob", style="magenta", justify="right")
    table.add_column("Edge (bps)", style="cyan", justify="right")
    table.add_column("Question", style="white", max_width=50)

    for opp in opportunities[:20]:
        tradfi_str = f"{opp.tradfi_prob:.2%}" if opp.tradfi_prob is not None else "N/A"
        question_short = (
            opp.event.question[:47] + "..."
            if len(opp.event.question) > 50
            else opp.event.question
        )
        table.add_row(
            f"{opp.apy:.1f}%",
            f"{opp.event.yes_price:.2%}",
            tradfi_str,
            f"{opp.edge_bps:.0f}",
            question_short,
        )

    console.print(table)

    if opportunities:
        best = opportunities[0]
        console.print(
            f"\n[bold green]Best Opportunity:[/bold green] {best.event.question}"
        )
        console.print(
            f"  APY: [bold cyan]{best.apy:.1f}%[/bold cyan] | Yes: {best.event.yes_price:.2%} | Age: {(datetime.now(timezone.utc) - best.event.created_at).total_seconds() / 3600:.1f}h"
        )


def display_combinatorial_results(arbitrages: list[CombinatorialArbitrage]) -> None:
    if not arbitrages:
        console.print(
            Panel(
                "[yellow]No strike monotonicity violations found[/yellow]",
                title="[bold]Combinatorial Hunt",
            )
        )
        return

    table = Table(
        title=f"[bold cyan]Combinatorial Arbitrage Opportunities ({len(arbitrages)} found)[/bold cyan]"
    )
    table.add_column("Asset", style="bold yellow", justify="center")
    table.add_column("Lower Strike", style="green", justify="right")
    table.add_column("Lower Prob", style="green", justify="right")
    table.add_column("Upper Strike", style="red", justify="right")
    table.add_column("Upper Prob", style="red", justify="right")
    table.add_column("Spread (bps)", style="bold cyan", justify="right")
    table.add_column("Expiry", style="white")

    for arb in arbitrages[:15]:
        table.add_row(
            arb.lower_strike.asset,
            f"${arb.lower_strike.strike:,}",
            f"{arb.lower_strike.yes_price:.1%}",
            f"${arb.higher_strike.strike:,}",
            f"{arb.higher_strike.yes_price:.1%}",
            f"{arb.spread_bps:.0f}",
            arb.lower_strike.date[:20],
        )

    console.print(table)

    console.print(
        "\n[bold yellow]Strategy:[/bold yellow] Buy YES on Lower Strike, Buy NO on Higher Strike"
    )
    console.print(
        "[dim]This exploits probability monotonicity: P(Higher Strike) must be <= P(Lower Strike)[/dim]"
    )


@app.command()
def contango(
    max_age_hours: int = typer.Option(
        48, "--max-age", "-a", help="Maximum market age in hours"
    ),
    min_apy: float = typer.Option(
        10.0, "--min-apy", "-m", help="Minimum APY threshold"
    ),
    simulate: bool = typer.Option(
        False, "--simulate", "-s", help="Run multi-leg strategy simulation"
    ),
    capital: float = typer.Option(
        10000.0, "--capital", "-c", help="Capital for simulation"
    ),
) -> None:
    """
    Hunt for Contango Strangle opportunities on Polymarket.

    Scans for markets < 48 hours old where shorting the 'Yes' side (> 0.50)
    yields attractive APY based on time to expiry.
    """
    logger.info("Poly-Alpha Contango Strangle Scanner")
    logger.info(f"Parameters: max_age={max_age_hours}h, min_apy={min_apy}%")

    opportunities = hunt_contango(max_age_hours=max_age_hours, min_apy=min_apy)
    display_contango_results(opportunities)

    if simulate and opportunities:
        best = opportunities[0]
        logger.info(f"\nRunning multi-leg simulation with ${capital:,.0f} capital...")
        try:
            simulate_multi_leg(
                capital=capital,
                yes_price=best.event.yes_price,
                strike=100000.0,
                expiry_days=max(
                    1, (best.event.expiry - datetime.now(timezone.utc)).days
                )
                if best.event.expiry
                else 30,
                tradfi_prob=best.tradfi_prob or 0.05,
            )
        except Exception as e:
            logger.error(f"Simulation failed: {e}")


@app.command()
def combinatorial() -> None:
    """
    Hunt for Combinatorial Arbitrage across crypto strikes.

    Scans all crypto assets for strike monotonicity violations
    where higher strike prices have higher implied probabilities.
    """
    logger.info("Poly-Alpha Combinatorial Arbitrage Scanner")

    arbitrages = hunt_combinatorial()
    display_combinatorial_results(arbitrages)


@app.command()
def status() -> None:
    """Display system status and configuration."""
    console.print(
        Panel(
            "[bold cyan]Poly-Alpha Quantitative Strategy Runner[/bold cyan]\n\n"
            "[bold]Available Commands:[/bold]\n"
            "  hunt-contango     - Scan for Contango Strangle APY opportunities\n"
            "  hunt-combinatorial - Scan for strike monotonicity violations\n\n"
            "[bold]Modules:[/bold]\n"
            "  tradfi.py         - Black-Scholes probability estimation\n"
            "  deribit.py        - Live crypto options IV\n"
            "  multi_leg.py      - Multi-leg strategy simulation\n"
            "  hunt_combinatorial.py - Combinatorial arb logic\n\n"
            "[dim]legacy_arb/ is deprecated[/dim]",
            title="[bold]System Status",
        )
    )


if __name__ == "__main__":
    app()
