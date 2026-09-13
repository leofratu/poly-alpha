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


@app.command()
def markets(
    json_out: bool = JSON_OPTION,
    all_kinds: bool = typer.Option(False, "--all", help="Include synthetic asset markets."),
) -> None:
    """List labeled offline markets (fixtures, plus synthetic with --all)."""
    if all_kinds:
        from poly_alpha.adapters.registry import default_markets

        snapshots = default_markets()
    else:
        snapshots = _fixture_markets()
    if json_out:
        from poly_alpha.api.server import snapshot_to_dict

        _print_json([snapshot_to_dict(snapshot) for snapshot in snapshots])
        return
    table = Table(title="Labeled markets (not real market data)")
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
def research(json_out: bool = JSON_OPTION) -> None:
    """Generate deterministic research notes for the fixture markets."""
    from poly_alpha.api.server import _to_jsonable
    from poly_alpha.research.analyst import model_vs_market, research_markets

    notes = research_markets(_fixture_markets())
    if json_out:
        _print_json([_to_jsonable(note) for note in notes])
        return
    table = Table(title="Fixture research (SIMULATED heuristic, not advice)")
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
    from poly_alpha.api.server import _to_jsonable
    from poly_alpha.backtesting.comparison import compare_strategies
    from poly_alpha.backtesting.demo_data import demo_resolved_markets
    from poly_alpha.backtesting.strategies import default_strategies

    metrics = compare_strategies(demo_resolved_markets(), default_strategies())
    if json_out:
        _print_json([_to_jsonable(item) for item in metrics])
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
    from poly_alpha.api.server import _to_jsonable
    from poly_alpha.backtesting.demo_data import demo_positions, demo_returns
    from poly_alpha.portfolio.risk import analyze_portfolio

    report = analyze_portfolio(demo_positions(), demo_returns())
    if json_out:
        _print_json(_to_jsonable(report))
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
) -> None:
    """Rank fixture markets by the lower bound of the model edge."""
    from poly_alpha.api.server import _to_jsonable
    from poly_alpha.research.analyst import research_markets
    from poly_alpha.research.screen import rank_opportunities, summarize

    opportunities = rank_opportunities(
        research_markets(_fixture_markets()), min_edge_low=min_edge_low
    )
    if json_out:
        payload = {
            "summary": summarize(opportunities),
            "opportunities": [_to_jsonable(item) for item in opportunities],
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
    from poly_alpha.research.report import render_markdown, write_markdown
    from poly_alpha.research.screen import rank_opportunities

    notes = research_markets(_fixture_markets())
    opportunities = rank_opportunities(notes, min_edge_low=float("-inf"))
    metrics = compare_strategies(demo_resolved_markets(), default_strategies())
    risk = analyze_portfolio(demo_positions(), demo_returns())
    content = render_markdown(notes, opportunities=opportunities, metrics=metrics, risk=risk)
    if output:
        write_markdown(output, content)
        console.print(f"[green]Wrote dossier to {output}[/green]")
        return
    typer.echo(content)


@app.command()
def size(json_out: bool = JSON_OPTION) -> None:
    """Size fixture opportunities with conservative fractional Kelly."""
    from poly_alpha.api.server import _to_jsonable
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
                "decision": _to_jsonable(decision),
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

