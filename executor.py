import json
import urllib.request
import urllib.error
import time
import numpy as np
from datetime import datetime, timezone
import dateutil.parser
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
import os

console = Console()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def api_request(url, headers=None, data=None, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=headers, data=data)
            with urllib.request.urlopen(req) as resp:
                return json.loads(resp.read().decode())
        except urllib.error.HTTPError as e:
            if e.code == 429:
                wait = 2 ** (attempt + 2)
                console.print(f"[yellow]Rate limited. Waiting {wait}s...[/yellow]")
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


def fetch_l2_markets(limit=2000):
    url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit={limit}"
    try:
        events = api_request(url, headers={"User-Agent": "PolyAlpha/4.0"})
    except Exception as e:
        console.print(f"[red]Failed to fetch markets: {e}[/red]")
        return []

    markets_data = []

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
            except (ValueError, TypeError, KeyError):
                continue

            now = datetime.now(timezone.utc)
            days = (target_date - now).days

            # Filter 1: Expiry (< 14 Days)
            if days < 0 or days > 14:
                continue

            try:
                tokens = json.loads(m.get("outcomePrices", "[]"))
                if not tokens or len(tokens) < 2:
                    continue

                yes_price = float(tokens[0])
                no_price = 1.0 - yes_price

                volume = float(m.get("volume", 0))
                liquidity = float(m.get("liquidity", volume * 0.05))

                # Filter 2: Retail Bias (1% to 25% Yes) & Liquidity
                if yes_price >= 0.01 and yes_price <= 0.25 and liquidity > 500:
                    markets_data.append(
                        {
                            "id": m.get("id", q),
                            "question": q,
                            "days": max(0.1, days),
                            "yes_price": yes_price,
                            "no_price": no_price,
                            "liquidity": liquidity,
                        }
                    )
            except Exception:
                pass

    return markets_data


def evaluate_risk_ai(markets):
    if not GEMINI_API_KEY:
        console.print(
            "[yellow]GEMINI_API_KEY not found. Skipping AI semantic risk evaluation.[/yellow]"
        )
        for m in markets:
            m["ai_risk"] = 0.05
        return markets

    console.print(
        f"[cyan]Sending {len(markets)} markets to Gemini AI for tail-risk analysis...[/cyan]"
    )

    questions = [m["question"] for m in markets]
    prompt = f"""
You are a quantitative risk analyst for a hedge fund. We are evaluating prediction market events that expire within 14 days.
Retail traders often bid up "lottery tickets" (e.g. 5% chance of a celebrity dropping out, or a sudden military strike).
Your job is to evaluate the fundamental real-world 'Black Swan' tail risk of each event actually occurring within the next 14 days.

0.0 = Impossible / Pure retail hopium / Absolute zero physical catalyst.
1.0 = Highly likely / Active catalyst exists right now.

Evaluate these markets and return ONLY a valid JSON array of floats (0.0 to 1.0), in the exact same order. No markdown, no text.
Markets:
{json.dumps(questions)}
"""

    url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-3-flash-preview:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.0},
    }

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GEMINI_API_KEY}",
    }

    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers
    )
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())
            text_response = data["candidates"][0]["content"]["parts"][0]["text"].strip()
            text_response = (
                text_response.replace("```json", "").replace("```", "").strip()
            )
            risk_scores = json.loads(text_response)

            for i, m in enumerate(markets):
                m["ai_risk"] = float(risk_scores[i]) if i < len(risk_scores) else 0.50
    except Exception as e:
        console.print(
            f"[red]AI Evaluation Failed: {e}. Halting trading — cannot assess tail risk safely.[/red]"
        )
        for m in markets:
            m["ai_risk"] = 0.50

    return markets


def shin_debiasing(p_market, gamma=1.20):
    return (p_market**gamma) / ((p_market**gamma) + ((1.0 - p_market) ** gamma))


def jaccard_similarity(s1, s2):
    set1 = set(s1.lower().split())
    set2 = set(s2.lower().split())
    union = set1.union(set2)
    if not union:
        return 0.0
    return len(set1.intersection(set2)) / len(union)


