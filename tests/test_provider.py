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


class _FakeSession:
    """Offline session that records posts and replays queued responses or exceptions."""

    def __init__(self, responses: Sequence[_FakeResponse | Exception]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        json: dict[str, Any] | None = None,
        timeout: int | None = None,
    ) -> _FakeResponse:
        self.calls.append({"url": url, "headers": headers, "json": json, "timeout": timeout})
        item = self._responses.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _snapshot() -> MarketSnapshot:
    """A tradeable, real-provenance snapshot with a two-sided price."""
    return MarketSnapshot(
        market_id="prov-1",
        question="Will it rain tomorrow?",
        asset=AssetRef(symbol="RAIN", asset_class="prediction"),
        yes_price=0.60,
        no_price=0.40,
        liquidity=500.0,
        volume=1000.0,
        provenance=Provenance(
            source="test fixture",
            kind=DataSourceKind.REAL,
            retrieved_at=_NOW,
        ),
    )


def _content_response(content: str) -> dict[str, Any]:
    return {"choices": [{"message": {"content": content, "refusal": None}}]}


def _model_response(
    *,
    estimate: float,
    low: float,
    high: float,
    rationale: str = "Model rationale.",
    citations: Sequence[str] = (),
) -> dict[str, Any]:
    content = json.dumps(
        {
            "estimate": estimate,
            "low": low,
            "high": high,
            "rationale": rationale,
            "citations": list(citations),
        }
    )
    return _content_response(content)


def test_heuristic_provider_matches_analyst() -> None:
    snapshot = _snapshot()
    provider = HeuristicProvider()
    assert provider.is_ai is False
    assert provider.name == "offline-heuristic"
    assert provider.research_market(snapshot, now=_NOW) == research_market(snapshot, now=_NOW)


def test_ai_provider_parses_response() -> None:
    snapshot = _snapshot()
    session = _FakeSession(
        [
            _FakeResponse(
                _model_response(
                    estimate=0.70,
                    low=0.60,
                    high=0.80,
                    rationale="Rain is likely.",
                    citations=["https://example.com/forecast"],
                )
            )
        ]
    )
    provider = OpenAICompatibleProvider(_SENTINEL_KEY, session=session)
    note = provider.research_market(snapshot, now=_NOW)

    assert provider.is_ai is True
    assert note.model_yes.simulated is True
    assert note.model_yes.estimate == pytest.approx(0.70)
    assert note.model_yes.low == pytest.approx(0.60)
    assert note.model_yes.high == pytest.approx(0.80)
    assert note.model_yes.basis.startswith("ai:")
    assert note.edge.estimate == pytest.approx(0.10)

    assert len(note.claims) == 1
    sources = note.claims[0].sources
    assert all(source.kind is DataSourceKind.SIMULATED for source in sources)
    assert any(source.url == "https://example.com/forecast" for source in sources)
    assert any("AI" in caveat for caveat in note.caveats)
    assert note.claims[0].support == pytest.approx(0.80)

    assert session.calls[0]["url"] == "https://api.openai.com/v1/chat/completions"
    assert session.calls[0]["headers"] == {"Authorization": f"Bearer {_SENTINEL_KEY}"}
    assert session.calls[0]["json"]["response_format"] == {"type": "json_object"}


def test_ai_provider_falls_back_on_request_error() -> None:
    snapshot = _snapshot()
    session = _FakeSession([requests.ConnectionError("offline")])
    provider = OpenAICompatibleProvider(_SENTINEL_KEY, session=session)
    assert provider.research_market(snapshot, now=_NOW) == research_market(snapshot, now=_NOW)


def test_ai_provider_falls_back_on_bad_content() -> None:
    snapshot = _snapshot()
    expected = research_market(snapshot, now=_NOW)
    malformed = _FakeSession([_FakeResponse(_content_response("not json"))])
    out_of_range = _FakeSession(
        [_FakeResponse(_model_response(estimate=0.90, low=0.40, high=1.20))]
    )
    refused = _FakeSession(
        [_FakeResponse({"choices": [{"message": {"content": None, "refusal": "no"}}]})]
    )

    assert (
        OpenAICompatibleProvider(_SENTINEL_KEY, session=malformed).research_market(
            snapshot, now=_NOW
        )
        == expected
    )
    assert (
        OpenAICompatibleProvider(_SENTINEL_KEY, session=out_of_range).research_market(
            snapshot, now=_NOW
        )
        == expected
    )
    assert (
        OpenAICompatibleProvider(_SENTINEL_KEY, session=refused).research_market(snapshot, now=_NOW)
        == expected
    )


def test_api_key_never_appears_in_note() -> None:
    snapshot = _snapshot()
    session = _FakeSession([_FakeResponse(_model_response(estimate=0.65, low=0.55, high=0.75))])
    provider = OpenAICompatibleProvider(_SENTINEL_KEY, session=session)
    note = provider.research_market(snapshot, now=_NOW)

    rendered = " ".join([note.summary, *note.caveats, *(claim.text for claim in note.claims)])
    assert _SENTINEL_KEY not in rendered


def test_select_provider_returns_heuristic_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)
    provider = select_provider()
    assert isinstance(provider, HeuristicProvider)


def test_select_provider_returns_ai_with_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, _SENTINEL_KEY)
    monkeypatch.delenv(AI_MODEL_ENV, raising=False)
    monkeypatch.delenv(AI_BASE_URL_ENV, raising=False)
    provider = select_provider(session=_FakeSession([]))
    assert isinstance(provider, OpenAICompatibleProvider)
    assert provider.is_ai is True


def test_select_provider_honors_model_and_base_url_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(API_KEY_ENV, _SENTINEL_KEY)
    monkeypatch.setenv(AI_MODEL_ENV, "custom-model")
    monkeypatch.setenv(AI_BASE_URL_ENV, "https://example.test/v1")
    session = _FakeSession([_FakeResponse(_model_response(estimate=0.5, low=0.4, high=0.6))])
    provider = select_provider(session=session)
    provider.research_market(_snapshot(), now=_NOW)
    assert session.calls[0]["url"] == "https://example.test/v1/chat/completions"
    assert session.calls[0]["json"]["model"] == "custom-model"
