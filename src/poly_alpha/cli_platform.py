"""CLI commands for the offline research platform.

Every command defaults to labeled fixture or demo data, never places live orders,
and never requires network access.
"""

from __future__ import annotations

import json
from typing import Any

import typer
from rich.console import Console
from rich.table import Table

app = typer.Typer(help="Research platform: markets, research, compare, risk, serve.")
console = Console()

JSON_OPTION = typer.Option(False, "--json", help="Emit machine-readable JSON.")


def _print_json(payload: Any) -> None:
    typer.echo(json.dumps(payload, indent=2, sort_keys=True, default=str))


def _fixture_markets() -> list[Any]:
    from poly_alpha.adapters.fixtures import fixture_adapter

    return fixture_adapter().list_markets()


def _real_markets() -> list[Any]:
    import requests

    from poly_alpha.adapters.polymarket import PolymarketAdapter

    try:
        return PolymarketAdapter().list_markets()
    except requests.RequestException as exc:
        console.print(f"[red]Could not fetch real markets: {exc}[/red]")
        return []


REAL_OPTION = typer.Option(False, "--real", help="Fetch real Polymarket markets (network).")


@app.command()
def markets(
    json_out: bool = JSON_OPTION,
    all_kinds: bool = typer.Option(False, "--all", help="Include synthetic asset markets."),
    real: bool = REAL_OPTION,
) -> None:
    """List markets: labeled fixtures, synthetic with --all, or real Polymarket with --real."""
    if real:
        snapshots = _real_markets()
    elif all_kinds:
        from poly_alpha.adapters.registry import default_markets

        snapshots = default_markets()
    else:
        snapshots = _fixture_markets()
    if json_out:
        from poly_alpha.api.server import snapshot_to_dict

        _print_json([snapshot_to_dict(snapshot) for snapshot in snapshots])
        return
    title = (
        "Real Polymarket markets (network; not investment advice)"
        if real
        else "Labeled markets (not real market data)"
    )
    table = Table(title=title)
    table.add_column("Market", style="cyan")
    table.add_column("Class")
    table.add_column("Kind")
    table.add_column("Yes", justify="right")
    table.add_column("No", justify="right")
    table.add_column("Liquidity", justify="right")
    for snapshot in snapshots:
        table.add_row(
            snapshot.market_id,
            snapshot.asset.asset_class,
            snapshot.provenance.kind.value,
            f"{snapshot.yes_price:.2f}" if snapshot.yes_price is not None else "n/a",
            f"{snapshot.no_price:.2f}" if snapshot.no_price is not None else "n/a",
            f"{snapshot.liquidity:,.0f}",
        )
    console.print(table)
    console.print(f"[yellow]{len(snapshots)} labeled markets; see provenance kind column.[/yellow]")


@app.command()
def research(json_out: bool = JSON_OPTION, real: bool = REAL_OPTION) -> None:
    """Generate deterministic research notes for the selected markets."""
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.research.analyst import model_vs_market, research_markets

    notes = research_markets(_real_markets() if real else _fixture_markets())
    if json_out:
        _print_json([to_jsonable(note) for note in notes])
        return
    table = Table(title="Research notes (SIMULATED heuristic; check provenance)")
    table.add_column("Market", style="cyan")
    table.add_column("Mkt", justify="right")
    table.add_column("Model", justify="right")
    table.add_column("Edge", justify="right")
    table.add_column("Basis")
    for note in notes:
        edge = model_vs_market(note)
        table.add_row(
            note.market_id,
            f"{note.market_implied_yes:.2f}" if note.market_implied_yes is not None else "n/a",
            f"{note.model_yes.estimate:.2f}",
            f"{edge:+.3f}" if edge is not None else "n/a",
            note.model_yes.basis,
        )
    console.print(table)


@app.command()
def compare(json_out: bool = JSON_OPTION) -> None:
    """Compare strategies over labeled demo resolved markets."""
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.backtesting.comparison import compare_strategies
    from poly_alpha.backtesting.demo_data import demo_resolved_markets
    from poly_alpha.backtesting.strategies import default_strategies

    metrics = compare_strategies(demo_resolved_markets(), default_strategies())
    if json_out:
        _print_json([to_jsonable(item) for item in metrics])
        return
    table = Table(title="Strategy comparison (DEMO resolutions, in-sample)")
    table.add_column("Strategy", style="cyan")
    table.add_column("Trades", justify="right")
    table.add_column("Hit rate", justify="right")
    table.add_column("PnL", justify="right")
    table.add_column("Max DD", justify="right")
    for item in metrics:
        table.add_row(
            item.name,
            str(item.trades),
            f"{item.hit_rate:.0%}",
            f"{item.total_pnl:+,.2f}",
            f"{item.max_drawdown:.0%}",
        )
    console.print(table)
    if metrics:
        console.print(f"[yellow]{metrics[0].caveat}[/yellow]")


@app.command()
def risk(json_out: bool = JSON_OPTION) -> None:
    """Report concentration and historical risk for the demo portfolio."""
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.backtesting.demo_data import demo_positions, demo_returns
    from poly_alpha.portfolio.risk import analyze_portfolio

    report = analyze_portfolio(demo_positions(), demo_returns())
    if json_out:
        _print_json(to_jsonable(report))
        return
    table = Table(title="Demo portfolio risk (SIMULATED positions/returns)")
    table.add_column("Metric", style="cyan")
    table.add_column("Value", justify="right")
    table.add_row("Positions", str(report.n_positions))
    table.add_row("Total stake", f"{report.total_stake:,.2f}")
    table.add_row("HHI", f"{report.hhi:.3f}")
    table.add_row("Max position", f"{report.max_position_fraction:.0%}")
    var = report.historical_var_95
    table.add_row("Historical VaR 95", f"{var:.3f}" if var is not None else "n/a")
    table.add_row("Max drawdown", f"{report.max_drawdown:.0%}")
    console.print(table)
    for note in report.notes:
        console.print(f"[yellow]{note}[/yellow]")


@app.command()
def serve(
    host: str = typer.Option("127.0.0.1", help="Bind address (loopback only by default)."),
    port: int = typer.Option(8000, help="TCP port."),
) -> None:
    """Serve the read-only research JSON API (loopback)."""
    from poly_alpha.api.server import create_server

    server = create_server(host=host, port=port)
    console.print(
        f"[green]Serving read-only research API on "
        f"http://{host}:{server.server_address[1]}[/green]"
    )
    server.serve_forever()


@app.command()
def screen(
    json_out: bool = JSON_OPTION,
    min_edge_low: float = typer.Option(0.0, help="Minimum conservative edge bound."),
    require_real: bool = typer.Option(False, "--require-real", help="Keep only real data."),
) -> None:
    """Rank labeled offline markets by the lower bound of the model edge."""
    from poly_alpha.adapters.registry import default_markets
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.research.analyst import research_markets
    from poly_alpha.research.screen import rank_opportunities, summarize

    opportunities = rank_opportunities(
        research_markets(default_markets()),
        min_edge_low=min_edge_low,
        require_real=require_real,
    )
    if json_out:
        payload = {
            "summary": summarize(opportunities),
            "opportunities": [to_jsonable(item) for item in opportunities],
        }
        _print_json(payload)
        return
    table = Table(title="Screened opportunities (SIMULATED, conservative lower bound)")
    table.add_column("Market", style="cyan")
    table.add_column("Edge low", justify="right")
    table.add_column("Edge high", justify="right")
    table.add_column("Real")
    for item in opportunities:
        table.add_row(
            item.note.market_id,
            f"{item.edge_low:+.3f}",
            f"{item.edge_high:+.3f}",
            "yes" if item.is_real else "no",
        )
    console.print(table)
    console.print(
        "[yellow]Edges are simulated heuristics; 'Real' is market-data provenance only. "
        "Not investment advice.[/yellow]"
    )


@app.command()
def report(
    output: str = typer.Option("", help="Write Markdown here instead of stdout."),
) -> None:
    """Render a provenance-tagged Markdown dossier over the fixtures."""
    from poly_alpha.backtesting.comparison import compare_strategies
    from poly_alpha.backtesting.demo_data import (
        demo_positions,
        demo_resolved_markets,
        demo_returns,
    )
    from poly_alpha.backtesting.strategies import default_strategies
    from poly_alpha.portfolio.risk import analyze_portfolio
    from poly_alpha.research.analyst import research_markets
    from poly_alpha.research.calibration import demo_calibration
    from poly_alpha.research.report import render_markdown, write_markdown
    from poly_alpha.research.screen import rank_opportunities

    notes = research_markets(_fixture_markets())
    opportunities = rank_opportunities(notes, min_edge_low=float("-inf"))
    metrics = compare_strategies(demo_resolved_markets(), default_strategies())
    risk = analyze_portfolio(demo_positions(), demo_returns())
    content = render_markdown(
        notes,
        opportunities=opportunities,
        metrics=metrics,
        risk=risk,
        calibration=demo_calibration(),
    )
    if output:
        write_markdown(output, content)
        console.print(f"[green]Wrote dossier to {output}[/green]")
        return
    typer.echo(content)


