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
    """
    lower_bound_used = uncertainty is not None and use_lower_bound
    raw = uncertainty.low if lower_bound_used else probability
    effective = _clamp_probability(raw)
    bound_note = "lower bound used" if lower_bound_used else "point estimate used"
    if not 0.0 < cap <= 1.0:
        raise ValueError(f"cap must be in (0, 1], got {cap!r}")
    if not 0.0 < price < 1.0:
        return SizingDecision(
            fraction=0.0,
            rationale=f"price {price!r} outside (0, 1); effective probability "
            f"{effective:.4f} ({bound_note})",
            capped=False,
            probability_used=effective,
        )
    edge = effective - price
    if edge <= 0.0:
        return SizingDecision(
            fraction=0.0,
            rationale="no positive edge at the conservative bound",
            capped=False,
            probability_used=effective,
        )
    full = edge / (1.0 - price)
    fraction = min(full, cap)
    capped = full > cap
    rationale = (
        f"effective probability {effective:.4f} ({bound_note}), price {price:.4f}, "
        f"edge {edge:.4f}, full Kelly {full:.4f}, cap {cap:.4f}"
    )
    if capped:
        rationale += "; capped"
    return SizingDecision(
        fraction=fraction,
        rationale=rationale,
        capped=capped,
        probability_used=effective,
    )


def portfolio_fractions(
    probabilities: Sequence[float],
    prices: Sequence[float],
    *,
    cap: float = 0.05,
) -> list[SizingDecision]:
    """Size each market independently, with no cross-position normalization.

    Fractions are produced pairwise from ``probabilities`` and ``prices``. They are
    not scaled to sum to one or to any budget, because the total is whatever the
    individual conservative edges support; callers apply portfolio limits on top.
    """
    if len(probabilities) != len(prices):
        raise ValueError(
            "probabilities and prices must have equal length, got "
            f"{len(probabilities)} and {len(prices)}"
        )
    return [
        kelly_fraction(probability=probability, price=price, cap=cap)
        for probability, price in zip(probabilities, prices, strict=True)
    ]


def total_fraction(decisions: Sequence[SizingDecision]) -> float:
    """Return the sum of the fractions in ``decisions``."""
    return sum(decision.fraction for decision in decisions)
