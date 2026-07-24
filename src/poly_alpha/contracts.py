"""Common market/asset data contracts shared across adapters, research, and risk.

Every value that reaches research or reporting carries a `Provenance`, so simulated,
fixture, or synthetic data can never be silently mistaken for a real observation.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DataSourceKind(str, Enum):
    """How a dataset was produced. REAL is the only kind not derived from scratch."""

    REAL = "real"
    FIXTURE = "fixture"
    SIMULATED = "simulated"
    SYNTHETIC = "synthetic"

    @property
    def is_real(self) -> bool:
        return self is DataSourceKind.REAL


@dataclass(frozen=True)
class Provenance:
    """Where a datum came from, and whether it is real."""

    source: str
    kind: DataSourceKind
    retrieved_at: datetime | None = None
    url: str | None = None
    note: str = ""
