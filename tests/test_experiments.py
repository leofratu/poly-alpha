"""Tests for the persistent, reproducible research experiment records."""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

import pytest

from poly_alpha.adapters.registry import default_markets
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
