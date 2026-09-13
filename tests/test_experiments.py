"""Tests for the persistent, reproducible research experiment records."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from poly_alpha.adapters.registry import default_markets
from poly_alpha.contracts import PriceLevel
from poly_alpha.research.experiments import (
    Experiment,
    append_experiment,
    build_experiment,
    experiment_from_dict,
    experiment_to_dict,
    fingerprint,
    read_experiments,
    reproduce,
)
from poly_alpha.research.pipeline import run_pipeline


def default_params() -> dict[str, float]:
    return {"bankroll": 1000.0, "cap": 0.05, "max_positions": 20, "max_deploy": 0.6}


def run_bundle(params: dict[str, float]):
    return run_pipeline(
        bankroll=params["bankroll"],
        cap=params["cap"],
        max_positions=int(params["max_positions"]),
        max_deploy=params["max_deploy"],
    )


def make_experiment() -> Experiment:
    markets = default_markets()
    params = default_params()
    return build_experiment(run_bundle(params), markets, params)


def test_fingerprint_is_deterministic_and_input_sensitive() -> None:
    markets = default_markets()
    params = default_params()
    base = fingerprint(markets, params)
    assert fingerprint(list(reversed(markets)), dict(params)) == base

    first_price = markets[0].yes_price
    bumped = 0.01 if first_price is None else first_price + 0.01
    changed_market = [replace(markets[0], yes_price=bumped), *markets[1:]]
    assert fingerprint(changed_market, params) != base
    assert fingerprint(markets, dict(params, cap=0.1)) != base

    requestioned = [replace(markets[0], question="A different question?"), *markets[1:]]
    assert fingerprint(requestioned, params) != base

    thicker_book = markets[0].orderbook + (PriceLevel(0.99, 10.0),)
    extended = [replace(markets[0], orderbook=thicker_book), *markets[1:]]
    assert fingerprint(extended, params) != base


def test_build_experiment_populates_fields_with_stable_run_id() -> None:
    markets = default_markets()
    params = default_params()
    bundle = run_bundle(params)
    first = build_experiment(bundle, markets, params)
    second = build_experiment(bundle, markets, dict(params))

    assert first.run_id == second.run_id
    assert first.market_count == bundle.market_count
    assert first.note_count == bundle.note_count
    assert first.opportunity_count == bundle.opportunity_count
    assert first.allocation_ids == tuple(a.market_id for a in bundle.allocations)
    assert first.total_stake == bundle.total_stake
    assert first.cash == bundle.cash
    assert first.params == params


def test_append_then_read_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "experiments.jsonl"
    first = make_experiment()
    second = make_experiment()
    append_experiment(path, first)
    append_experiment(path, second)
    assert read_experiments(path) == [first, second]


def test_read_experiments_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_experiments(tmp_path / "does-not-exist.jsonl") == []


def test_read_experiments_skips_malformed_and_mistyped_lines(tmp_path: Path) -> None:
    path = tmp_path / "experiments.jsonl"
    valid = experiment_to_dict(make_experiment())
    wrong_type = dict(valid, market_count="4")
    path.write_text(
        json.dumps(valid) + "\nnot json at all\n" + "123\n[1, 2]\n" + json.dumps(wrong_type) + "\n",
        encoding="utf-8",
    )
    experiments = read_experiments(path)
    assert len(experiments) == 1
    assert isinstance(experiments[0], Experiment)
    assert experiments[0].market_count == valid["market_count"]


def test_append_after_torn_line_does_not_merge_records(tmp_path: Path) -> None:
    path = tmp_path / "experiments.jsonl"
    experiment = make_experiment()
    path.write_text('{"torn":', encoding="utf-8")
    append_experiment(path, experiment)
    assert read_experiments(path) == [experiment]


def test_experiment_from_dict_rejects_missing_market_count() -> None:
    data = experiment_to_dict(make_experiment())
    del data["market_count"]
    with pytest.raises(ValueError):
        experiment_from_dict(data)


def test_experiment_from_dict_rejects_non_int_market_count() -> None:
    data = experiment_to_dict(make_experiment())
    data["market_count"] = "4"
    with pytest.raises(ValueError):
        experiment_from_dict(data)


def test_experiment_from_dict_rejects_non_numeric_total_stake() -> None:
    data = experiment_to_dict(make_experiment())
    data["total_stake"] = "nope"
    with pytest.raises(ValueError):
        experiment_from_dict(data)


def test_experiment_from_dict_rejects_bool_market_count() -> None:
    data = experiment_to_dict(make_experiment())
    data["market_count"] = True
    with pytest.raises(ValueError):
        experiment_from_dict(data)


def test_reproduce_false_when_a_parameter_changes() -> None:
    experiment = make_experiment()
    changed = replace(experiment, params=dict(experiment.params, bankroll=2000.0))
    assert reproduce(changed) is False


def test_reproduce_true_for_fresh_and_false_for_tampered() -> None:
    experiment = make_experiment()
    assert reproduce(experiment) is True
    tampered = replace(experiment, run_id="0" * 64)
    assert reproduce(tampered) is False
