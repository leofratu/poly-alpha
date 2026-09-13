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


class ResearchProvider(Protocol):
    """A source of provenance-tagged research notes for one market snapshot."""

    name: str
    is_ai: bool

    def research_market(
        self, snapshot: MarketSnapshot, *, now: datetime | None = None
    ) -> ResearchNote: ...


class HeuristicProvider:
    """Default provider: delegates to the deterministic offline analyst heuristic."""

    name = "offline-heuristic"
    is_ai = False

    def research_market(
        self, snapshot: MarketSnapshot, *, now: datetime | None = None
    ) -> ResearchNote:
        """Build a deterministic offline note; no network and no AI model is involved."""
        return _heuristic_research_market(snapshot, now=now)


class OpenAICompatibleProvider:
    """Optional AI provider speaking the OpenAI Chat Completions JSON-object shape."""

    name = "openai-compatible"
    is_ai = True

    def __init__(
        self,
        api_key: str,
        *,
        model: str = DEFAULT_AI_MODEL,
        base_url: str = DEFAULT_AI_BASE_URL,
        timeout: int = DEFAULT_TIMEOUT,
        session: Any = None,
        fallback: ResearchProvider | None = None,
    ) -> None:
        self._api_key = api_key
        self._model = model
        self._base_url = base_url
        self._timeout = timeout
        self._session = session if session is not None else requests.Session()
        self._fallback = fallback if fallback is not None else HeuristicProvider()

    def research_market(
        self, snapshot: MarketSnapshot, *, now: datetime | None = None
    ) -> ResearchNote:
        """Ask the model for an estimate, falling back to the heuristic on any error."""
        try:
            payload = self._request(snapshot)
            return self._note_from(snapshot, payload, now)
        except (requests.RequestException, ValueError, KeyError, TypeError, IndexError):
            return self._fallback.research_market(snapshot, now=now)

    def _request(self, snapshot: MarketSnapshot) -> dict[str, Any]:
        """POST one JSON-object chat completion and return the decoded response body."""
        implied = snapshot.implied_yes()
        implied_text = f"{implied:.4f}" if implied is not None else "n/a"
        user_content = (
            f"Market ID: {snapshot.market_id}\n"
            f"Question: {snapshot.question}\n"
            f"Implied YES probability: {implied_text}\n"
            f"YES price: {snapshot.yes_price}\n"
            f"NO price: {snapshot.no_price}\n"
            f"Liquidity: {snapshot.liquidity}\n"
            f"Volume: {snapshot.volume}"
        )
        body: dict[str, Any] = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
        resp = self._session.post(
            f"{self._base_url.rstrip('/')}/chat/completions",
            headers={"Authorization": f"Bearer {self._api_key}"},
            json=body,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()  # type: ignore[no-any-return]
