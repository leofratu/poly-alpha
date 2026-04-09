from __future__ import annotations

from dataclasses import dataclass

from strategy_core import StrategyConfig, shin_debiasing


@dataclass(frozen=True)
class PaperAlphaSpec:
    min_yes_price: float = 0.01
    max_yes_price: float = 0.30
    min_no_price: float = 0.70
    max_no_price: float = 0.99
    min_liquidity: float = 20.0
    min_volume: float = 10.0
    min_days: float = 0.1
    max_days: float = 30.0
    max_lifecycle_pct: float = 0.25
    min_shin_edge: float = 0.003
    max_vol_liq_ratio: float = 50.0
    jaccard_threshold: float = 0.90
    fixed_bet_size: float = 5.0
    max_positions: int = 100
    deploy_cap_pct: float = 0.80


DEFAULT_PAPER_ALPHA = PaperAlphaSpec()


def to_strategy_config(spec: PaperAlphaSpec = DEFAULT_PAPER_ALPHA) -> StrategyConfig:
    return StrategyConfig(
        min_yes_price=spec.min_yes_price,
        max_yes_price=spec.max_yes_price,
        min_liquidity=spec.min_liquidity,
        min_volume=spec.min_volume,
        max_days=spec.max_days,
        min_days=spec.min_days,
        max_lifecycle_pct=spec.max_lifecycle_pct,
        min_shin_edge=spec.min_shin_edge,
        max_vol_liq_ratio=spec.max_vol_liq_ratio,
        jaccard_threshold=spec.jaccard_threshold,
    )


def category_early_bias(category: str) -> float:
    return {
        "crypto": 0.050,
        "politics": 0.035,
        "weather": 0.035,
        "esports": 0.030,
        "sports": 0.020,
        "other": 0.025,
    }.get(category, 0.025)


def lifecycle_multiplier(pct_elapsed: float) -> float:
    if pct_elapsed < 0.0:
        return 0.0
    if pct_elapsed <= 0.10:
        return 1.0
    if pct_elapsed <= 0.25:
        return max(0.0, 1.0 - ((pct_elapsed - 0.10) / 0.15))
    return 0.0


def estimate_paper_true_no(no_price: float, category: str, pct_elapsed: float) -> float:
    shin_no = shin_debiasing(no_price, category)
    boost = category_early_bias(category) * lifecycle_multiplier(pct_elapsed)
    estimated = max(shin_no, no_price + boost)
    return min(max(estimated, no_price), 0.999)


def estimate_paper_no_edge(no_price: float, category: str, pct_elapsed: float) -> float:
    return estimate_paper_true_no(no_price, category, pct_elapsed) - no_price


def expected_profit_per_dollar(no_price: float, category: str, pct_elapsed: float) -> float:
    true_no = estimate_paper_true_no(no_price, category, pct_elapsed)
    if no_price <= 0.0 or no_price >= 1.0:
        return -1.0
    return (true_no / no_price) - 1.0


def is_paper_candidate(
    yes_price: float,
    no_price: float,
    pct_elapsed: float,
    days_remaining: float,
    liquidity: float,
    volume: float,
    volume_24h: float,
    spec: PaperAlphaSpec = DEFAULT_PAPER_ALPHA,
) -> bool:
    if yes_price < spec.min_yes_price or yes_price > spec.max_yes_price:
        return False
    if no_price < spec.min_no_price or no_price > spec.max_no_price:
        return False
    if pct_elapsed > spec.max_lifecycle_pct:
        return False
    if days_remaining < spec.min_days or days_remaining > spec.max_days:
        return False
    if liquidity < spec.min_liquidity or volume < spec.min_volume:
        return False
    if liquidity > 0 and (volume_24h / liquidity) > spec.max_vol_liq_ratio:
        return False
    return True
