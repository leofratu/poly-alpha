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
