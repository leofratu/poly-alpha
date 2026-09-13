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
| `adapters/registry.py` | `default_adapters`, `aggregate_markets`, `markets_by_kind`: composes fixtures + crypto/equity series into one labeled snapshot stream, skipping failed adapters. |
| `adapters/history.py` | `MarketHistory`, `fixture_histories`: deterministic multi-step snapshot histories (FIXTURE) spanning time for walk-forward tests. |
| `research/notes.py` | Note containers: `ResearchClaim` (direction, support, sources) and `ResearchNote` (summary, model `Uncertainty`, edge, caveats, `source_kinds`). |
| `research/analyst.py` | Deterministic offline engine. `research_market` / `research_markets` turn snapshots into notes using de-vigged price, order-book imbalance, liquidity shrinkage, and Shin debiasing. |
| `research/screen.py` | `Opportunity`, `rank_opportunities`, `summarize`: ranks notes by the **lower bound** of the model edge, optionally requiring `REAL` provenance. |
| `research/overview.py` | `MarketOverview`, `build_overview`, `dimensions`, `overview_rows`: cross-market ranking by absolute edge across asset classes and data kinds. |
| `research/calibration.py` | `CalibrationReport`, `interval_coverage`, `calibration_by_kind`, `demo_calibration`: measures uncertainty-interval coverage against supplied outcomes (labeled; not real-world evidence). |
| `research/pipeline.py` | `ResearchBundle`, `run_pipeline`: composes registry -> research -> screen -> allocate -> risk + calibration into one deterministic bundle. |
| `validation.py` | `validate_snapshot`, `is_valid`, `validate_uncertainty`: dependency-free contract invariant checks (no exceptions on bad data). |
| `research/report.py` | `render_markdown` / `write_markdown`: composes notes, opportunities, allocations, comparison metrics, risk, and uncertainty coverage into one provenance-labeled Markdown dossier. |
| `research/journal.py` | `JournalEntry`, `build_entry`, `append_entry`, `read_entries`: append-only JSONL audit trail of research runs (counts by kind, mean edge, simulated flag). |
| `portfolio/sizing.py` | `SizingDecision`, `kelly_fraction`: conservative fractional-Kelly sizing that uses the uncertainty lower bound and a hard cap. |
| `portfolio/allocate.py` | `Allocation`, `AllocationPlan`, `allocate`: turns ranked opportunities into a budgeted portfolio under position and deploy caps. |
| `portfolio/stress.py` | `StressScenario`, `StressResult`, `run_scenarios`: additive price-shock scenarios over a labeled portfolio; deterministic and caveated by the CLI. |
| `backtesting/comparison.py` | `ResolvedMarket`, `StrategyMetrics`, `compare_strategies`: replays resolved markets through supplied strategies and ranks the No-side ledger by total PnL. |
| `backtesting/strategies.py` | Named heuristic strategies (`market_implied`, `shin_debiased`, `constant_half`, `uncertainty_gated`) plus `describe`; no strategy claims validated performance. |
| `backtesting/simulation.py` | `simulate_portfolio`: uncertainty-aware paper equity curve over supplied resolved markets; in-sample, non-annualized, caveated. |
| `backtesting/walkforward.py` | `WalkForwardResult`, `walk_forward`: holds one No-side position across a deterministic snapshot history and settles at the final snapshot; caveated. |
| `backtesting/costs.py` | `CostModel`: fee/slippage-adjusted effective price and net edge for a buy or sell side. |
| `portfolio/risk.py` | `Position`, `RiskReport`, `analyze_portfolio`, `portfolio_value`: concentration (HHI, max position fraction) and, when a return series is supplied, historical VaR and drawdown. |
| `api/server.py` | Stdlib-only read-only JSON API: `DataProvider`, `StaticProvider`, `default_provider`, `create_server`; endpoints `/health`, `/markets`, `/research`, `/risk`, `/compare`, `/overview`, `/validation`, `/curves`, `/calibration`, `/stress`, `/allocate`, `/run`, plus a read-only HTML dashboard at `/`. |
| `strategy.py` | Shared strategy primitives used by the engine (`classify_category`, `shin_debiasing`). |
| `cli.py` | Typer entry point (`scan`, `status`, `init`, `step`, `live`, `backtest`); the research modules are imported lazily by the commands. |
| `cli_platform.py` | Typer group mounted as `poly-alpha research`: `markets`, `research`, `screen`, `report`, `size`, `strategy`, `compare`, `simulate`, `curves`, `calibration`, `costs`, `stress`, `allocate`, `run`, `overview`, `validate`, `journal`, `history`, `risk`, `serve`. |

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
        +--> research.screen.rank_opportunities(...)        --> Opportunity
        +--> portfolio.sizing.kelly_fraction(...)           --> SizingDecision
        +--> backtesting.comparison.compare_strategies(...) --> StrategyMetrics
        +--> portfolio.risk.analyze_portfolio(...)          --> RiskReport
        |
        v
