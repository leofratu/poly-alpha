"""End-to-end tests for the offline research CLI workflow."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from typer.testing import CliRunner

from poly_alpha.cli import app

runner = CliRunner()


def _invoke(args: list[str]) -> Any:
    """Invoke the top-level CLI with args, letting real errors surface."""
    return runner.invoke(app, args, catch_exceptions=False)


def _payload(result: Any) -> Any:
    """Parse the JSON payload from a successful CLI invocation."""
    assert result.exit_code == 0
    return json.loads(result.output)


def test_workflow_markets_all_json() -> None:
    payload = _payload(_invoke(["research", "markets", "--all", "--json"]))
    assert isinstance(payload, list)
    assert payload


def test_workflow_screen_json() -> None:
    payload = _payload(_invoke(["research", "screen", "--json"]))
    assert "summary" in payload
    assert "opportunities" in payload


def test_workflow_allocate_json_balances_bankroll() -> None:
    payload = _payload(_invoke(["research", "allocate", "--json"]))
    assert abs(payload["total_stake"] + payload["cash"] - payload["bankroll"]) < 1e-6


def test_workflow_run_json_reports_bundle() -> None:
    payload = _payload(_invoke(["research", "run", "--json"]))
    assert payload["simulated"] is True