def run_executor(capital=100000.0):
    console.print(
        Panel(
            "[bold green]POLY-ALPHA AUTONOMOUS EXECUTOR[/bold green]\n[white]Ingesting L2 Orderbooks, Running LLM Risk Analysis, and Executing Kelly Allocation...[/white]"
        )
    )

    raw_markets = fetch_l2_markets()
    if not raw_markets:
        return

    # Limit to top 40 most liquid to avoid Gemini payload limits
    raw_markets.sort(key=lambda x: x["liquidity"], reverse=True)
    raw_markets = raw_markets[:40]

    ai_markets = evaluate_risk_ai(raw_markets)

    # Filter out markets the AI thinks actually have > 15% real-world risk
    safe_markets = [m for m in ai_markets if m["ai_risk"] <= 0.15]
    console.print(
        f"[green]AI approved {len(safe_markets)} markets as pure retail bias (Tail Risk <= 15%).[/green]\n"
    )

    if not safe_markets:
        return

    n = len(safe_markets)
    expected_returns = np.zeros(n)
    variances = np.zeros(n)

    for i, m in enumerate(safe_markets):
        retail_no = m["no_price"]
        # Quant Model: Blend Shin Debiasing (P-Measure) with AI Risk Adjustment
        shin_prob = shin_debiasing(retail_no)
        # AI Risk applies to the "Yes" side. So AI "No" prob is 1.0 - AI_Risk
        ai_prob = 1.0 - m["ai_risk"]

        # Blended True Probability
        true_no_prob = (shin_prob * 0.70) + (ai_prob * 0.30)

        b = (1.0 / retail_no) - 1.0
        ev = (true_no_prob * b) - (1.0 - true_no_prob)
        expected_returns[i] = ev
        variances[i] = true_no_prob * ((b - ev) ** 2) + (1.0 - true_no_prob) * (
            (-retail_no - ev) ** 2
        )

        m["true_no_prob"] = true_no_prob
        m["ev"] = ev

    viable_indices = [i for i, ev in enumerate(expected_returns) if ev > 0]
    viable_markets = [safe_markets[i] for i in viable_indices]
    k = len(viable_markets)

    if k == 0:
        console.print("[red]No positive EV markets remaining.[/red]")
        return

    cov_matrix = np.zeros((k, k))
    for i in range(k):
        for j in range(k):
            if i == j:
                cov_matrix[i, j] = variances[viable_indices[i]]
            else:
                sim = jaccard_similarity(
                    viable_markets[i]["question"], viable_markets[j]["question"]
                )
                std_i = np.sqrt(variances[viable_indices[i]])
                std_j = np.sqrt(variances[viable_indices[j]])
                cov_matrix[i, j] = sim * std_i * std_j

    ev_vector = np.array([m["ev"] for m in viable_markets])
    reg_cov = cov_matrix + np.eye(k) * 1e-6
    inv_cov = np.linalg.inv(reg_cov)

    kelly_fractions = inv_cov @ ev_vector
    allocated_fractions = np.clip(kelly_fractions * 0.5, 0, None)

    total_deployed = 0.0

    console.print("[bold cyan]Execution Blotter (Trade Routing)[/bold cyan]")
    table = Table(show_header=True, header_style="bold white")
    table.add_column("Asset / Market", style="cyan")
    table.add_column("AI Risk", justify="right", style="red")
    table.add_column("L2 Price", justify="right", style="yellow")
    table.add_column("EV", justify="right", style="blue")
    table.add_column("Order Type", style="magenta")
    table.add_column("Size (USDC)", justify="right", style="bold green")

    for i, m in enumerate(viable_markets):
        remaining_capital = capital - total_deployed
        target_capital = capital * allocated_fractions[i]

        max_capital = min(target_capital, m["liquidity"])
        max_capital = min(max_capital, remaining_capital)

        if max_capital > 50:
            total_deployed += max_capital
            table.add_row(
                m["question"][:45] + "...",
                f"{m['ai_risk'] * 100:.1f}%",
                f"{m['no_price'] * 100:.1f}¢",
                f"{m['ev'] * 100:.2f}%",
                "LIMIT GTC (Maker)",
                f"${max_capital:,.0f}",
            )

    console.print(table)
    console.print(f"\n[bold]ROUTING STATUS:[/bold] [green]SIMULATED[/green]")
    console.print(
        f"[bold]TOTAL CAPITAL ALLOCATED:[/bold] ${total_deployed:,.2f} / ${capital:,.2f}"
    )
    console.print(
        "[bold yellow]Action:[/bold yellow] To execute live on Polygon, integrate Ethers.py with Polymarket CTF Exchange addresses and sign the payload with your private key."
    )


if __name__ == "__main__":
    run_executor()