research.report.render_markdown(...) --> Markdown dossier
api.server (read-only JSON)  /  cli_platform commands
```

1. An adapter produces `MarketSnapshot`s, each carrying a `Provenance`.
2. `research_markets` derives a `ResearchNote` per snapshot, with a simulated heuristic
   estimate, an explicit interval, and cited sources.
3. `compare_strategies` scores strategies over already-resolved markets;
   `analyze_portfolio` summarizes concentration and supplied historical returns.
4. `api.server` (or `cli.py`) presents the snapshots, notes, metrics, and risk report.

## Extension points

Adding an adapter:

1. Implement the `MarketAdapter` protocol: expose `name`, `source_kind`, `list_markets()`,
   and `get_snapshot(market_id)`.
2. Build `MarketSnapshot`s with the correct `DataSourceKind` and a `Provenance` naming the
   source, retrieval time, and any URL/note.
3. Raise `AdapterError` when a snapshot cannot be produced; skip malformed payloads rather
   than fabricating values.
4. Wire the adapter into `api.server.default_provider` (or a custom `DataProvider`) so the
   research, comparison, and risk paths pick it up.

Other extension points: add a new `strategy` callable for `compare_strategies`, or a new
`DataProvider` to serve a different composition of the same contracts.

## Reproducible experiments

`research/experiments.py` stores one JSON Line per pipeline run with a deterministic
`run_id`: a sha256 fingerprint of the exact market inputs (id, question, prices,
provenance kind, liquidity, order book) and parameters, plus the resulting counts,
allocations, stake, and cash. Because the fixtures are deterministic, re-running the same parameters yields the
same `run_id`, so `reproduce(experiment)` detects any drift in inputs or parameters.
`poly-alpha research experiment` records a run and `research experiments` lists them.
Journal entries remain the lightweight aggregate audit trail; experiment records are
the reproducible artifacts.

## Optional AI research provider

The default engine stays the offline heuristic. `research/provider.py` adds an optional,
clearly separated AI path behind the same `ResearchNote` contract:

- `HeuristicProvider` wraps the deterministic engine; `is_ai` is `False`.
- `OpenAICompatibleProvider` calls an OpenAI-compatible `POST /chat/completions` endpoint
  with `response_format={"type": "json_object"}` and requires `POLY_ALPHA_AI_API_KEY`;
  `POLY_ALPHA_AI_MODEL` and `POLY_ALPHA_AI_BASE_URL` override the model and endpoint.
- On a missing key, a request error, or a malformed/out-of-range response it falls back to
  the heuristic, so `poly-alpha research --ai` still works fully offline.
- AI estimates are model output, not observations: `Uncertainty.simulated` is `True`, the
  basis is `ai:<model>`, and model-supplied citations are tagged `SIMULATED` and labeled
  unverified. The API key is only sent as an Authorization header and never written to a
  note, caveat, or log.

## Limitations and honesty

- The research engine is a **deterministic offline heuristic, not a trained model**. It is
  a pure function of the snapshot (de-vigged price, order-book depth/imbalance, liquidity),
  with no learning and no external inputs. The optional AI provider above is the only path
  that makes model or network calls, and it is off unless explicitly enabled.
- Fixture, synthetic, and simulated data are **labeled** via `DataSourceKind` and
  `Provenance`, and **are not real market data**. Fixture markets are hand-authored;
  series markets are generated; the model's own intervals are marked `simulated`.
- Backtest metrics are **in-sample, not annualized, and not forecasts**. They score a fixed
  set of supplied resolved markets and describe the past, not future performance.
- Nothing here executes live trades. Research notes, comparison metrics, and risk reports
  are analysis artifacts only, and the API is read-only.
- This is not investment advice, and no claim of profitability, expected return, or win
  rate is made anywhere in the platform.
