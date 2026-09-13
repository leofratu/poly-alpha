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
