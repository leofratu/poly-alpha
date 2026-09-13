"""Deterministic, budgeted portfolio allocation over screened opportunities.

The allocator turns already-ranked opportunities into a conservative paper portfolio.
It never places orders, touches the network, or uses randomness: every stake is a pure
function of the screened input, its listed price, and the deployment constraints. The
result is simulated, in-sample research material, not investment advice or a forecast.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass

from poly_alpha.portfolio.sizing import SizingDecision, kelly_fraction
from poly_alpha.research.screen import Opportunity

_CAVEAT = (
    "Simulated heuristic allocation over labeled data (in-sample): not investment "
    "advice and not a forecast. Deterministic and offline, with no orders placed."
)


@dataclass(frozen=True)
class Allocation:
    """One market's budgeted position within an allocation plan."""

    market_id: str
    fraction: float
    stake: float
    rationale: str


@dataclass(frozen=True)
class AllocationPlan:
    """A budgeted, cash-aware allocation across screened opportunities."""

    bankroll: float
    total_fraction: float
    total_stake: float
    cash: float
    allocations: tuple[Allocation, ...]
    caveat: str


def _validate(bankroll: float, cap: float, max_positions: int, max_deploy: float) -> None:
    """Reject constraint values outside their documented domains."""
    if bankroll <= 0.0:
        raise ValueError(f"bankroll must be positive, got {bankroll!r}")
    if not 0.0 < cap <= 1.0:
        raise ValueError(f"cap must be in (0, 1], got {cap!r}")
    if max_positions < 0:
        raise ValueError(f"max_positions must be non-negative, got {max_positions!r}")
    if not 0.0 < max_deploy <= 1.0:
        raise ValueError(f"max_deploy must be in (0, 1], got {max_deploy!r}")


def _price_for(opportunity: Opportunity, prices: Mapping[str, float]) -> float | None:
    """Return the strictly interior listed price, or None when unusable."""
    price = prices.get(opportunity.note.market_id)
    if price is None or not 0.0 < price < 1.0:
        return None
    return price


def _build_allocation(
    market_id: str,
    fraction: float,
    bankroll: float,
    decision: SizingDecision,
    *,
    clamped: bool,
) -> Allocation:
    """Assemble one allocation, noting any clamp applied by the deploy budget."""
    rationale = decision.rationale
    if clamped:
        rationale = f"{rationale}; clamped to remaining deployment budget"
    return Allocation(
        market_id=market_id,
        fraction=fraction,
        stake=bankroll * fraction,
        rationale=rationale,
    )


def allocate(
    opportunities: Sequence[Opportunity],
    prices: Mapping[str, float],
    *,
    bankroll: float = 1000.0,
    cap: float = 0.05,
    max_positions: int = 20,
    max_deploy: float = 0.6,
