"""Persistent, reproducible, fully offline experiment records over deterministic runs.

Each record captures a deterministic fingerprint of the exact market inputs and
parameters that produced a :class:`~poly_alpha.research.pipeline.ResearchBundle`,
alongside the resulting outputs, and stores it as one UTF-8 JSON Line. Records are
reproducible: re-running the pipeline over the same markets and parameters yields the
same ``run_id``. This module never touches the network, uses no randomness, and places
no orders; its output is simulated, in-sample research material, not investment advice
and not a forecast.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from poly_alpha.adapters.registry import default_markets
from poly_alpha.contracts import MarketSnapshot
from poly_alpha.research.pipeline import ResearchBundle, run_pipeline

__all__ = [
    "DEFAULT_EXPERIMENTS_PATH",
    "Experiment",
    "append_experiment",
    "build_experiment",
    "experiment_from_dict",
    "experiment_to_dict",
    "fingerprint",
    "read_experiments",
    "reproduce",
]

DEFAULT_EXPERIMENTS_PATH = Path.home() / ".poly_alpha" / "experiments.jsonl"


@dataclass(frozen=True)
class Experiment:
    """A reproducible record of one deterministic offline research run."""

    run_id: str
    created_at: str
    params: dict[str, float]
    market_count: int
    note_count: int
    opportunity_count: int
    allocation_ids: tuple[str, ...]
    total_stake: float
    cash: float


def fingerprint(markets: Sequence[MarketSnapshot], params: Mapping[str, float]) -> str:
    """Return a deterministic sha256 fingerprint of the market inputs and ``params``.

    The payload is a canonical JSON object of each market's ``[market_id, yes_price,
    no_price, provenance kind, liquidity, volume]`` (markets sorted by ``market_id``)
    plus the sorted ``params`` items, so identical inputs share a fingerprint.
    """
    payload = {
        "markets": [
            [
                market.market_id,
                market.yes_price,
                market.no_price,
                market.provenance.kind.value,
                market.liquidity,
                market.volume,
            ]
            for market in sorted(markets, key=lambda market: market.market_id)
        ],
        "params": sorted(params.items()),
    }
    canonical = json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_experiment(
    bundle: ResearchBundle,
    markets: Sequence[MarketSnapshot],
    params: Mapping[str, float],
    *,
    created_at: datetime | None = None,
) -> Experiment:
    """Build an :class:`Experiment` recording ``bundle`` and its exact inputs.

    Supplying ``created_at`` makes the record fully deterministic; otherwise the
    current UTC time is used. ``run_id`` never depends on the timestamp.
    """
    created = created_at if created_at is not None else datetime.now(UTC)
    return Experiment(
        run_id=fingerprint(markets, params),
        created_at=created.isoformat(),
        params=dict(params),
        market_count=bundle.market_count,
        note_count=bundle.note_count,
        opportunity_count=bundle.opportunity_count,
        allocation_ids=tuple(allocation.market_id for allocation in bundle.allocations),
        total_stake=bundle.total_stake,
        cash=bundle.cash,
    )


def experiment_to_dict(experiment: Experiment) -> dict[str, object]:
    """Convert an experiment to a JSON-serializable dict."""
    return {
        "run_id": experiment.run_id,
        "created_at": experiment.created_at,
        "params": dict(experiment.params),
        "market_count": experiment.market_count,
        "note_count": experiment.note_count,
        "opportunity_count": experiment.opportunity_count,
        "allocation_ids": list(experiment.allocation_ids),
        "total_stake": experiment.total_stake,
        "cash": experiment.cash,
    }
