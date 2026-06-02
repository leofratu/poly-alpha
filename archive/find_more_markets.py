"""
Find more markets by relaxing filters incrementally.
Shows exactly which filter is choking the pipeline.
"""

import json
import urllib.request
import ssl
import time
import re
import numpy as np
from datetime import datetime, timezone
import dateutil.parser
from rich.console import Console
from rich.table import Table

console = Console()

ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

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
        "sports": 1.20,
        "other": 1.18,
    }.get(cat, 1.18)
    return (p**gamma) / ((p**gamma) + ((1.0 - p) ** gamma))


def fetch_all():
    console.print("[cyan]Fetching ALL active markets...[/cyan]")
    all_m = []
    offset = 0
    total = 0
    while True:
        url = f"https://gamma-api.polymarket.com/events?closed=false&active=true&limit=1000&offset={offset}"
        req = urllib.request.Request(url, headers={"User-Agent": "PolyAlpha/1.0"})
        try:
            with urllib.request.urlopen(req, timeout=30, context=ssl_context) as resp:
                events = json.loads(resp.read().decode())
                if not events:
                    break
                for e in events:
                    for m in e.get("markets", []):
                        all_m.append(m)
                total += len(events)
                console.print(f"  {total:,} events ({len(all_m):,} markets)...")
                offset += 1000
                time.sleep(0.3)
        except Exception as e:
            console.print(f"[yellow]Error: {e}[/yellow]")
            break
    return all_m


