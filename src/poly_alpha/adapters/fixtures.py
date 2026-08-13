"""Deterministic, offline fixture markets for tests and local development."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
)

FIXTURE_AS_OF = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)

_PROVENANCE_SOURCE = "poly-alpha deterministic fixtures"
_BOOK_STEP = 0.02


@dataclass(frozen=True)
class _FixtureSpec:
    """Deterministic inputs describing one fixture market."""

    market_id: str
    question: str
    symbol: str
    asset_class: str
    yes_price: float
    no_price: float
    liquidity: float
    volume: float
    close_time: datetime


_SPECS: tuple[_FixtureSpec, ...] = (
    _FixtureSpec(
        "fixture-sports-hawks",
        "Will the Home Hawks win the 2026 championship?",
        "SPORTS-HAWKS",
        "sports",
        0.62,
        0.38,
        4200.0,
        18500.0,
