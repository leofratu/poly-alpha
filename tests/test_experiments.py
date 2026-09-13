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
