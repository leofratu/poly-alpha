"""Shared strategy logic for Poly-Alpha market filtering and scoring."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


SHIN_GAMMA = {
    "politics": 1.05,
    "crypto": 1.30,
    "weather": 1.15,
    "esports": 1.18,
    "sports": 1.20,
    "other": 1.18,
}

CATEGORY_LIMITS = {
    "sports": 20,
    "politics": 8,
    "other": 6,
    "crypto": 4,
    "weather": 4,
    "esports": 4,
}

CATEGORY_PRIORITY = {
    "sports": 1,
    "politics": 2,
    "other": 3,
    "crypto": 4,
    "weather": 5,
    "esports": 6,
}

LONG_TERM_PATTERNS = re.compile(
    r"(win the|finish in|relegated|champion|championship|finals|"
    r"premier league|la liga|serie a|bundesliga)",
    re.IGNORECASE,
)

LOW_ALPHA_SPORTS = re.compile(
    r"(exact score.*\d+\s*-\s*\d+|halftime|first half|1h moneyline)",
    re.IGNORECASE,
)

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

EMOTIONAL_OTHER_PATTERN = re.compile(
    r"(elon|musk|trump|netflix|box office|opening weekend|movie|show|album|song|"
    r"viral|twitter|tweet|x post|celebrity|drama|meme|lawsuit|arrested|"
    r"top global|youtube|tiktok|oscar|grammy|emmy)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StrategyConfig:
    min_yes_price: float = 0.05
    max_yes_price: float = 0.15
    min_liquidity: float = 250.0
    min_volume: float = 10.0
    max_days: float = 3.0
    min_days: float = 0.0
    min_lifecycle_pct: float = 0.75
    max_lifecycle_pct: float = 1.0
    min_shin_edge: float = 0.03
    max_vol_liq_ratio: float = 15.0
    jaccard_threshold: float = 0.30
    include_categories: tuple[str, ...] = ("sports", "politics", "other")
    allowed_sports_types: tuple[str, ...] = ("spread", "total")
    allow_emotional_other: bool = True
    category_min_edge: dict[str, float] = field(
        default_factory=lambda: {
            "sports": 0.03,
            "politics": 0.005,
            "other": 0.025,
        }
    )


@dataclass(frozen=True)
class MarketProfile:
    category: str
    market_type: str
    emotional: bool


def clean_late_no_config() -> StrategyConfig:
    """Observed live-alpha profile: late-expiry No-side sports plus emotional headlines."""
    return StrategyConfig()


def classify_category(question: str) -> str:
    q = question.lower()

    if any(
        w in q
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
        w in q
        for w in [
            "temperature",
            "weather",
            "snow",
            "rain",
            "hurricane",
            "highest temperature",
            "lowest temperature",
            "degrees c",
            "degrees f",
        ]
    ):
        return "weather"

    if any(
        w in q
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
            "vct ",
            "bo3",
        ]
    ):
        return "esports"

    if any(
        w in q
        for w in [
            "win on",
            "vs.",
            " o/u",
            "ncaa",
            "fc ",
            "premier",
            "la liga",
            "serie a",
            "bundesliga",
            "moneyline",
            "spread:",
            "leading at halftime",
            "warriors",
            "kings",
        ]
    ):
        return "sports"

    politics_keywords = [
        "trump",
        "election",
        "cabinet",
        "strike",
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
        "reza pahlavi",
    ]
    if any(w in q for w in politics_keywords) or re.search(r"\bwar\b", q):
        return "politics"

    return "other"


def classify_market_type(question: str) -> str:
    q = question.lower()
    if re.search(r"exact score.*\d+\s*-\s*\d+", q):
        return "exact_score"
    if "spread:" in q or re.search(r"\(-\d+(?:\.\d+)?\)", q):
        return "spread"
    if "o/u" in q:
        return "total"
    if "halftime" in q or "first half" in q or "1h moneyline" in q:
        return "halftime"
    if any(token in q for token in ["between $", "between "]):
        return "range"
    if any(token in q for token in ["above $", "below $"]):
        return "binary"
    if "up or down" in q:
        return "up_down"
    if " win on " in f" {q} " or q.startswith("will "):
        return "moneyline"
    return "binary"


def describe_market(question: str) -> MarketProfile:
    category = classify_category(question)
    market_type = classify_market_type(question)
    emotional = category == "politics" or bool(EMOTIONAL_OTHER_PATTERN.search(question))
    return MarketProfile(category=category, market_type=market_type, emotional=emotional)


def shin_debiasing(p_market: float, category: str = "other") -> float:
    gamma = SHIN_GAMMA.get(category, 1.18)
    return (p_market**gamma) / ((p_market**gamma) + ((1.0 - p_market) ** gamma))


def jaccard_similarity(s1: str, s2: str) -> float:
    set1 = set(s1.lower().split())
    set2 = set(s2.lower().split())
    union = set1.union(set2)
    if not union:
        return 0.0
    return len(set1.intersection(set2)) / len(union)


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _date_mismatch(question: str, target_date: datetime, now: datetime) -> bool:
    q_lower = question.lower()
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


def candidate_from_market(
    market: dict[str, Any],
    now: datetime,
    cfg: StrategyConfig,
) -> tuple[dict[str, Any] | None, str | None]:
    question = market.get("question", "")
    q_lower = question.lower()

    if LONG_TERM_PATTERNS.search(q_lower):
        return None, "long_term"

    end_date = _parse_dt(market.get("endDate"))
    if not end_date:
        return None, "no_end_date"

    if _date_mismatch(question, end_date, now):
        return None, "date_mismatch"

    days_remaining = (end_date - now).total_seconds() / 86400.0
    if days_remaining < cfg.min_days or days_remaining > cfg.max_days:
        return None, "outside_time_window"

    created = _parse_dt(market.get("createdAt"))
    if created:
        total_duration = (end_date - created).total_seconds() / 86400.0
        pct_elapsed = 1.0 - (days_remaining / total_duration) if total_duration > 0 else 1.0
    else:
        pct_elapsed = 0.5

    if pct_elapsed < cfg.min_lifecycle_pct or pct_elapsed > cfg.max_lifecycle_pct:
        return None, "outside_lifecycle_window"

    try:
        tokens = json.loads(market.get("outcomePrices", "[]"))
        outcomes = json.loads(market.get("outcomes", "[]"))
    except Exception:
        return None, "parse_error"

    if len(tokens) < 2:
        return None, "no_prices"

    if len(outcomes) != 2:
        return None, "not_binary"

    try:
        yes_price = float(tokens[0])
    except Exception:
        return None, "parse_error"

    no_price = 1.0 - yes_price
    if yes_price < cfg.min_yes_price or yes_price > cfg.max_yes_price:
        return None, "outside_price"

    profile = describe_market(question)
    category = profile.category
    market_type = profile.market_type

    if category not in cfg.include_categories:
        return None, "excluded_category"
    if category == "sports" and market_type not in cfg.allowed_sports_types:
        return None, "unsupported_sports_type"
    if category == "other":
        if not (cfg.allow_emotional_other and profile.emotional):
            return None, "non_emotional_other"
        if market_type != "binary":
            return None, "structured_other"
    if category == "politics" and market_type not in {"binary", "moneyline"}:
        return None, "structured_politics"

    volume = float(market.get("volume", 0) or 0)
    liquidity = float(market.get("liquidity", volume * 0.05) or 0)
    vol_24h = float(market.get("volume24hr", 0) or 0)

    if volume < cfg.min_volume:
        return None, "low_volume"
    if liquidity < cfg.min_liquidity:
        return None, "low_liquidity"
    if liquidity > 0 and (vol_24h / liquidity) > cfg.max_vol_liq_ratio:
        return None, "hft_spike"

    shin_no = shin_debiasing(no_price, category)
    shin_edge = shin_no - no_price
    min_edge = cfg.category_min_edge.get(category, cfg.min_shin_edge)
    if shin_edge < min_edge:
        return None, "low_edge"

    confidence = (shin_edge * max(liquidity, 1.0)) / max(days_remaining, 0.05)

    return {
        "id": market.get("id", ""),
        "question": question,
        "category": category,
        "market_type": market_type,
        "emotional": profile.emotional,
        "yes_price": yes_price,
        "no_price": no_price,
        "liquidity": liquidity,
        "volume": volume,
        "volume24hr": vol_24h,
        "days": days_remaining,
        "pct_elapsed": pct_elapsed * 100,
        "shin_no": shin_no,
        "shin_edge": shin_edge,
        "confidence": confidence,
        "priority": CATEGORY_PRIORITY.get(category, 99),
    }, None
