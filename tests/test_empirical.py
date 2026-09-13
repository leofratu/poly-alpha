"""Tests for the synthetic empirical Monte Carlo (offline, seeded)."""

from __future__ import annotations

import pytest

from poly_alpha.backtesting import empirical


def test_get_win_rate_applies_category_adjustment() -> None:
    base, _ = empirical.get_win_rate(0.90, "middle", "other")
    politics, _ = empirical.get_win_rate(0.90, "middle", "politics")
    sports, _ = empirical.get_win_rate(0.90, "middle", "sports")
    assert politics > base > sports


def test_run_is_deterministic_and_labeled_synthetic() -> None:
    first = empirical.run(n_trials=2_000, trades_per_cycle=10, seed=1)
    second = empirical.run(n_trials=2_000, trades_per_cycle=10, seed=1)
    assert first == second
    assert first["synthetic"] == 1.0
    assert "not a backtest" in str(first["caveat"])


def test_run_uses_category_adjustments(monkeypatch: pytest.MonkeyPatch) -> None:
    base = empirical.run(n_trials=2_000, trades_per_cycle=10, seed=1)["mean"]
    monkeypatch.setattr(empirical, "CATEGORY_ADJ", dict.fromkeys(empirical.CATEGORY_ADJ, -0.30))
    lowered = empirical.run(n_trials=2_000, trades_per_cycle=10, seed=1)["mean"]
    assert lowered < base
