"""Deterministic, fully offline research engine over market snapshots.

No network and no model calls are made: every estimate is a pure function of the
snapshot, derived from the de-vigged market price, order-book depth, and liquidity.
Uncertainty intervals widen as data quality falls so consumers can size confidence
honestly.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime

from poly_alpha.contracts import (
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
    Uncertainty,
)
from poly_alpha.research.notes import ResearchClaim, ResearchNote
from poly_alpha.strategy import classify_category, shin_debiasing

_FIXED_TIME = datetime(1970, 1, 1, tzinfo=UTC)
_LIQUIDITY_REFERENCE = 500.0
_DEPTH_REFERENCE = 100.0
_IMBALANCE_WEIGHT = 0.15
_MAX_BOOK_LEVELS = 3
_BASE_HALF_WIDTH = 0.04
_LIQUIDITY_HALF_WIDTH = 0.18
_DEPTH_HALF_WIDTH = 0.12
_MAX_HALF_WIDTH = 0.5
_NEUTRAL_DEADBAND = 0.005


def _clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, value))


def _sign_direction(value: float) -> str:
    if value > _NEUTRAL_DEADBAND:
        return "bullish_yes"
    if value < -_NEUTRAL_DEADBAND:
        return "bearish_yes"
    return "neutral"

