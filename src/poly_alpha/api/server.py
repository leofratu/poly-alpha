"""Standard-library-only read-only JSON API over the poly-alpha data contracts."""

from __future__ import annotations

import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import fields, is_dataclass
from datetime import datetime
from enum import Enum
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Protocol, cast
from urllib.parse import urlsplit

from poly_alpha.contracts import MarketSnapshot

CAPABILITIES: tuple[str, ...] = ("markets", "research", "risk", "compare")


class DataProvider(Protocol):
    """Source of the data the API serves."""

    def markets(self) -> list[MarketSnapshot]: ...

    def research(self) -> list[dict]: ...

    def risk(self) -> dict: ...

    def compare(self) -> list[dict]: ...


class StaticProvider:
    """DataProvider that returns values injected at construction time."""

    def __init__(
        self,
        markets: Sequence[MarketSnapshot] = (),
        research: Sequence[dict] = (),
        risk: Mapping[str, object] | None = None,
        compare: Sequence[dict] = (),
    ) -> None:
        self._markets = list(markets)
        self._research = [dict(item) for item in research]
        self._risk = dict(risk) if risk is not None else {}
        self._compare = [dict(item) for item in compare]

    def markets(self) -> list[MarketSnapshot]:
