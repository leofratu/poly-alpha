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
