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
        datetime(2026, 6, 20, 23, 0, tzinfo=UTC),
    ),
    _FixtureSpec(
        "fixture-sports-derby",
        "Will Team A beat Team B in the June derby?",
        "SPORTS-DERBY",
        "sports",
        0.55,
        0.45,
        3100.0,
        12200.0,
        datetime(2026, 6, 14, 18, 0, tzinfo=UTC),
    ),
    _FixtureSpec(
        "fixture-politics-incumbent",
        "Will the incumbent win the 2026 general election?",
        "POL-INCUMBENT",
        "politics",
        0.58,
        0.42,
        7800.0,
        45600.0,
        datetime(2026, 11, 3, 23, 0, tzinfo=UTC),
    ),
    _FixtureSpec(
        "fixture-politics-bill",
        "Will the infrastructure bill pass by July 2026?",
        "POL-BILL",
        "politics",
        0.34,
        0.66,
        2600.0,
        9800.0,
        datetime(2026, 7, 1, 12, 0, tzinfo=UTC),
    ),
    _FixtureSpec(
        "fixture-crypto-btc",
        "Will BTC exceed $150k by year end?",
        "CRYPTO-BTC",
        "crypto",
        0.28,
        0.72,
        9100.0,
        61400.0,
        datetime(2026, 12, 31, 23, 59, tzinfo=UTC),
    ),
    _FixtureSpec(
        "fixture-weather-nyc",
        "Will NYC record above 95F in June 2026?",
        "WX-NYC-95F",
        "weather",
        0.41,
        0.59,
        1400.0,
        5200.0,
        datetime(2026, 6, 30, 23, 59, tzinfo=UTC),
    ),
    _FixtureSpec(
        "fixture-other-best-picture",
        "Will the frontrunner win Best Picture?",
        "FILM-BESTPIC",
        "other",
        0.47,
        0.53,
        2000.0,
        8700.0,
        datetime(2026, 9, 20, 2, 0, tzinfo=UTC),
    ),
    _FixtureSpec(
        "fixture-other-launch",
        "Will the mission launch before September 2026?",
        "SPACE-LAUNCH",
        "other",
        0.73,
        0.27,
        3600.0,
        15300.0,
        datetime(2026, 8, 31, 23, 59, tzinfo=UTC),
    ),
    _FixtureSpec(
        "fixture-equity-aapl-up",
        "Will AAPL close above its previous price?",
        "EQUITY-AAPL",
        "equity",
        0.51,
        0.49,
        5400.0,
        27000.0,
        datetime(2026, 6, 8, 20, 0, tzinfo=UTC),
    ),
    _FixtureSpec(
        "fixture-crypto-eth-up",
