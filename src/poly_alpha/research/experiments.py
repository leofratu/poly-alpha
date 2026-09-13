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


def _require_str(data: Mapping[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _require_int(data: Mapping[str, object], key: str) -> int:
    value = data.get(key)
    if not isinstance(value, int):
        raise ValueError(f"{key} must be an int")
    return value


def _require_number(data: Mapping[str, object], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be a number")
    return float(value)


def experiment_from_dict(data: dict[str, object]) -> Experiment:
    """Rebuild an experiment from a dict, raising ``ValueError`` on bad fields."""
    raw_params = data.get("params")
    if not isinstance(raw_params, dict):
        raise ValueError("params must be an object")
    params: dict[str, float] = {}
    for key, value in raw_params.items():
        if not isinstance(value, (int, float)):
            raise ValueError("params values must be numbers")
        params[str(key)] = float(value)

    raw_ids = data.get("allocation_ids")
    if not isinstance(raw_ids, (list, tuple)):
        raise ValueError("allocation_ids must be a list")

    return Experiment(
        run_id=_require_str(data, "run_id"),
        created_at=_require_str(data, "created_at"),
        params=params,
        market_count=_require_int(data, "market_count"),
        note_count=_require_int(data, "note_count"),
        opportunity_count=_require_int(data, "opportunity_count"),
        allocation_ids=tuple(str(item) for item in raw_ids),
        total_stake=_require_number(data, "total_stake"),
        cash=_require_number(data, "cash"),
    )


def append_experiment(path: str | Path, experiment: Experiment) -> None:
    """Append ``experiment`` as one UTF-8 JSON line, creating parent directories."""
    experiments_path = Path(path)
    experiments_path.parent.mkdir(parents=True, exist_ok=True)
    line = json.dumps(experiment_to_dict(experiment), sort_keys=True)
    with experiments_path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")


def read_experiments(path: str | Path) -> list[Experiment]:
    """Read experiments from a JSONL file, returning ``[]`` when it is missing.

    Blank, malformed, or mistyped lines are skipped rather than raising, so a
    partially written or externally edited file never blocks readers.
    """
    experiments_path = Path(path)
    if not experiments_path.exists():
        return []
    experiments: list[Experiment] = []
    with experiments_path.open("r", encoding="utf-8") as handle:
        for line in handle:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                data = json.loads(stripped)
                experiments.append(experiment_from_dict(data))
            except (json.JSONDecodeError, KeyError, TypeError, ValueError):
                continue
    return experiments
