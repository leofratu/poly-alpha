"""Deterministic multi-step fixture histories so the platform can span time."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    Provenance,
)

_PROVENANCE_SOURCE = "poly-alpha fixture history"
_HISTORY_NOTE = "Deterministic fixture history; not real market data."
_AMPLITUDE = 0.015
_OMEGA = 0.7
_MIN_STEPS = 2
_PROBABILITY_FLOOR = 1e-9


@dataclass(frozen=True)
class _HistorySpec:
    """Deterministic inputs describing one multi-step fixture history."""

    market_id: str
    question: str
    symbol: str
    asset_class: str
    start_yes: float
    target_yes: float
    liquidity: float
    volume: float
    close_time: datetime
    phase: float


_SPECS: tuple[_HistorySpec, ...] = (
    _HistorySpec(
        "history-sports-hawks",
        "Will the Home Hawks win the 2026 championship?",
        "SPORTS-HAWKS",
        "sports",
