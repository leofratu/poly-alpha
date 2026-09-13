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
    notes = make_notes()
    output = render_markdown(notes, generated_at=NOW)
    for note in notes:
        assert note.question in output
        assert note.market_id in output


def test_uncertainty_interval_and_edge_numbers_appear() -> None:
    notes = make_notes()
    output = render_markdown(notes, generated_at=NOW)
    for note in notes:
        assert f"{note.model_yes.estimate:.1%}" in output
        assert f"{note.model_yes.low:.1%}" in output
        assert f"{note.model_yes.high:.1%}" in output
        assert f"{note.edge.estimate:+.1%}" in output


def test_claims_show_direction_support_and_sources() -> None:
    note = make_notes()[0]
    output = render_markdown([note], generated_at=NOW)
    for claim in note.claims:
        assert claim.text in output
        assert claim.direction in output
        assert f"support: {claim.support:.0%}" in output
    assert "demo-fixture (fixture)" in output


def test_caveats_are_rendered() -> None:
    note = make_notes()[0]
    output = render_markdown([note], generated_at=NOW)
    for caveat in note.caveats:
        assert caveat in output


def test_optional_sections_render_without_crashing() -> None:
    positions = [
        Position("m1", "sports", 150.0, 0.55, Provenance("demo", DataSourceKind.FIXTURE)),
        Position("m2", "politics", 50.0, 0.35, Provenance("demo", DataSourceKind.FIXTURE)),
    ]
    risk = analyze_portfolio(positions, [-0.10, 0.05, 0.02, -0.03, 0.04])
    markets = [
        ResolvedMarket(make_snapshot(market_id="r1", question="Resolved one?"), resolved_yes=False),
        ResolvedMarket(make_snapshot(market_id="r2", question="Resolved two?"), resolved_yes=True),
    ]
    metrics = compare_strategies(markets, {"half": half})
    notes = make_notes()
    opportunities = [
        Opportunity(
            note=notes[0],
            edge_low=0.10,
            edge_high=0.20,
            score=1.5,
            requires_real_data=False,
        )
    ]
    output = render_markdown(
        notes,
        opportunities=opportunities,
        metrics=metrics,
        risk=risk,
        generated_at=NOW,
    )
    assert "## Screened opportunities" in output
    assert "real=no" in output
    assert "## Strategy comparison" in output
    assert metrics[0].caveat in output
    assert "## Portfolio risk" in output
    assert "Historical VaR 95:" in output
    assert "Max position fraction:" in output


def test_optional_sections_omitted_when_not_supplied() -> None:
    output = render_markdown(make_notes(), generated_at=NOW)
    assert "## Screened opportunities" not in output
    assert "## Strategy comparison" not in output
    assert "## Portfolio risk" not in output


def test_output_is_deterministic_for_fixed_time() -> None:
    notes = make_notes()
    first = render_markdown(notes, generated_at=NOW)
    second = render_markdown(notes, generated_at=NOW)
    assert first == second
    assert first.endswith("\n")


def test_missing_generated_at_emits_no_timestamp() -> None:
    output = render_markdown(make_notes())
    assert "Generated at:" not in output


def test_write_markdown_writes_utf8(tmp_path: Path) -> None:
    target = tmp_path / "dossier.md"
    write_markdown(target, "# Dossier — ünïcode\n")
    assert target.read_text(encoding="utf-8") == "# Dossier — ünïcode\n"
