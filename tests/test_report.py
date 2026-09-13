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


