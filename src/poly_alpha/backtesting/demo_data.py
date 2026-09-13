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
    """Resolve a snapshot by comparing a hash draw against its de-vigged YES probability."""
    fair = snapshot.implied_yes()
    if fair is None:
        fair = snapshot.yes_price if snapshot.yes_price is not None else _FALLBACK_YES
    return _hash_uniform(snapshot.market_id) < fair


def demo_resolved_markets() -> list[ResolvedMarket]:
    """Pair each fixture market with a deterministic demo resolution.

    The outcome is decided by SHA-256 hashing the ``market_id`` and comparing the
    first four digest bytes, read as a big-endian fraction in ``[0, 1)``, against
    the snapshot's ``yes_price``. This is fully deterministic and deliberately not
    the naive ``yes_price > 0.5`` rule, so a market can resolve against its quoted
    favorite. Each ``ResolvedMarket`` keeps the fixture snapshot, whose provenance
    is ``DataSourceKind.FIXTURE``.
    """
    return [
        ResolvedMarket(snapshot=snapshot, resolved_yes=_resolve(snapshot))
        for snapshot in fixture_adapter().list_markets()
    ]


def demo_positions() -> list[Position]:
    """Build one simulated demo position per fixture market.

    Each stake is ``round(liquidity * 0.02, 2)`` and each ``yes_probability`` is the
    de-vigged ``implied_yes()``, falling back to 0.5 when unavailable. Provenance is
    copied from the fixture snapshot.
    """
    positions: list[Position] = []
    for snapshot in fixture_adapter().list_markets():
        implied = snapshot.implied_yes()
        positions.append(
            Position(
                market_id=snapshot.market_id,
                asset_class=snapshot.asset.asset_class,
                stake=round(snapshot.liquidity * _DEMO_STAKE_FRACTION, 2),
                yes_probability=implied if implied is not None else _FALLBACK_YES,
                provenance=snapshot.provenance,
            )
        )
    return positions


def demo_returns(n: int = 60) -> list[float]:
    """Return a deterministic simulated return series of length ``n``.

    Draws from ``numpy.random.default_rng`` with a fixed seed, sampling
    ``normal(0.0005, 0.02)``. The values are simulated, not observed, and exist only
    to demonstrate historical VaR and drawdown.
    """
    rng = np.random.default_rng(_DEMO_RETURN_SEED)
    return [float(value) for value in rng.normal(_DEMO_RETURN_MEAN, _DEMO_RETURN_STD, n)]
