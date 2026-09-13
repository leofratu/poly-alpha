"""Standard-library-only read-only JSON API over the poly-alpha data contracts.

Most endpoints read from the injected DataProvider; `/curves`, `/calibration`, `/stress`,
`/allocate`, and `/run` are computed from the packaged fixture/demo datasets and are
intentionally not provider-injected.
"""

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

CAPABILITIES: tuple[str, ...] = (
    "markets",
    "research",
    "risk",
    "compare",
    "overview",
    "validation",
    "curves",
    "calibration",
    "stress",
    "allocate",
    "run",
)

INDEX_HTML = """<!doctype html>
<html lang="en"><head><meta charset="utf-8"><title>Poly-Alpha Research</title>
<style>
body{font-family:system-ui,sans-serif;margin:2rem;max-width:1100px}
table{border-collapse:collapse;width:100%;margin:1rem 0}
th,td{border:1px solid #ccc;padding:.35rem .5rem;text-align:right}
th:first-child,td:first-child{text-align:left}
.note{color:#7a4b00;background:#fff7e6;padding:.5rem .75rem;border-radius:4px}
</style></head><body>
<h1>Poly-Alpha Research</h1>
<p class="note">Read-only research and paper-trading view. Fixture, simulated, and synthetic
data are labeled and are not real. Not investment advice.</p>
<h2>Capabilities</h2><div id="health"></div>
<h2>Cross-market overview (top 10 by |edge|)</h2><div id="overview"></div>
<h2>Portfolio risk (demo)</h2><div id="risk"></div>
<h2>Allocation (demo)</h2><div id="allocation"></div>
<h2>Uncertainty coverage (demo)</h2><div id="calibration"></div>
<script>
async function load(){
  const h = await (await fetch('/health')).json();
  document.getElementById('health').textContent = (h.capabilities || []).join(', ');
  const o = await (await fetch('/overview')).json();
  const rows = (o.data || []).slice(0, 10).map(r => '<tr><td>' + r.market_id + '</td><td>' +
    r.asset_class + '</td><td>' + r.source_kind + '</td><td>' + (r.implied_yes ?? 'n/a') +
    '</td><td>' + r.model_yes.toFixed(3) + '</td><td>' + (r.edge >= 0 ? '+' : '') +
    r.edge.toFixed(3) + '</td><td>' + (r.simulated ? 'yes' : 'no') + '</td></tr>').join('');
  document.getElementById('overview').innerHTML =
    '<table><thead><tr><th>Market</th><th>Class</th><th>Kind</th><th>Implied</th>' +
    '<th>Model</th><th>Edge</th><th>Sim</th></tr></thead><tbody>' + rows + '</tbody></table>';
  const rk = await (await fetch('/risk')).json();
  const d = rk.data || {};
  document.getElementById('risk').textContent =
    'positions=' + d.n_positions + ' stake=' + d.total_stake + ' hhi=' + d.hhi +
    ' simulated=' + rk.simulated;
  const ca = await (await fetch('/calibration')).json();
  const cr = ca.data || {};
  document.getElementById('calibration').textContent =
    'markets=' + cr.n + ' coverage=' + cr.coverage + ' mean_width=' + cr.mean_width +
    ' simulated=' + ca.simulated;
  const al = await (await fetch('/allocate')).json();
  const ap = al.data || {};
  const allocs = (ap.allocations || []).map(a =>
    '<tr><td>' + a.market_id + '</td><td>' + a.fraction.toFixed(3) + '</td><td>' +
    a.stake.toFixed(2) + '</td></tr>').join('');
  document.getElementById('allocation').innerHTML =
    'deployed=' + ap.total_stake + ' cash=' + ap.cash + ' simulated=' + al.simulated +
    '<table><thead><tr><th>Market</th><th>Fraction</th><th>Stake</th></tr></thead><tbody>' +
    allocs + '</tbody></table>';
}
load();
</script></body></html>"""


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
        return [cast(dict, to_jsonable(note)) for note in notes]

    def risk(self) -> dict:
        return cast(dict, to_jsonable(self._risk_fn()))

    def compare(self) -> list[dict]:
        return [cast(dict, to_jsonable(metrics)) for metrics in self._compare_fn()]


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


