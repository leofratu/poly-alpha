"""Small named-strategy library that plugs into ``compare_strategies``.

Each strategy maps a ``MarketSnapshot`` to a fair YES probability or None to skip
the market. Every strategy here is a heuristic; none has validated performance.
"""

from __future__ import annotations

from collections.abc import Callable

from poly_alpha.contracts import MarketSnapshot
from poly_alpha.research.analyst import research_market
from poly_alpha.strategy import classify_category, shin_debiasing

StrategyFn = Callable[[MarketSnapshot], float | None]

_HEURISTIC_NOTE = "heuristic; no validated performance"


def market_implied(snapshot: MarketSnapshot) -> float | None:
    """Return the de-vigged market-implied YES probability, or None when unpriced."""
    return snapshot.implied_yes()


def shin_debiased(snapshot: MarketSnapshot) -> float | None:
    """Shin-debias the de-vigged implied price using the snapshot's classified category."""
    implied = snapshot.implied_yes()
    if implied is None:
        return None
    return shin_debiasing(implied, classify_category(snapshot.question))


def constant_half(snapshot: MarketSnapshot) -> float | None:
    """Return a fixed neutral 0.5 YES probability for every snapshot."""
    return 0.5


def uncertainty_gated(snapshot: MarketSnapshot) -> float | None:
    """Return the research model estimate only when its lower edge bound is positive."""
    note = research_market(snapshot)
    if note.edge.low > 0.0:
        return note.model_yes.estimate
    return None


def default_strategies() -> dict[str, StrategyFn]:
