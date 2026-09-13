"""Tests for the offline research CLI surface."""

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


def test_markets_lists_labeled_fixtures() -> None:
    result = _invoke(["research", "markets"])
    assert result.exit_code == 0
    assert "labeled markets" in result.output


def test_markets_all_includes_synthetic() -> None:
    result = _invoke(["research", "markets", "--all"])
    assert result.exit_code == 0
    assert "labeled markets" in result.output
    assert "synthetic" in result.output


def test_research_json_emits_notes() -> None:
    result = _invoke(["research", "research", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list) and payload
    for note in payload:
        assert "market_id" in note
        assert "model_yes" in note


def test_screen_json_has_summary_and_opportunities() -> None:
    result = _invoke(["research", "screen", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "summary" in payload
    assert "opportunities" in payload


def test_size_json_emits_decisions() -> None:
    result = _invoke(["research", "size", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list) and payload
    for item in payload:
        assert "market_id" in item
        assert "decision" in item


def test_compare_json_emits_strategy_metrics() -> None:
    result = _invoke(["research", "compare", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list) and payload
    for item in payload:
        assert "roi" in item
        assert "trades" in item


def test_simulate_json_emits_results() -> None:
    result = _invoke(["research", "simulate", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list) and payload
    for item in payload:
        assert "strategy" in item
        simulated = item["result"]
        assert "equity_curve" in simulated
        assert "caveat" in simulated


def test_risk_json_reports_concentration() -> None:
    result = _invoke(["research", "risk", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, dict)
    assert "hhi" in payload
    assert "n_positions" in payload


def test_report_writes_markdown_dossier(tmp_path: Path) -> None:
    target = tmp_path / "out.md"
    result = _invoke(["research", "report", "--output", str(target)])
    assert result.exit_code == 0
    assert target.exists()
    content = target.read_text(encoding="utf-8")
    assert "not investment advice" in content
    assert "Provenance summary" in content


def test_help_succeeds() -> None:
    result = _invoke(["--help"])
    assert result.exit_code == 0


def test_overview_json_has_dimensions_and_rows() -> None:
    result = _invoke(["research", "overview", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["rows"]
    assert payload["dimensions"]["source_kind"]["fixture"] >= 1


def test_validate_reports_no_issues_for_fixtures() -> None:
    result = _invoke(["research", "validate", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["invalid_count"] == 0
    assert payload["checks"]