def test_filters(all_markets):
    now = datetime.now(timezone.utc)

    # Test multiple filter configurations
    configs = [
        {
            "name": "PERFECT (current)",
            "max_days": 7.0,
            "min_yes": 0.05,
            "max_yes": 0.15,
            "min_liq": 250,
            "min_edge": 0.03,
            "reject_sports": True,
            "reject_long": True,
        },
        {
            "name": "WIDER: 14 days",
            "max_days": 14.0,
            "min_yes": 0.05,
            "max_yes": 0.15,
            "min_liq": 250,
            "min_edge": 0.03,
            "reject_sports": True,
            "reject_long": True,
        },
        {
            "name": "WIDER: 14d + 3-20¢ Yes",
            "max_days": 14.0,
            "min_yes": 0.03,
            "max_yes": 0.20,
            "min_liq": 250,
            "min_edge": 0.03,
            "reject_sports": True,
            "reject_long": True,
        },
        {
            "name": "WIDER: 14d + 3-20¢ + $100 liq",
            "max_days": 14.0,
            "min_yes": 0.03,
            "max_yes": 0.20,
            "min_liq": 100,
            "min_edge": 0.03,
            "reject_sports": True,
            "reject_long": True,
        },
        {
            "name": "WIDER: 14d + 3-20¢ + $100 liq + 2¢ edge",
            "max_days": 14.0,
            "min_yes": 0.03,
            "max_yes": 0.20,
            "min_liq": 100,
            "min_edge": 0.02,
            "reject_sports": True,
            "reject_long": True,
        },
        {
            "name": "MAX: 30d + 1-30¢ + $50 liq + 1¢ edge",
            "max_days": 30.0,
            "min_yes": 0.01,
            "max_yes": 0.30,
            "min_liq": 50,
            "min_edge": 0.01,
            "reject_sports": False,
            "reject_long": False,
        },
    ]

    results = []

    for cfg in configs:
        passed = []
        rejected = {}

        for m in all_markets:
            try:
                q = m.get("question", "")
                ql = q.lower()

                if cfg["reject_long"] and LONG_TERM.search(ql):
                    rejected["long_term"] = rejected.get("long_term", 0) + 1
                    continue

                if cfg["reject_sports"] and LOW_ALPHA.search(ql):
                    rejected["low_alpha_sports"] = (
                        rejected.get("low_alpha_sports", 0) + 1
                    )
                    continue

                end_date_str = m.get("endDate")
                if not end_date_str:
                    rejected["no_end_date"] = rejected.get("no_end_date", 0) + 1
                    continue

                try:
                    target_date = dateutil.parser.isoparse(end_date_str).astimezone(
                        timezone.utc
                    )
                except:
                    rejected["parse_error"] = rejected.get("parse_error", 0) + 1
                    continue

                days = (target_date - now).total_seconds() / 86400.0

                if days < 0.1 or days > cfg["max_days"]:
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

                if yes_price < cfg["min_yes"] or yes_price > cfg["max_yes"]:
                    rejected["outside_price"] = rejected.get("outside_price", 0) + 1
                    continue

                volume = float(m.get("volume", 0))
                liquidity = float(m.get("liquidity", volume * 0.05))
                if liquidity < cfg["min_liq"]:
                    rejected["low_liq"] = rejected.get("low_liq", 0) + 1
                    continue

                cat = classify_category(q)
                shin_no = shin_debiasing(no_price, cat)
                edge = shin_no - no_price

                if edge < cfg["min_edge"]:
                    rejected["low_edge"] = rejected.get("low_edge", 0) + 1
                    continue

                passed.append(
                    {
                        "question": q,
                        "category": cat,
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "liquidity": liquidity,
                        "days": days,
                        "shin_edge": edge,
                    }
                )
            except:
                rejected["parse_error"] = rejected.get("parse_error", 0) + 1

        # Dedup
        diversified = []
        for m in passed:
            dup = False
            for e in diversified:
                s1 = set(m["question"].lower().split())
                s2 = set(e["question"].lower().split())
                u = s1.union(s2)
                if u and len(s1.intersection(s2)) / len(u) > 0.3:
                    dup = True
                    break
            if not dup:
                diversified.append(m)

        results.append(
            {
                "name": cfg["name"],
                "passed": len(passed),
                "after_dedup": len(diversified),
                "rejected": rejected,
                "by_category": {},
            }
        )

        for m in diversified:
            cat = m["category"]
            results[-1]["by_category"][cat] = results[-1]["by_category"].get(cat, 0) + 1

    # Print results
    console.print("\n[bold cyan]FILTER COMPARISON:[/bold cyan]")
    t = Table(show_header=True, header_style="bold magenta")
    t.add_column("Config", style="cyan")
    t.add_column("Passed", justify="right", style="green")
    t.add_column("After Dedup", justify="right", style="yellow")
    t.add_column("Politics", justify="right", style="red")
    t.add_column("Crypto", justify="right", style="yellow")
    t.add_column("Sports", justify="right", style="white")
    t.add_column("Weather", justify="right", style="cyan")
    t.add_column("Other", justify="right", style="magenta")

    for r in results:
        bc = r["by_category"]
        t.add_row(
            r["name"],
            str(r["passed"]),
            str(r["after_dedup"]),
            str(bc.get("politics", 0)),
            str(bc.get("crypto", 0)),
            str(bc.get("sports", 0)),
            str(bc.get("weather", 0)),
            str(bc.get("other", 0) + bc.get("esports", 0)),
        )
    console.print(t)

    # Show what the MAX config found
    max_result = results[-1]
    if max_result["after_dedup"] > 0:
        console.print(
            f"\n[bold]Top 30 from MAX config ({max_result['after_dedup']} total after dedup):[/bold]"
        )
        mt = Table(show_header=True, header_style="bold green")
        mt.add_column("#", style="cyan")
        mt.add_column("Cat", style="magenta")
        mt.add_column("Question", style="white")
        mt.add_column("Yes", justify="right", style="red")
        mt.add_column("Edge", justify="right", style="blue")
        mt.add_column("Liq", justify="right", style="yellow")
        mt.add_column("Days", justify="right")

        # Re-run MAX to get the actual list
        max_cfg = configs[-1]
        max_passed = []
        for m in all_markets:
            try:
                q = m.get("question", "")
                ql = q.lower()
                if max_cfg["reject_long"] and LONG_TERM.search(ql):
                    continue
                if max_cfg["reject_sports"] and LOW_ALPHA.search(ql):
                    continue
                end_date_str = m.get("endDate")
                if not end_date_str:
                    continue
                try:
                    target_date = dateutil.parser.isoparse(end_date_str).astimezone(
                        timezone.utc
                    )
                except:
                    continue
                days = (target_date - now).total_seconds() / 86400.0
                if days < 0.1 or days > max_cfg["max_days"]:
                    continue
                tokens = json.loads(m.get("outcomePrices", "[]"))
                if len(tokens) < 2:
                    continue
                outcomes = json.loads(m.get("outcomes", "[]"))
                if len(outcomes) != 2:
                    continue
                yes_price = float(tokens[0])
                no_price = 1.0 - yes_price
                if yes_price < max_cfg["min_yes"] or yes_price > max_cfg["max_yes"]:
                    continue
                volume = float(m.get("volume", 0))
                liquidity = float(m.get("liquidity", volume * 0.05))
                if liquidity < max_cfg["min_liq"]:
                    continue
                cat = classify_category(q)
                shin_no = shin_debiasing(no_price, cat)
                edge = shin_no - no_price
                if edge < max_cfg["min_edge"]:
                    continue
                max_passed.append(
                    {
                        "question": q,
                        "category": cat,
                        "yes_price": yes_price,
                        "no_price": no_price,
                        "liquidity": liquidity,
                        "days": days,
                        "shin_edge": edge,
                    }
                )
            except:
                continue

        max_passed.sort(key=lambda x: -x["shin_edge"])
        cat_colors = {
            "politics": "bold red",
            "crypto": "bold yellow",
            "weather": "bold cyan",
            "esports": "bold magenta",
            "sports": "bold white",
            "other": "bold white",
        }

        for i, m in enumerate(max_passed[:30]):
            mt.add_row(
                str(i + 1),
                f"[{cat_colors.get(m['category'], 'white')}]{m['category']}[/{cat_colors.get(m['category'], 'white')}]",
                m["question"][:50],
                f"{m['yes_price'] * 100:.1f}¢",
                f"+{m['shin_edge'] * 100:.1f}¢",
                f"${m['liquidity']:,.0f}",
                f"{m['days']:.1f}",
            )
        console.print(mt)
        if len(max_passed) > 30:
            console.print(f"  ...and {len(max_passed) - 30} more")


if __name__ == "__main__":
    all_markets = fetch_all()
    console.print(f"\n[green]Total: {len(all_markets):,} markets[/green]")
    test_filters(all_markets)
