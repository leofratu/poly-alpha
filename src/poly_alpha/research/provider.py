"""Optional research providers over market snapshots.

The default provider is :class:`HeuristicProvider`, which delegates to the deterministic,
fully offline engine in ``poly_alpha.research.analyst``. That engine is a HEURISTIC and
NOT an AI model: its estimate is a pure function of the snapshot.

The AI provider (:class:`OpenAICompatibleProvider`) is optional, requires an API key, and
falls back to the heuristic on any error. Its estimates are simulated model output, not
observations: they are tagged ``simulated=True`` and every caveat says so. Provider output
is research and paper-trading material only and is never investment advice.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, datetime
from typing import Any, Protocol

import requests

from poly_alpha.contracts import DataSourceKind, MarketSnapshot, Provenance, Uncertainty
from poly_alpha.research.analyst import research_market as _heuristic_research_market
from poly_alpha.research.notes import ResearchClaim, ResearchNote

DEFAULT_AI_BASE_URL = "https://api.openai.com/v1"
DEFAULT_AI_MODEL = "gpt-4.1-mini"
DEFAULT_TIMEOUT = 30
API_KEY_ENV = "POLY_ALPHA_AI_API_KEY"
AI_MODEL_ENV = "POLY_ALPHA_AI_MODEL"
AI_BASE_URL_ENV = "POLY_ALPHA_AI_BASE_URL"

_SYSTEM_PROMPT = (
    "You estimate the probability that a binary prediction market resolves YES. "
    "Respond with a single JSON object with exactly these keys: "
    '"estimate", "low", "high", "rationale", "citations". '
    '"estimate", "low", and "high" are numbers in [0, 1] with low <= estimate <= high. '
    '"rationale" is a short string. "citations" is an array of source URLs and may be '
    "empty. Do not claim certainty or guaranteed outcomes."
)
