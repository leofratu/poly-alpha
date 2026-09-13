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
    assert payload["market_count"] >= 1
    assert abs(payload["total_stake"] + payload["cash"] - 1000.0) < 1e-6


def test_workflow_report_writes_dossier(tmp_path: Path) -> None:
    target = tmp_path / "dossier.md"
    result = _invoke(["research", "report", "--output", str(target)])
    assert result.exit_code == 0
    content = target.read_text(encoding="utf-8")
    assert "Provenance summary" in content
    assert "Allocation (simulated)" in content
    assert "not investment advice" in content


def test_workflow_journal_then_history_summary(tmp_path: Path) -> None:
    log = tmp_path / "runs.jsonl"
    assert _invoke(["research", "journal", "--path", str(log), "--json"]).exit_code == 0
    payload = _payload(
        _invoke(["research", "history", "--path", str(log), "--summary", "--json"])
    )
    assert payload["runs"] >= 1
    assert payload["any_simulated"] is True


def test_workflow_run_is_deterministic() -> None:
    first = _payload(_invoke(["research", "run", "--json"]))
    second = _payload(_invoke(["research", "run", "--json"]))
    assert first == second
