"""Tests for the offline research CLI surface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
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


def test_research_ai_without_key_falls_back_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLY_ALPHA_AI_API_KEY", raising=False)
    result = _invoke(["research", "research", "--ai", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert isinstance(payload, list) and payload
    assert all(note["model_yes"]["simulated"] is True for note in payload)
    assert all(not note["model_yes"]["basis"].startswith("ai:") for note in payload)


def test_research_ai_without_key_labels_heuristic_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("POLY_ALPHA_AI_API_KEY", raising=False)
    result = _invoke(["research", "research", "--ai"])
    assert result.exit_code == 0
    assert "AI provider unavailable" in result.output


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


def test_overview_limit_truncates_rows() -> None:
    result = _invoke(["research", "overview", "--limit", "3", "--json"])
    assert result.exit_code == 0
    assert len(json.loads(result.output)["rows"]) == 3


def test_validate_reports_no_issues_for_fixtures() -> None:
    result = _invoke(["research", "validate", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["invalid_count"] == 0
    assert payload["checks"]


def test_journal_and_history_round_trip(tmp_path: Path) -> None:
    log = tmp_path / "journal.jsonl"
    wrote = _invoke(["research", "journal", "--path", str(log), "--json"])
    assert wrote.exit_code == 0
    assert json.loads(wrote.output)["market_count"] >= 1
    read = _invoke(["research", "history", "--path", str(log), "--json"])
    assert read.exit_code == 0
    entries = json.loads(read.output)
    assert len(entries) == 1
    assert entries[0]["simulated"] is True


def test_history_summary_aggregates_entries(tmp_path: Path) -> None:
    log = tmp_path / "journal.jsonl"
    assert _invoke(["research", "journal", "--path", str(log), "--json"]).exit_code == 0
    result = _invoke(["research", "history", "--path", str(log), "--summary", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["runs"] == 1
    assert payload["total_markets"] >= 1
    assert payload["any_simulated"] is True


def test_strategy_lists_named_heuristics() -> None:
    result = _invoke(["research", "strategy", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert "uncertainty_gated" in payload
    assert all("heuristic" in text for text in payload.values())


def test_curves_json_emits_walk_forward_results() -> None:
    result = _invoke(["research", "curves", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload
    assert "equity_curve" in payload[0]["result"]


def test_calibration_json_reports_coverage() -> None:
    result = _invoke(["research", "calibration", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    report = payload["report"]
    assert report["n"] >= 1
    assert 0.0 <= report["coverage"] <= 1.0


def test_costs_json_applies_basis_points() -> None:
    result = _invoke(["research", "costs", "--fee-bps", "100", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["total_bps"] == 100.0
    assert payload["side"] == "buy"
    assert payload["rows"]


def test_costs_sell_side_is_supported() -> None:
    result = _invoke(["research", "costs", "--side", "sell", "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["side"] == "sell"


def test_version_command_prints_semver() -> None:
    result = _invoke(["version"])
    assert result.exit_code == 0
    assert "." in result.output


def test_stress_json_reports_scenarios() -> None:
    result = _invoke(["research", "stress", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    names = [row["scenario"] for row in payload]
    assert "base" in names
    assert any(row["change"] < 0 for row in payload)


def test_allocate_json_reports_plan() -> None:
    result = _invoke(["research", "allocate", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["bankroll"] == 1000.0
    assert "allocations" in payload
    assert abs(payload["cash"] + payload["total_stake"] - payload["bankroll"]) < 1e-6


def test_allocate_require_real_yields_empty_plan() -> None:
    result = _invoke(["research", "allocate", "--require-real", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["allocations"] == []
    assert payload["cash"] == payload["bankroll"]


def test_run_json_reports_bundle() -> None:
    result = _invoke(["research", "run", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["market_count"] >= 1
    assert payload["simulated"] is True
    assert abs(payload["total_stake"] + payload["cash"] - 1000.0) < 1e-6


def test_experiment_records_and_lists(tmp_path: Path) -> None:
    path = tmp_path / "experiments.jsonl"
    result = _invoke(["research", "experiment", "--path", str(path), "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["market_count"] >= 1
    assert payload["simulated"] is True

    listed = _invoke(["research", "experiments", "--path", str(path), "--json"])
    assert listed.exit_code == 0
    records = json.loads(listed.output)
    assert len(records) == 1
    assert records[0]["run_id"] == payload["run_id"]
    assert records[0]["simulated"] is True


def test_costs_without_size_has_no_depth_edges() -> None:
    result = _invoke(["research", "costs", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["size"] == 0.0
    assert payload["rows"]
    assert all(row["depth_net_edge"] is None for row in payload["rows"])


def test_costs_size_adds_depth_aware_edges() -> None:
    result = _invoke(["research", "costs", "--size", "1", "--json"])
    assert result.exit_code == 0
    payload = json.loads(result.output)
    assert payload["size"] == 1.0
    assert any(row["depth_net_edge"] is not None for row in payload["rows"])
