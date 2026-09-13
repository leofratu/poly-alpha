# System Architecture

## Module Dependency Graph

```
cli.py
  └── execution/
        ├── paper_engine.py  ──→  strategy.py
        │                    ──→  data/polymarket.py (via shared API logic)
        └── live_executor.py ──→  strategy.py
                             ──→  data/polymarket.py

strategy.py (zero external deps — pure logic)

data/
  ├── polymarket.py  (requests → Gamma API)
  └── tradfi.py      (yfinance → Yahoo/Options)

backtesting/
  ├── monte_carlo.py (numpy + requests)
  └── empirical.py   (numpy only — no network)
```

## Research platform layer

The offline research platform is described in detail in `docs/RESEARCH_PLATFORM.md`,
`docs/DATA_PROVENANCE.md`, and `docs/RUNBOOK.md`. Its modules:

```
contracts.py, validation.py
adapters/    fixtures (FIXTURE), polymarket (REAL), series (SYNTHETIC), registry, history
research/    notes, analyst, screen, overview, report, calibration, journal, pipeline
portfolio/   risk, sizing, allocate, stress
backtesting/ comparison, strategies, simulation, walkforward, costs, demo_data
api/server.py (read-only JSON + dashboard), cli_platform.py (research commands)
```

Flow: adapter → `MarketSnapshot` (with `Provenance`) → research note (with `Uncertainty`) →
conservative screen → budgeted allocation → portfolio risk / calibration → Markdown dossier or
API. Nothing places orders: `--real` only reads Polymarket market data.

## Data Flow

1. `PolymarketClient` fetches raw event JSON from Gamma API
2. `strategy.candidate_from_market()` filters + scores each market
3. `paper_engine.scan_markets()` diversifies via Jaccard clustering
4. `paper_engine.deploy_trades()` walks L2 and records to SQLite
5. `paper_engine.settle_trades()` checks resolution + updates PnL

## Persistence

- **SQLite** at `~/.poly_alpha/paper_wallet.sqlite`
  - `wallet` table: single row, free capital
  - `positions` table: all trades (open + closed)

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `POLY_ALPHA_PRESET` | Strategy preset | `strict` |
| `POLY_ALPHA_DB` | SQLite path | `~/.poly_alpha/paper_wallet.sqlite` |
| `GEMINI_API_KEY` | Gemini AI risk filter (optional) | empty |
| `POLY_*` live-execution keys | Local `.env` only; **untracked** and unused by the research platform | empty |
