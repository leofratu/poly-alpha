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
        return list(self._markets)

    def research(self) -> list[dict]:
        return list(self._research)

    def risk(self) -> dict:
        return dict(self._risk)

    def compare(self) -> list[dict]:
        return list(self._compare)


class _ModuleProvider:
    """DataProvider composing the project's fixture, research, risk, and backtest modules."""

    def __init__(
        self,
        markets_fn: Callable[[], Sequence[MarketSnapshot]],
        research_fn: Callable[[Sequence[MarketSnapshot]], Sequence[object]],
        risk_fn: Callable[[], object],
        compare_fn: Callable[[], Sequence[object]],
    ) -> None:
        self._markets_fn = markets_fn
        self._research_fn = research_fn
        self._risk_fn = risk_fn
        self._compare_fn = compare_fn

    def markets(self) -> list[MarketSnapshot]:
        return list(self._markets_fn())

    def research(self) -> list[dict]:
        notes = self._research_fn(self.markets())
        return [cast(dict, _to_jsonable(note)) for note in notes]

    def risk(self) -> dict:
        return cast(dict, _to_jsonable(self._risk_fn()))

    def compare(self) -> list[dict]:
        return [cast(dict, _to_jsonable(metrics)) for metrics in self._compare_fn()]


def default_provider() -> DataProvider:
    """Build the real provider, falling back to static data when modules are absent."""
    try:
        from poly_alpha.adapters.fixtures import fixture_adapter
        from poly_alpha.backtesting.comparison import compare_strategies
