"""Dependency-free validation helpers for the shared market and interval contracts.

Validators never raise on bad data; they return human-readable issue strings so
callers can decide whether to reject, log, or repair a snapshot.
"""

from __future__ import annotations

import math

from poly_alpha.contracts import MarketSnapshot, Uncertainty


def _check_probability(name: str, value: float | None, issues: list[str]) -> None:
    """Append an issue when a set probability is not strictly within (0, 1)."""
    if value is None:
        return
    if not math.isfinite(value) or not 0.0 < value < 1.0:
        issues.append(f"{name} must be strictly within (0, 1), got {value!r}")


def validate_snapshot(snapshot: MarketSnapshot) -> tuple[str, ...]:
    """Return readable issues found in a snapshot, or an empty tuple when valid."""
    issues: list[str] = []
    if not snapshot.market_id.strip():
        issues.append("market_id must be non-empty")
    if not snapshot.question.strip():
        issues.append("question must be non-empty")
    if not snapshot.provenance.source.strip():
        issues.append("provenance.source must be non-empty")
    _check_probability("yes_price", snapshot.yes_price, issues)
    _check_probability("no_price", snapshot.no_price, issues)
    if not math.isfinite(snapshot.liquidity) or snapshot.liquidity < 0.0:
        issues.append(f"liquidity must be finite and >= 0, got {snapshot.liquidity!r}")
    if not math.isfinite(snapshot.volume) or snapshot.volume < 0.0:
        issues.append(f"volume must be finite and >= 0, got {snapshot.volume!r}")
    if snapshot.close_time is not None and snapshot.close_time.tzinfo is None:
        issues.append("close_time must be timezone-aware")
    for index, level in enumerate(snapshot.orderbook):
        if not math.isfinite(level.price) or not 0.0 < level.price < 1.0:
            issues.append(
                f"orderbook[{index}].price must be strictly within (0, 1), got {level.price!r}"
            )
        if not math.isfinite(level.size) or level.size < 0.0:
            issues.append(f"orderbook[{index}].size must be finite and >= 0, got {level.size!r}")
    return tuple(issues)
