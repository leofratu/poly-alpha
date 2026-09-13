"""CLI commands for the offline research platform.

Every command defaults to labeled fixture or demo data, never places live orders,
and never requires network access.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
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
def markets(json_out: bool = JSON_OPTION) -> None:
    """List labeled fixture markets available offline."""
    snapshots = _fixture_markets()
    if json_out:
        from poly_alpha.api.server import snapshot_to_dict

        _print_json([snapshot_to_dict(snapshot) for snapshot in snapshots])
        return
    table = Table(title="Fixture markets (FIXTURE data, not real)")
    table.add_column("Market", style="cyan")
    table.add_column("Class")
    table.add_column("Yes", justify="right")
    table.add_column("No", justify="right")
    table.add_column("Liquidity", justify="right")
    for snapshot in snapshots:
        table.add_row(
            snapshot.market_id,
            snapshot.asset.asset_class,
            f"{snapshot.yes_price:.2f}" if snapshot.yes_price is not None else "n/a",
            f"{snapshot.no_price:.2f}" if snapshot.no_price is not None else "n/a",
            f"{snapshot.liquidity:,.0f}",
        )
    console.print(table)
    console.print(f"[yellow]{len(snapshots)} fixture markets; source kind FIXTURE.[/yellow]")


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


def _strategies() -> dict[str, Callable[[Any], float | None]]:
    from poly_alpha.strategy import classify_category, shin_debiasing

    def market_implied(snapshot: Any) -> float | None:
        return snapshot.implied_yes()
