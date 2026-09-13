# Research Platform

An engineering overview of the read-only research surface in `poly_alpha`: it normalizes
prediction-market data, produces provenance-tagged research notes, compares strategies on
resolved markets, summarizes portfolio risk, and serves the results over a small JSON API.

## What it is

- A deterministic, offline-first analysis pipeline built on shared data contracts.
- Every value that reaches research or reporting carries a `Provenance` tag.
- Public access is read-only: the HTTP API only answers `GET` and rejects writes.
- No live order placement, no exchange keys, and no network calls in the research engine
  itself (only the live `PolymarketAdapter` reaches the network, to fetch markets).

## Module map

| Module | Responsibility |
|--------|----------------|
| `contracts.py` | Core contracts: `DataSourceKind`, `Provenance`, `AssetRef`, `PriceLevel`, `Uncertainty`, and `MarketSnapshot` (with `implied_yes` de-vig and `is_tradeable`). |
| `adapters/base.py` | `MarketAdapter` protocol (`name`, `source_kind`, `list_markets`, `get_snapshot`) and `AdapterError`. The structural contract all adapters satisfy. |
| `adapters/fixtures.py` | `FixtureMarketAdapter`: hand-authored, deterministic `DataSourceKind.FIXTURE` markets for local development and tests. |
| `adapters/polymarket.py` | `PolymarketAdapter`: maps live Polymarket Gamma payloads to `MarketSnapshot`s tagged `DataSourceKind.REAL`; skips malformed or non-two-sided markets. |
| `adapters/series.py` | `BinaryFromSeriesAdapter`: derives one synthetic up/down market per supplied price series, tagged `DataSourceKind.SYNTHETIC`. |
| `research/notes.py` | Note containers: `ResearchClaim` (direction, support, sources) and `ResearchNote` (summary, model `Uncertainty`, edge, caveats, `source_kinds`). |
| `research/analyst.py` | Deterministic offline engine. `research_market` / `research_markets` turn snapshots into notes using de-vigged price, order-book imbalance, liquidity shrinkage, and Shin debiasing. |
| `backtesting/comparison.py` | `ResolvedMarket`, `StrategyMetrics`, `compare_strategies`: replays resolved markets through supplied strategies and ranks the No-side ledger by total PnL. |
| `portfolio/risk.py` | `Position`, `RiskReport`, `analyze_portfolio`, `portfolio_value`: concentration (HHI, max position fraction) and, when a return series is supplied, historical VaR and drawdown. |
| `api/server.py` | Stdlib-only read-only JSON API: `DataProvider`, `StaticProvider`, `default_provider`, `create_server`; endpoints `/health`, `/markets`, `/research`, `/risk`, `/compare`. |
| `strategy.py` | Shared strategy primitives used by the engine (`classify_category`, `shin_debiasing`). |
| `cli.py` | Typer entry point (`scan`, `status`, `init`, `step`, `live`, `backtest`); the research modules are imported lazily by the commands. |

## End-to-end flow

```
adapter (fixtures | polymarket | series)
        |
        v
MarketSnapshot(s)  -- Provenance + orderbook + two-sided prices
        |
        v
research.analyst.research_markets(...)  --> ResearchNote (Uncertainty, claims, caveats)
        |
        +--> backtesting.comparison.compare_strategies(...) --> StrategyMetrics
        +--> portfolio.risk.analyze_portfolio(...)          --> RiskReport
        |
        v