def to_jsonable(value: object) -> object:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Mapping):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: to_jsonable(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    return value


def snapshot_to_dict(s: MarketSnapshot) -> dict:
    """Convert a snapshot into JSON-safe primitives."""
    return cast(dict, to_jsonable(s))


def _markets_are_simulated(provider: DataProvider) -> bool:
    """True when any served market is not real observed data.

    Used by /markets, /validation, /research, and /overview. /risk and /compare are always
    computed from the packaged demo dataset, so they report simulated=True directly.
    """
    return any(not market.provenance.kind.is_real for market in provider.markets())


def _handler_class(provider: DataProvider) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = urlsplit(self.path).path
            if path in ("/", "/index.html"):
                self._send_html(200, INDEX_HTML)
            elif path == "/health":
                from poly_alpha import __version__

                self._send(
                    200,
                    {
                        "status": "ok",
                        "version": __version__,
                        "capabilities": list(CAPABILITIES),
                    },
                )
            elif path == "/markets":
                markets = provider.markets()
                data = [snapshot_to_dict(market) for market in markets]
                self._send(
                    200,
                    {
                        "data": data,
                        "count": len(data),
                        "simulated": _markets_are_simulated(provider),
                    },
                )
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
                from poly_alpha.portfolio.risk import DEMO_CAVEAT

                self._send(
                    200,
                    {"data": provider.risk(), "simulated": True, "caveat": DEMO_CAVEAT},
                )
            elif path == "/compare":
                from poly_alpha.backtesting.comparison import CAVEAT

                self._send(
                    200,
                    {"data": provider.compare(), "simulated": True, "caveat": CAVEAT},
                )
            elif path == "/overview":
                from poly_alpha.research.overview import build_overview, dimensions

                rows = build_overview(provider.markets())
                self._send(
                    200,
                    {
                        "data": [to_jsonable(row) for row in rows],
                        "dimensions": dimensions(rows),
                        "simulated": _markets_are_simulated(provider),
                    },
                )
            elif path == "/validation":
                from poly_alpha.validation import validate_snapshot

                checks = [
                    {"market_id": market.market_id, "issues": list(validate_snapshot(market))}
                    for market in provider.markets()
                ]
                invalid = sum(1 for check in checks if check["issues"])
                self._send(
                    200,
                    {
                        "data": checks,
                        "invalid_count": invalid,
                        "simulated": _markets_are_simulated(provider),
                    },
                )
            elif path == "/curves":
                from poly_alpha.adapters.history import fixture_histories
                from poly_alpha.backtesting.strategies import default_strategies
                from poly_alpha.backtesting.walkforward import walk_forward

                rows = [
                    {
                        "market_id": history.market_id,
                        "strategy": name,
                        "result": to_jsonable(walk_forward(history, strategy)),
                    }
                    for history in fixture_histories()
                    for name, strategy in default_strategies().items()
                ]
                self._send(200, {"data": rows, "simulated": True})
            elif path == "/calibration":
                from poly_alpha.backtesting.demo_data import demo_resolved_markets
                from poly_alpha.research.analyst import research_markets
                from poly_alpha.research.calibration import (
                    calibration_by_kind,
                    interval_coverage,
                )

                markets = demo_resolved_markets()
                notes = research_markets([market.snapshot for market in markets])
                outcomes = [market.resolved_yes for market in markets]
                groups = calibration_by_kind(notes, outcomes)
                self._send(
                    200,
                    {
                        "data": to_jsonable(interval_coverage(notes, outcomes)),
                        "by_kind": {kind: to_jsonable(report) for kind, report in groups.items()},
                        "simulated": True,
                    },
                )
            elif path == "/stress":
                from poly_alpha.adapters.fixtures import fixture_adapter
                from poly_alpha.backtesting.demo_data import demo_positions
                from poly_alpha.portfolio.stress import run_scenarios

                prices = {
                    market.market_id: market.yes_price if market.yes_price is not None else 0.5
                    for market in fixture_adapter().list_markets()
                }
                results = run_scenarios(demo_positions(), prices)
                self._send(
                    200,
                    {"data": [to_jsonable(result) for result in results], "simulated": True},
                )
            elif path == "/allocate":
                from poly_alpha.adapters.registry import default_markets
                from poly_alpha.portfolio.allocate import allocate
                from poly_alpha.research.analyst import research_markets
                from poly_alpha.research.screen import rank_opportunities

                markets = default_markets()
                opportunities = rank_opportunities(
                    research_markets(markets), min_edge_low=float("-inf")
                )
                prices = {
                    market.market_id: market.yes_price if market.yes_price is not None else 0.5
                    for market in markets
                }
                self._send(
                    200,
                    {"data": to_jsonable(allocate(opportunities, prices)), "simulated": True},
                )
            elif path == "/run":
                from poly_alpha.research.pipeline import run_pipeline

                self._send(200, {"data": to_jsonable(run_pipeline()), "simulated": True})
            else:
                self._send(404, {"error": "not found", "path": path})

        def _reject(self) -> None:
            self._send(405, {"error": "method not allowed"})

        do_POST = _reject  # noqa: N815 - method name required by BaseHTTPRequestHandler
        do_PUT = _reject  # noqa: N815 - method name required by BaseHTTPRequestHandler
        do_PATCH = _reject  # noqa: N815 - method name required by BaseHTTPRequestHandler
        do_DELETE = _reject  # noqa: N815 - method name required by BaseHTTPRequestHandler

        def _send(self, status: int, payload: object) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _send_html(self, status: int, html: str) -> None:
            body = html.encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
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
