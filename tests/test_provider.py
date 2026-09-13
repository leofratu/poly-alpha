"""Tests for the optional research providers (fully offline, no network or AI calls)."""

from __future__ import annotations

import json
from collections.abc import Sequence
from datetime import UTC, datetime
from typing import Any

import pytest
import requests

from poly_alpha.contracts import AssetRef, DataSourceKind, MarketSnapshot, Provenance
from poly_alpha.research.analyst import research_market
from poly_alpha.research.provider import (
    AI_BASE_URL_ENV,
    AI_MODEL_ENV,
    API_KEY_ENV,
    HeuristicProvider,
    OpenAICompatibleProvider,
    select_provider,
)

_NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
_SENTINEL_KEY = "sk-test-SENTINEL-key-do-not-leak-0000"


class _FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(self, payload: dict[str, Any]) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict[str, Any]:
        return self._payload