@app.command()
def size(json_out: bool = JSON_OPTION) -> None:
    """Size fixture opportunities with conservative fractional Kelly."""
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.portfolio.sizing import kelly_fraction
    from poly_alpha.research.analyst import research_market

    decisions = []
    for snapshot in _fixture_markets():
        if snapshot.yes_price is None or snapshot.no_price is None:
            continue
        note = research_market(snapshot)
        decision = kelly_fraction(
            probability=note.model_yes.estimate,
            price=snapshot.yes_price,
            uncertainty=note.model_yes,
        )
        decisions.append((note.market_id, snapshot.yes_price, decision))
    if json_out:
        payload = [
            {
                "market_id": market_id,
                "price": price,
                "decision": to_jsonable(decision),
            }
            for market_id, price, decision in decisions
        ]
        _print_json(payload)
        return
    table = Table(title="Conservative sizing (SIMULATED, lower-bound Kelly)")
    table.add_column("Market", style="cyan")
    table.add_column("Price", justify="right")
    table.add_column("Prob used", justify="right")
    table.add_column("Fraction", justify="right")
    table.add_column("Capped")
    for market_id, price, decision in decisions:
        table.add_row(
            market_id,
            f"{price:.2f}",
            f"{decision.probability_used:.2f}",
            f"{decision.fraction:.3f}",
            "yes" if decision.capped else "no",
        )
    console.print(table)


@app.command()
def simulate(json_out: bool = JSON_OPTION) -> None:
    """Paper-simulate strategies over labeled demo resolutions (in-sample)."""
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.backtesting.demo_data import demo_resolved_markets
    from poly_alpha.backtesting.simulation import simulate_portfolio
    from poly_alpha.backtesting.strategies import default_strategies

    markets = demo_resolved_markets()
    results = [
        (name, simulate_portfolio(markets, strategy))
        for name, strategy in default_strategies().items()
    ]
    if json_out:
        payload = [{"strategy": name, "result": to_jsonable(result)} for name, result in results]
        _print_json(payload)
        return
    table = Table(title="Paper simulation (DEMO resolutions, in-sample, simulated)")
    table.add_column("Strategy", style="cyan")
    table.add_column("Trades", justify="right")
    table.add_column("Ending", justify="right")
    table.add_column("Max DD", justify="right")
    for name, result in results:
        table.add_row(
            name,
            str(result.trades),
            f"{result.ending_bankroll:,.2f}",
            f"{result.max_drawdown:.1%}",
        )
    console.print(table)
    if results:
        console.print(f"[yellow]{results[0][1].caveat}[/yellow]")


@app.command()
def overview(json_out: bool = JSON_OPTION) -> None:
    """Rank labeled offline markets by absolute research edge."""
    from poly_alpha.adapters.registry import default_markets
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.research.overview import build_overview, dimensions, overview_rows

    rows = build_overview(default_markets())
    if json_out:
        payload = {
            "dimensions": dimensions(rows),
            "rows": [to_jsonable(row) for row in rows],
        }
        _print_json(payload)
        return
    table = Table(title="Market overview (labeled offline data; simulated estimates)")
    table.add_column("Market")
    table.add_column("Class")
    table.add_column("Kind")
    table.add_column("Implied", justify="right")
    table.add_column("Model", justify="right")
    table.add_column("Edge", justify="right")
    table.add_column("Width", justify="right")
    table.add_column("Sim")
    for row in overview_rows(rows):
        table.add_row(*row)
    console.print(table)
    console.print(
        "[yellow]Model estimates are simulated heuristics; not investment advice.[/yellow]"
    )


