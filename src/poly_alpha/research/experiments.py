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
