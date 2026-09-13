"""Conservative position sizing driven by research uncertainty.

Stake size is tied to the lower bound of an uncertainty interval rather than to a
point estimate, so an optimistic research view cannot by itself justify a larger
position. Sizing is per-market and deliberately not normalized across positions;
callers combine fractions themselves and apply any portfolio-level budget.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from poly_alpha.contracts import Uncertainty


@dataclass(frozen=True)
class SizingDecision:
    """A stake fraction and the reasoning that produced it."""

    fraction: float
    rationale: str
    capped: bool
    probability_used: float


def _clamp_probability(value: float) -> float:
    return max(0.0, min(1.0, value))


def kelly_fraction(
    *,
    probability: float,
    price: float,
    uncertainty: Uncertainty | None = None,
    cap: float = 0.05,
    use_lower_bound: bool = True,
) -> SizingDecision:
    """Size a binary position with full Kelly, capped at ``cap`` of the bankroll.

    When ``uncertainty`` is supplied and ``use_lower_bound`` is True the interval's
    ``low`` value is the effective probability, otherwise ``probability`` is used.
    The effective probability is clamped to [0, 1]. A price outside (0, 1) or a
    non-positive edge at the effective probability yields a zero fraction. Full
    Kelly for a binary paying 1.0 is ``edge / (1 - price)``; the returned fraction
    is the smaller of that and ``cap``.