@app.command()
def validate(json_out: bool = JSON_OPTION) -> None:
    """Check labeled offline markets against the shared contract invariants."""
    from poly_alpha.adapters.registry import default_markets
    from poly_alpha.validation import validate_snapshot

    checks = [
        {"market_id": market.market_id, "issues": list(validate_snapshot(market))}
        for market in default_markets()
    ]
    invalid = sum(1 for check in checks if check["issues"])
    if json_out:
        _print_json({"invalid_count": invalid, "checks": checks})
        return
    console.print(f"[green]{len(checks)} markets checked; {invalid} with issues.[/green]")
    for check in checks:
        for issue in check["issues"]:
            console.print(f"[yellow]{check['market_id']}: {issue}[/yellow]")


JOURNAL_PATH = typer.Option(
    "~/.poly_alpha/research_journal.jsonl", help="Append-only journal file path."
)


@app.command()
def journal(path: str = JOURNAL_PATH, json_out: bool = JSON_OPTION) -> None:
    """Append a provenance summary of a fixture research run to the journal."""
    import os

    from poly_alpha.research.analyst import research_markets
    from poly_alpha.research.journal import append_entry, build_entry, entry_to_dict

    entry = build_entry(research_markets(_fixture_markets()))
    target = os.path.expanduser(path)
    append_entry(target, entry)
    payload = entry_to_dict(entry)
    if json_out:
        _print_json(payload)
        return
    console.print(f"[green]Appended research journal entry to {target}.[/green]")
    console.print(
        f"[white]{entry.market_count} markets | mean edge {entry.mean_edge:+.4f} "
        f"| simulated={entry.simulated}[/white]"
    )


@app.command()
def history(path: str = JOURNAL_PATH, json_out: bool = JSON_OPTION) -> None:
    """List recorded research journal entries."""
    import os

    from poly_alpha.api.server import to_jsonable
    from poly_alpha.research.journal import read_entries

    entries = read_entries(os.path.expanduser(path))
    if json_out:
        _print_json([to_jsonable(entry) for entry in entries])
        return
    table = Table(title="Research journal (provenance audit; simulated estimates)")
    table.add_column("Recorded")
    table.add_column("Markets", justify="right")
    table.add_column("Mean edge", justify="right")
    table.add_column("Top")
    table.add_column("Sim")
    for entry in entries:
        table.add_row(
            entry.recorded_at,
            str(entry.market_count),
            f"{entry.mean_edge:+.4f}",
            entry.top_market_id or "n/a",
            "yes" if entry.simulated else "no",
        )
    console.print(table)


@app.command()
def strategy(json_out: bool = JSON_OPTION) -> None:
    """List the named heuristic strategies and what each one assumes."""
    from poly_alpha.backtesting.strategies import describe

    descriptions = describe()
    if json_out:
        _print_json(descriptions)
        return
    table = Table(title="Strategy ideas (heuristics; no validated performance)")
    table.add_column("Strategy", style="cyan")
    table.add_column("Description")
    for name, text in descriptions.items():
        table.add_row(name, text)
    console.print(table)


@app.command()
def curves(json_out: bool = JSON_OPTION) -> None:
    """Walk each named strategy forward over deterministic fixture histories."""
    from poly_alpha.adapters.history import fixture_histories
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.backtesting.strategies import default_strategies
    from poly_alpha.backtesting.walkforward import walk_forward

    results = [
        (history.market_id, name, walk_forward(history, strategy))
        for history in fixture_histories()
        for name, strategy in default_strategies().items()
    ]
    if json_out:
        payload = [
            {"market_id": market_id, "strategy": name, "result": to_jsonable(result)}
            for market_id, name, result in results
        ]
        _print_json(payload)
        return
    table = Table(title="Walk-forward (SIMULATED fixture histories, in-sample)")
    table.add_column("Market")
    table.add_column("Strategy", style="cyan")
    table.add_column("Trades", justify="right")
    table.add_column("Ending", justify="right")
    table.add_column("Max DD", justify="right")
    for market_id, name, result in results:
        table.add_row(
            market_id,
            name,
            str(result.trades),
            f"{result.ending_bankroll:,.2f}",
            f"{result.max_drawdown:.1%}",
        )
    console.print(table)
    if results:
        console.print(f"[yellow]{results[0][2].caveat}[/yellow]")


