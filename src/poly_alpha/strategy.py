"""Core strategy logic for market filtering, classification, and Shin debiasing."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

SHIN_GAMMA: dict[str, float] = {
    "politics": 1.05,
    "crypto": 1.30,
    "weather": 1.15,
    "esports": 1.18,
    "sports": 1.20,
    "other": 1.18,
}

CATEGORY_LIMITS: dict[str, int] = {
    "sports": 20,
    "politics": 8,
    "other": 6,
    "crypto": 4,
    "weather": 4,
    "esports": 4,
}

CATEGORY_PRIORITY: dict[str, int] = {
    "sports": 1,
    "politics": 2,
    "other": 3,
    "crypto": 4,
    "weather": 5,
    "esports": 6,
}

LONG_TERM_PATTERNS: re.Pattern[str] = re.compile(
    r"(win the|finish in|relegated|champion|championship|finals|"
    r"premier league|la liga|serie a|bundesliga)",
    re.IGNORECASE,
)

LOW_ALPHA_SPORTS: re.Pattern[str] = re.compile(
    r"(exact score.*\d+\s*-\s*\d+|halftime|first half|1h moneyline)",
    re.IGNORECASE,
)

MONTHS: dict[str, int] = {
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

EMOTIONAL_OTHER_PATTERN: re.Pattern[str] = re.compile(
    r"(elon|musk|trump|netflix|box office|opening weekend|movie|show|album|song|"
    r"viral|twitter|tweet|x post|celebrity|drama|meme|lawsuit|arrested|"
    r"top global|youtube|tiktok|oscar|grammy|emmy)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class StrategyConfig:
    """Configuration for the market selection strategy."""

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
    category_limits: dict[str, int] = field(default_factory=lambda: dict(CATEGORY_LIMITS))
    max_positions: int = 50
    max_portfolio_deploy: float = 0.60
    min_trade_size: float = 3.0
    allow_synthetic_retail_fill: bool = False
    category_min_edge: dict[str, float] = field(
        default_factory=lambda: {
            "sports": 0.03,
            "politics": 0.005,
            "other": 0.025,
        }
    )


@dataclass(frozen=True)
class MarketProfile:
    """Classified profile for a prediction market."""

    category: str
    market_type: str
    emotional: bool


# ---------------------------------------------------------------------------
# Strategy presets
# ---------------------------------------------------------------------------


def clean_late_no_config() -> StrategyConfig:
    """Default production profile: late-expiry No-side sports + emotional headlines."""
    return StrategyConfig()


def paper_reset_sports_core_config() -> StrategyConfig:
    """Reset profile: keep only the sleeves closest to the paper's working edge."""
    return StrategyConfig(
        min_yes_price=0.04,
        max_yes_price=0.18,
        min_liquidity=175.0,
        min_volume=12.0,
        max_days=3.0,
        min_lifecycle_pct=0.55,
        max_lifecycle_pct=1.0,
        min_shin_edge=0.025,
        max_vol_liq_ratio=12.0,
        jaccard_threshold=0.45,
        include_categories=("sports",),
        allowed_sports_types=("spread", "total"),
        allow_emotional_other=False,
        category_limits={
            "sports": 40,
            "politics": 0,
            "other": 0,
            "crypto": 0,
            "weather": 0,
            "esports": 0,
        },
        max_positions=40,
        max_portfolio_deploy=0.75,
        min_trade_size=8.0,
        allow_synthetic_retail_fill=False,
        category_min_edge={"sports": 0.025},
    )


def balanced_late_no_config() -> StrategyConfig:
    """Higher-throughput profile that broadens the clean sleeve with basic guardrails."""
    return StrategyConfig(
        min_yes_price=0.04,
        max_yes_price=0.18,
        max_days=5.0,
        min_lifecycle_pct=0.60,
        max_lifecycle_pct=1.0,
        include_categories=("sports", "politics", "other", "crypto"),
        allowed_sports_types=("spread", "total", "moneyline"),
        category_min_edge={
            "sports": 0.02,
            "politics": 0.005,
            "other": 0.02,
            "crypto": 0.02,
        },
    )


def throughput_late_no_config() -> StrategyConfig:
    """Aggressive search profile for throughput exploration."""
    return StrategyConfig(
        min_yes_price=0.03,
        max_yes_price=0.20,
        max_days=7.0,
        min_lifecycle_pct=0.50,
        max_lifecycle_pct=1.0,
        include_categories=("sports", "politics", "other", "crypto"),
        allowed_sports_types=("spread", "total", "moneyline"),
        category_min_edge={
            "sports": 0.015,
            "politics": 0.003,
            "other": 0.015,
            "crypto": 0.015,
        },
        category_limits={
            "sports": 28,
            "politics": 10,
            "other": 8,
            "crypto": 8,
            "weather": 4,
            "esports": 4,
        },
        max_positions=65,
        max_portfolio_deploy=0.70,
        min_trade_size=2.5,
    )


def expansion_late_no_config() -> StrategyConfig:
    """Broader alpha-hunting profile for paper exploration."""
    return StrategyConfig(
        min_yes_price=0.02,
        max_yes_price=0.25,
        min_liquidity=100.0,
        min_volume=5.0,
        max_days=10.0,
        min_lifecycle_pct=0.35,
        max_lifecycle_pct=1.0,
        include_categories=("sports", "politics", "other", "crypto", "weather", "esports"),
        allowed_sports_types=("spread", "total", "moneyline"),
        category_min_edge={
            "sports": 0.01,
            "politics": 0.002,
            "other": 0.01,
            "crypto": 0.01,
            "weather": 0.008,
            "esports": 0.01,
        },
        category_limits={
            "sports": 45,
            "politics": 16,
            "other": 12,
            "crypto": 12,
            "weather": 8,
            "esports": 8,
        },
        max_positions=90,
        max_portfolio_deploy=0.80,
        min_trade_size=2.0,
    )


def quality_expansion_config() -> StrategyConfig:
    """Hybrid: expand trade count while keeping core quality in sports derivatives."""
    return StrategyConfig(
        min_yes_price=0.03,
        max_yes_price=0.18,
        min_liquidity=150.0,
        min_volume=8.0,
        max_days=7.0,
        min_lifecycle_pct=0.40,
        max_lifecycle_pct=1.0,
        include_categories=("sports", "politics", "other", "crypto"),
        allowed_sports_types=("spread", "total", "moneyline"),
        category_min_edge={
            "sports": 0.015,
            "politics": 0.003,
            "other": 0.015,
            "crypto": 0.015,
        },
        category_limits={
            "sports": 32,
            "politics": 12,
            "other": 8,
            "crypto": 8,
            "weather": 4,
            "esports": 4,
        },
        max_positions=70,
        max_portfolio_deploy=0.72,
        min_trade_size=2.5,
    )


def acceleration_config() -> StrategyConfig:
    """Expansion profile for pushing toward 100-slot paper book."""
    return StrategyConfig(
        min_yes_price=0.02,
        max_yes_price=0.22,
        min_liquidity=75.0,
        min_volume=5.0,
        max_days=7.0,
        min_lifecycle_pct=0.30,
        max_lifecycle_pct=1.0,
        jaccard_threshold=0.85,
        include_categories=("sports", "politics", "other", "crypto", "weather", "esports"),
        allowed_sports_types=("spread", "total", "moneyline"),
        category_min_edge={
            "sports": 0.008,
            "politics": 0.0015,
            "other": 0.01,
            "crypto": 0.01,
            "weather": 0.007,
            "esports": 0.008,
        },
        category_limits={
            "sports": 60,
            "politics": 20,
            "other": 10,
            "crypto": 12,
            "weather": 10,
            "esports": 10,
        },
        max_positions=100,
        max_portfolio_deploy=0.85,
        min_trade_size=2.0,
        allow_synthetic_retail_fill=True,
    )


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def _matches_keyword(text: str, keyword: str) -> bool:
    """Match single-word keywords on word boundaries; multi-word phrases as substrings."""
    if keyword.isalnum():
        return re.search(rf"\b{re.escape(keyword)}\b", text) is not None
    return keyword in text


def classify_category(question: str) -> str:
    """Classify a market question into a category."""
    q = question.lower()

    if any(
        _matches_keyword(q, w)
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
        _matches_keyword(q, w)
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
        _matches_keyword(q, w)
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
        _matches_keyword(q, w)
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
    if any(_matches_keyword(q, w) for w in politics_keywords) or re.search(r"\bwar\b", q):
        return "politics"

    return "other"


def classify_market_type(question: str) -> str:
    """Classify the structural type of a market (spread, total, moneyline, etc.)."""
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
    """Return full classified profile for a market question."""
    category = classify_category(question)
    market_type = classify_market_type(question)
    emotional = category == "politics" or bool(EMOTIONAL_OTHER_PATTERN.search(question))
    return MarketProfile(category=category, market_type=market_type, emotional=emotional)


# ---------------------------------------------------------------------------
# Probability math
# ---------------------------------------------------------------------------


def shin_debiasing(p_market: float, category: str = "other") -> float:
    """Apply Shin (1992) power-law debiasing to convert Q-measure to P-measure."""
    gamma: float = SHIN_GAMMA.get(category, 1.18)
    numerator: float = p_market**gamma
    denominator: float = numerator + (1.0 - p_market) ** gamma
    return numerator / denominator


def jaccard_similarity(s1: str, s2: str) -> float:
    """Compute Jaccard similarity between two market questions (word-level)."""
    set1 = set(s1.lower().split())
    set2 = set(s2.lower().split())
    union = set1 | set2
    if not union:
        return 0.0
    return len(set1 & set2) / len(union)


# ---------------------------------------------------------------------------
# Market candidate filtering
# ---------------------------------------------------------------------------


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)
    except (ValueError, TypeError):
        return None


def _date_mismatch(question: str, target_date: datetime, now: datetime) -> bool:
    q_lower = question.lower()
    for month_name, month_no in MONTHS.items():
        if not re.search(rf"\b{month_name}\b", q_lower):
            continue
        distance = abs(target_date.month - month_no)
        if min(distance, 12 - distance) > 2 and target_date.year == now.year:
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
    """Filter and score a raw market dict. Returns (candidate, None) or (None, reason)."""
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
        tokens: list[str] = json.loads(market.get("outcomePrices", "[]"))
        outcomes: list[str] = json.loads(market.get("outcomes", "[]"))
    except (json.JSONDecodeError, TypeError):
        return None, "parse_error"

    if len(tokens) < 2:
        return None, "no_prices"

    if len(outcomes) != 2:
        return None, "not_binary"

    try:
        yes_price = float(tokens[0])
    except (ValueError, IndexError):
        return None, "parse_error"

    try:
        no_price = float(tokens[1])
    except (ValueError, IndexError):
        no_price = 1.0 - yes_price
    if not 0.0 < no_price < 1.0:
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
