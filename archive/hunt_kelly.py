import json
import urllib.request
from datetime import datetime, timezone
import dateutil.parser
from rich.console import Console
from rich.table import Table

console = Console()


def shin_debiasing(p_market, question=""):
    q_lower = question.lower()
    if any(w in q_lower for w in ["bitcoin", "ethereum", "solana", "xrp", "crypto"]):
        gamma = 1.30
    elif any(
        w in q_lower for w in ["win on", "vs.", "o/u", "ncaa", "fc", "championship"]
    ):
        gamma = 1.20
    elif any(w in q_lower for w in ["temperature", "weather", "snow"]):
        gamma = 1.15
    elif any(w in q_lower for w in ["trump", "election", "cabinet", "strike", "war"]):
        gamma = 1.05
    else:
        gamma = 1.18
    return (p_market**gamma) / ((p_market**gamma) + ((1.0 - p_market) ** gamma))


def fetch_l2_liquidity(limit=1000):
    # For sub-3 day markets, capital allocation is strictly limited by the
    # L2 Order Book depth (liquidity) at the BBO (Best Bid/Offer).
    url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit={limit}"
    req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
    try:
        with urllib.request.urlopen(req) as resp:
            events = json.loads(resp.read().decode())
    except Exception as e:
        console.print(f"[red]Failed to fetch markets: {e}[/red]")
        return []

    fast_markets = []

    for event in events:
        for m in event.get("markets", []):
            if not m.get("active") or m.get("closed"):
                continue

            q = m.get("question", "")
            end_date_str = m.get("endDate")
            if not end_date_str:
                continue

            try:
                target_date = dateutil.parser.isoparse(end_date_str).astimezone(
                    timezone.utc
                )
            except (ValueError, TypeError):
                continue

            now = datetime.now(timezone.utc)
            days = (target_date - now).days

            # Expiry in < 3 Days
            if days < 0 or days > 3:
                continue

            try:
                tokens = json.loads(m.get("outcomePrices", "[]"))
                if not tokens or len(tokens) < 2:
                    continue

                yes_price = float(tokens[0])
                no_price = 1.0 - yes_price

                # Retrieve available liquidity on the BBO
                # The Gamma API sometimes returns 'liquidity' or 'volume'
                # For real capital allocation, you cannot deploy $10k if the BBO only has $500 available.
                volume = float(m.get("volume", 0))
                liquidity = float(
                    m.get("liquidity", volume * 0.05)
                )  # Approximate BBO depth if liquidity not provided

                # We target 1% to 20% lotto tickets
                if yes_price >= 0.01 and yes_price <= 0.20:
                    # Kelly Criterion Calculation (Fraction of Portfolio to Wager)
                    # f* = (bp - q) / b
                    # p = Shin-debiased true probability of "No" winning
                    # b = Net fractional odds received on the wager ($1 / no_price) - 1
                    # q = Probability of losing (1 - p)

                    b = (1.0 / no_price) - 1.0
                    p = shin_debiasing(no_price, q)
                    q_loss = 1.0 - p

                    if b > 0:
                        kelly_fraction = (b * p - q_loss) / b
                    else:
                        kelly_fraction = 0

                    # Half-Kelly for safety
                    safe_kelly = max(0, kelly_fraction * 0.5)

                    fast_markets.append(
                        {
                            "question": q,
                            "days": days,
                            "yes_price": yes_price,
                            "no_price": no_price,
                            "liquidity": liquidity,
                            "safe_kelly": safe_kelly,
                            "roi": b,
                            "ev": p * b - q_loss,
                        }
                    )
            except Exception:
                pass

    return fast_markets


def size_portfolio(total_portfolio_usd=100000.0):
    markets = fetch_l2_liquidity()
    markets.sort(key=lambda x: x["safe_kelly"], reverse=True)

    console.print(
        f"[bold cyan]Kelly Criterion Capital Allocation | Portfolio: ${total_portfolio_usd:,.2f}[/bold cyan]\n"
    )

    table = Table(show_header=True, header_style="bold magenta")
    table.add_column("Market (< 72h Expiry)", style="cyan")
    table.add_column("Retail 'Yes'", justify="right", style="red")
    table.add_column("ROI per Trade", justify="right", style="green")
    table.add_column("L2 Liquidity Cap", justify="right", style="yellow")
    table.add_column("Safe Kelly %", justify="right", style="blue")
    table.add_column("Recommended Size", justify="right", style="bold white")

    total_allocated = 0.0
    expected_profit = 0.0

    for m in markets[:10]:
        # Target allocation based on Half-Kelly
        # Ensure we do not deploy more than 60% of total portfolio (40% black swan reserve)
        max_portfolio_deploy = total_portfolio_usd * 0.60
        remaining_capital = min(
            total_portfolio_usd - total_allocated,
            max_portfolio_deploy - total_allocated,
        )
        if remaining_capital <= 0:
            console.print(
                "[yellow]Portfolio deployment cap reached (60% max). Preserving 40% black swan reserve.[/yellow]"
            )
            break
        target_allocation = remaining_capital * m["safe_kelly"]

        # We CANNOT exceed the L2 liquidity available at that price!
        # If the order book only has $1,200 available at 95%, we cannot dump $5,000 into it without massive slippage.
        actual_allocation = min(target_allocation, m["liquidity"])

        if actual_allocation < 10:
            continue

        total_allocated += actual_allocation
        expected_profit += actual_allocation * m["ev"]

        table.add_row(
            m["question"][:45] + "...",
            f"{m['yes_price'] * 100:.1f}%",
            f"{m['roi'] * 100:.2f}%",
            f"${m['liquidity']:,.0f}",
            f"{m['safe_kelly'] * 100:.1f}%",
            f"[bold green]${actual_allocation:,.0f}[/bold green]",
        )

    console.print(table)
    console.print(
        f"\n[bold]Total Capital Deployed (L2 Adjusted):[/bold] ${total_allocated:,.2f} / ${total_portfolio_usd:,.2f}"
    )
    console.print(
        f"[bold]Expected Absolute Profit (48-72h):[/bold] [bold green]+${expected_profit:,.2f}[/bold green]"
    )


if __name__ == "__main__":
    size_portfolio()
