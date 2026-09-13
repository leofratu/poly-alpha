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
        0.55,
        0.70,
        4200.0,
        18500.0,
        datetime(2026, 6, 20, 23, 0, tzinfo=UTC),
        0.0,
    ),
    _HistorySpec(
        "history-politics-incumbent",
        "Will the incumbent win the 2026 general election?",
        "POL-INCUMBENT",
        "politics",
        0.48,
        0.42,
        7800.0,
        45600.0,
        datetime(2026, 11, 3, 23, 0, tzinfo=UTC),
        1.3,
    ),
    _HistorySpec(
        "history-crypto-btc-up",
        "Will BTC close above its previous price?",
        "CRYPTO-BTC-UP",
        "crypto",
        0.50,
        0.62,
        9100.0,
        61400.0,
        datetime(2026, 12, 31, 23, 59, tzinfo=UTC),
        2.6,
    ),
    _HistorySpec(
        "history-equity-aapl-up",
        "Will AAPL close above its previous price?",
        "EQUITY-AAPL-UP",
        "equity",
        0.52,
        0.45,
        5400.0,
        27000.0,
        datetime(2026, 6, 8, 20, 0, tzinfo=UTC),
        3.9,
    ),
)


def _clamp_probability(value: float) -> float:
    """Force a probability strictly inside the open unit interval."""
    return min(max(value, _PROBABILITY_FLOOR), 1.0 - _PROBABILITY_FLOOR)


def _yes_price(spec: _HistorySpec, index: int, steps: int) -> float:
    """Closed-form drift plus a small deterministic sinusoid, clamped to (0, 1)."""
    progress = index / (steps - 1)
    drift = spec.start_yes + (spec.target_yes - spec.start_yes) * progress
    wave = _AMPLITUDE * math.sin(_OMEGA * index + spec.phase)
    return _clamp_probability(drift + wave)


def _asset(spec: _HistorySpec) -> AssetRef:
    """Build the asset reference shared by every snapshot in a history."""
    return AssetRef(symbol=spec.symbol, asset_class=spec.asset_class, description=spec.question)


def _snapshot(
    spec: _HistorySpec,
    index: int,
    steps: int,
    provenance: Provenance,
) -> MarketSnapshot:
    """Materialize one snapshot, stepping the close time back one day per index."""
    yes_price = _yes_price(spec, index, steps)
    close_time = spec.close_time - timedelta(days=steps - 1 - index)
    return MarketSnapshot(
        market_id=spec.market_id,
        question=spec.question,
        asset=_asset(spec),
        yes_price=yes_price,
        no_price=1.0 - yes_price,
        liquidity=spec.liquidity,
        volume=spec.volume,
        provenance=provenance,
        close_time=close_time,
    )


@dataclass(frozen=True)
class MarketHistory:
    """A time-ordered series of snapshots for one market."""

    asset: AssetRef
    snapshots: tuple[MarketSnapshot, ...]
