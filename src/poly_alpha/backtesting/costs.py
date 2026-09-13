"""Execution-cost model for evaluating prediction-market edges net of fees.

The model is a pure calculation: it never places orders and never touches the
network. Costs are expressed in basis points (1 bp = 0.01%) and are applied to the
entry price so a strategy can compare a fair probability against a costed price.
A buy pays up and a sell receives less; both effective prices stay within [0, 1]
because a binary share cannot cost less than 0 or more than 1.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

_BPS_PER_UNIT: float = 10000.0

_BUY: str = "buy"
_SELL: str = "sell"


def _normalize_side(side: str) -> str:
    """Return ``side`` lowercased, rejecting anything but buy/sell."""
    normalized = side.lower()
    if normalized not in (_BUY, _SELL):
        raise ValueError(f"side must be 'buy' or 'sell', got {side!r}")
    return normalized


@dataclass(frozen=True)
class CostModel:
    """Per-trade fee and slippage applied to an entry price, in basis points.

    Both ``fee_bps`` and ``slippage_bps`` must be finite and non-negative. The two
    are summed when a price is adjusted, so callers may model them separately but a
    single ``total_bps`` is what actually moves the price.
    """

    fee_bps: float = 0.0
    slippage_bps: float = 0.0

    def __post_init__(self) -> None:
        for name in ("fee_bps", "slippage_bps"):
            value = getattr(self, name)
            if not math.isfinite(value) or value < 0.0:
                raise ValueError(f"{name} must be finite and >= 0, got {value!r}")

