"""Execution-cost model for evaluating prediction-market edges net of fees.

The model is a pure calculation: it never places orders and never touches the
network. Costs are expressed in basis points (1 bp = 0.01%) and are applied to the
entry price so a strategy can compare a fair probability against a costed price.
A buy pays up and a sell receives less; both effective prices stay within [0, 1]
because a binary share cannot cost less than 0 or more than 1.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from poly_alpha.contracts import PriceLevel

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
class DepthFill:
    """Result of walking resting levels for a requested size."""

    shares: float
    notional: float
    average_price: float
    levels_consumed: int
    unfilled: float

    @property
    def is_complete(self) -> bool:
        return self.unfilled <= 0.0


def walk_book(levels: Sequence[PriceLevel], size: float, *, side: str = _BUY) -> DepthFill:
    """Walk resting levels to estimate the fill for ``size`` shares.

    A buy consumes the cheapest levels first; a sell consumes the highest bids first.
    The average price is notional-weighted. A request larger than the available depth
    is partially filled and reports the shortfall in ``unfilled``.
    """
    normalized = _normalize_side(side)
    if not math.isfinite(size) or size <= 0.0:
        raise ValueError(f"size must be finite and > 0, got {size!r}")
    ordered = sorted(levels, key=lambda level: level.price, reverse=normalized == _SELL)
    remaining = size
    notional = 0.0
    filled = 0.0
    consumed = 0
    for level in ordered:
        if remaining <= 0.0:
            break
        take = min(remaining, max(0.0, level.size))
        if take <= 0.0:
            continue
        notional += take * level.price
        filled += take
        remaining -= take
        consumed += 1
    return DepthFill(
        shares=filled,
        notional=notional,
        average_price=notional / filled if filled > 0.0 else 0.0,
        levels_consumed=consumed,
        unfilled=max(0.0, remaining),
    )


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

    @property
    def total_bps(self) -> float:
        """Combined fee and slippage, in basis points."""
        return self.fee_bps + self.slippage_bps

    def effective_price(self, price: float, side: str) -> float:
        """Return ``price`` moved by costs for the given ``side``, clamped to [0, 1].

        A buy pays the combined cost on top of ``price``; a sell gives it up. The
        clamp keeps the result a valid share price when costs would push it beyond
        the unit interval.
        """
        normalized = _normalize_side(side)
        fraction = self.total_bps / _BPS_PER_UNIT
        adjusted = price * (1.0 + fraction) if normalized == _BUY else price * (1.0 - fraction)
        return max(0.0, min(1.0, adjusted))

    def net_edge(
        self,
        *,
        fair_probability: float,
        price: float,
        side: str = _BUY,
    ) -> float:
        """Return the edge after costs, with each winning share paying out 1.0.

        For a buy the edge is ``fair_probability - effective_price("buy")``. For a
        sell the caller takes the other side, so the edge is
        ``(1 - fair_probability) - (1 - effective_price("sell"))``: the probability
        that the other side loses, minus the costed price of that other side. Both
        conventions use the same unit payoff of 1.0 per winning share.
        """
        normalized = _normalize_side(side)
        if normalized == _BUY:
            return fair_probability - self.effective_price(price, _BUY)
        return (1.0 - fair_probability) - (1.0 - self.effective_price(price, _SELL))