@app.command()
def calibration(json_out: bool = JSON_OPTION) -> None:
    """Report uncertainty-interval coverage over labeled demo resolutions."""
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.backtesting.demo_data import demo_resolved_markets
    from poly_alpha.research.analyst import research_markets
    from poly_alpha.research.calibration import calibration_by_kind, interval_coverage

    markets = demo_resolved_markets()
    notes = research_markets([market.snapshot for market in markets])
    outcomes = [market.resolved_yes for market in markets]
    report = interval_coverage(notes, outcomes)
    groups = calibration_by_kind(notes, outcomes)
    if json_out:
        payload = {
            "report": to_jsonable(report),
            "by_kind": {kind: to_jsonable(value) for kind, value in groups.items()},
        }
        _print_json(payload)
        return
    table = Table(title="Uncertainty coverage (DEMO resolutions; not real-world evidence)")
    table.add_column("Group", style="cyan")
    table.add_column("N", justify="right")
    table.add_column("Coverage", justify="right")
    table.add_column("Mean width", justify="right")
    table.add_row("all", str(report.n), f"{report.coverage:.0%}", f"{report.mean_width:.3f}")
    for kind, value in groups.items():
        table.add_row(kind, str(value.n), f"{value.coverage:.0%}", f"{value.mean_width:.3f}")
    console.print(table)
    for note in report.notes:
        console.print(f"[yellow]{note}[/yellow]")


@app.command()
def costs(
    fee_bps: float = typer.Option(0.0, help="Fee in basis points."),
    slippage_bps: float = typer.Option(0.0, help="Slippage in basis points."),
    json_out: bool = JSON_OPTION,
) -> None:
    """Show fee/slippage-adjusted edges for the fixture markets."""
    from poly_alpha.backtesting.costs import CostModel
    from poly_alpha.research.analyst import research_markets
    from poly_alpha.research.screen import rank_opportunities

    model = CostModel(fee_bps=fee_bps, slippage_bps=slippage_bps)
    opportunities = rank_opportunities(
        research_markets(_fixture_markets()), min_edge_low=float("-inf")
    )
    rows = []
    for opportunity in opportunities:
        implied = opportunity.note.market_implied_yes
        if implied is None:
            continue
        rows.append(
            {
                "market_id": opportunity.note.market_id,
                "gross_edge": opportunity.note.edge.estimate,
                "net_edge": model.net_edge(
                    fair_probability=opportunity.note.model_yes.estimate,
                    price=implied,
                    side="buy",
                ),
            }
        )
    if json_out:
        _print_json(
            {
                "total_bps": model.total_bps,
                "rows": rows,
                "simulated": True,
                "caveat": "Simulated cost-adjusted edges over labeled fixture data; not advice.",
            }
        )
        return
    table = Table(title="Cost-adjusted buy edges (SIMULATED; gross vs net)")
    table.add_column("Market", style="cyan")
    table.add_column("Gross", justify="right")
    table.add_column("Net", justify="right")
    for row in rows:
        table.add_row(
            row["market_id"],
            f"{row['gross_edge']:+.4f}",
            f"{row['net_edge']:+.4f}",
        )
    console.print(table)
    console.print(
        f"[yellow]Assumed cost {model.total_bps:.0f} bps. Not investment advice.[/yellow]"
    )


@app.command()
def stress(json_out: bool = JSON_OPTION) -> None:
    """Run deterministic price-shock scenarios over the demo portfolio."""
    from poly_alpha.adapters.fixtures import fixture_adapter
    from poly_alpha.api.server import to_jsonable
    from poly_alpha.backtesting.demo_data import demo_positions
    from poly_alpha.portfolio.stress import run_scenarios

    prices = {
        market.market_id: market.yes_price if market.yes_price is not None else 0.5
        for market in fixture_adapter().list_markets()
    }
    results = run_scenarios(demo_positions(), prices)
    if json_out:
        _print_json([to_jsonable(result) for result in results])
        return
    table = Table(title="Portfolio stress (SIMULATED demo positions; not advice)")
    table.add_column("Scenario", style="cyan")
    table.add_column("Start", justify="right")
    table.add_column("Stressed", justify="right")
    table.add_column("Change", justify="right")
    table.add_column("Worst")
    for result in results:
        table.add_row(
            result.scenario,
            f"{result.start_value:,.2f}",
            f"{result.stressed_value:,.2f}",
            f"{result.change:+,.2f}",
            result.worst_market_id or "n/a",
        )
    console.print(table)
