"""Clearly-labeled simulated demo data for exercising comparison and risk offline.

Every value produced here is simulated or derived from fixture inputs. Nothing is
real, nothing touches the network, and identical calls return identical results.
"""

from __future__ import annotations

import hashlib

import numpy as np

from poly_alpha.adapters.fixtures import fixture_adapter
from poly_alpha.backtesting.comparison import ResolvedMarket
from poly_alpha.contracts import MarketSnapshot
from poly_alpha.portfolio.risk import Position

DEMO_NOTE: str = (
    "DEMO: simulated, offline data for exercising comparison and risk; not real market data."
)

_DEMO_RETURN_SEED: int = 20260601
_DEMO_STAKE_FRACTION: float = 0.02
_DEMO_RETURN_MEAN: float = 0.0005
_DEMO_RETURN_STD: float = 0.02
_HASH_WINDOW_BYTES: int = 4
_FALLBACK_YES: float = 0.5


def _hash_uniform(market_id: str) -> float:
    """Map a market id to a deterministic uniform draw in [0, 1)."""
    digest = hashlib.sha256(market_id.encode("utf-8")).digest()
    window = digest[:_HASH_WINDOW_BYTES]
    return int.from_bytes(window, "big") / float(1 << (8 * _HASH_WINDOW_BYTES))


def _resolve(snapshot: MarketSnapshot) -> bool:
    """Resolve a snapshot by comparing a hash draw against its YES price."""
    yes_price = snapshot.yes_price if snapshot.yes_price is not None else _FALLBACK_YES
    return _hash_uniform(snapshot.market_id) < yes_price


def demo_resolved_markets() -> list[ResolvedMarket]:
    """Pair each fixture market with a deterministic demo resolution.

    The outcome is decided by SHA-256 hashing the ``market_id`` and comparing the
