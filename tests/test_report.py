"""Tests for the pure Markdown research dossier renderer."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from poly_alpha.backtesting.comparison import ResolvedMarket, compare_strategies
from poly_alpha.contracts import (
    AssetRef,
    DataSourceKind,
    MarketSnapshot,
    PriceLevel,
    Provenance,
)
from poly_alpha.portfolio.risk import Position, analyze_portfolio
from poly_alpha.research.analyst import research_market
from poly_alpha.research.notes import ResearchNote
from poly_alpha.research.report import render_markdown, write_markdown
from poly_alpha.research.screen import Opportunity

NOW = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
ASSET = AssetRef(symbol="TEST", asset_class="prediction")
YES_BOOK = (PriceLevel(0.65, 100.0), PriceLevel(0.60, 100.0))


def make_snapshot(
    *,
    market_id: str,
    question: str,
    kind: DataSourceKind = DataSourceKind.FIXTURE,
    orderbook: tuple[PriceLevel, ...] = YES_BOOK,
) -> MarketSnapshot:
    return MarketSnapshot(
        market_id=market_id,
        question=question,
        asset=ASSET,
        yes_price=0.60,
        no_price=0.40,
        liquidity=500.0,
        volume=1000.0,
        provenance=Provenance(source="demo-fixture", kind=kind, retrieved_at=NOW),
        orderbook=orderbook,
    )


def make_notes() -> list[ResearchNote]:
    return [
        research_market(
            make_snapshot(market_id="m1", question="Will event one resolve YES?"), now=NOW
        ),
        research_market(
            make_snapshot(
                market_id="m2",
                question="Will event two resolve YES?",
                orderbook=(),
            ),
            now=NOW,
        ),
    ]


def half(snapshot: MarketSnapshot) -> float | None:
    return 0.5


def test_disclaimer_is_present_and_bold() -> None:
    output = render_markdown(make_notes(), generated_at=NOW)
    assert "**" in output
    assert "not investment advice" in output
    assert "not real observations" in output
    assert "in-sample" in output
    assert "not forecasts" in output


def test_provenance_summary_counts_fixture_notes() -> None:
    output = render_markdown(make_notes(), generated_at=NOW)
    assert "## Provenance summary" in output
    assert "- fixture: 2" in output
    assert "Real data present: no" in output


def test_provenance_summary_reports_real_data() -> None:
    note = research_market(
        make_snapshot(market_id="m3", question="Real?", kind=DataSourceKind.REAL), now=NOW
    )
    output = render_markdown([note], generated_at=NOW)
    assert "- real: 1" in output
    assert "Real data present: yes" in output


def test_every_note_question_appears() -> None:
