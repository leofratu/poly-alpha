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


def _market_implied(snapshot: MarketSnapshot) -> float | None:
    """Use the de-vigged market price as the fair YES probability."""
    return snapshot.implied_yes()


def _shin_debiased(snapshot: MarketSnapshot) -> float | None:
    """Use Shin (1992) debiasing of the de-vigged market price."""
    from poly_alpha.strategy import classify_category, shin_debiasing

    implied = snapshot.implied_yes()
    if implied is None:
        return None
    return shin_debiasing(implied, classify_category(snapshot.question))


def default_provider() -> DataProvider:
    """Build the offline research provider over labeled fixture and demo data."""
    try:
        from poly_alpha.adapters.registry import default_markets
        from poly_alpha.backtesting.comparison import compare_strategies
        from poly_alpha.backtesting.demo_data import (
            demo_positions,
            demo_resolved_markets,
            demo_returns,
        )
        from poly_alpha.portfolio.risk import analyze_portfolio
        from poly_alpha.research.analyst import research_markets
    except ImportError as exc:
        note = f"research modules unavailable: {exc}"
        return StaticProvider(risk={"status": "unavailable", "note": note})
    return _ModuleProvider(
        markets_fn=default_markets,
        research_fn=research_markets,
        risk_fn=lambda: analyze_portfolio(demo_positions(), demo_returns()),
        compare_fn=lambda: compare_strategies(
            demo_resolved_markets(),
            {"market_implied": _market_implied, "shin_debiased": _shin_debiased},
        ),
    )


def _to_jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): _to_jsonable(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (list, tuple, set)):
        return [_to_jsonable(item) for item in value]
    return value


def snapshot_to_dict(s: MarketSnapshot) -> dict:
    """Convert a snapshot into JSON-safe primitives."""
    return cast(dict, _to_jsonable(s))


def _markets_are_simulated(provider: DataProvider) -> bool:
    """True when any served market is not real observed data."""
    return any(not market.provenance.kind.is_real for market in provider.markets())


def _handler_class(provider: DataProvider) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path == "/health":
                self._send(200, {"status": "ok", "capabilities": list(CAPABILITIES)})
            elif path == "/markets":
                markets = provider.markets()
                data = [snapshot_to_dict(market) for market in markets]
                self._send(200, {"data": data, "count": len(data)})
            elif path == "/research":
                research = provider.research()
                simulated = _markets_are_simulated(provider) or any(
                    bool(note.get("model_yes", {}).get("simulated")) for note in research
                )
                self._send(
                    200,
                    {"data": research, "count": len(research), "simulated": simulated},
                )
            elif path == "/risk":
                self._send(
                    200,
                    {"data": provider.risk(), "simulated": _markets_are_simulated(provider)},
                )
            elif path == "/compare":
                from poly_alpha.backtesting.comparison import CAVEAT

                self._send(
                    200,
                    {
                        "data": provider.compare(),
                        "simulated": _markets_are_simulated(provider),
                        "caveat": CAVEAT,
                    },
                )
            else:
                self._send(404, {"error": "not found", "path": path})

        def _reject(self) -> None:
            self._send(405, {"error": "method not allowed"})

        do_POST = _reject
        do_PUT = _reject
        do_PATCH = _reject
        do_DELETE = _reject

        def _send(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, fmt: str, *args: object) -> None:
            pass

    return Handler


def create_server(
    host: str = "127.0.0.1",
    port: int = 0,
    provider: DataProvider | None = None,
) -> ThreadingHTTPServer:
    """Return a configured read-only JSON server bound to (host, port)."""
    active = provider if provider is not None else default_provider()
    return ThreadingHTTPServer((host, port), _handler_class(active))


if __name__ == "__main__":
    create_server(port=8000).serve_forever()
