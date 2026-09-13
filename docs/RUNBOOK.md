# Runbook

How to run the poly-alpha research platform. All commands are research/simulation/paper-trading
only: no live orders, no fund transfers, and no public deployment. Anything not marked REAL is
fixture, simulated, or synthetic data.

## Setup

```bash
uv sync --extra dev          # creates .venv and installs deps
uv run poly-alpha --help     # base CLI
uv run poly-alpha research --help
```

The research commands run offline by default. `--real` flags reach the Polymarket Gamma API and
tag results `DataSourceKind.REAL`.

## Market data

```bash
uv run poly-alpha research markets            # 10 labeled FIXTURE markets
uv run poly-alpha research markets --all      # + crypto/equity SYNTHETIC series (13 total)
uv run poly-alpha research markets --real     # REAL Polymarket markets (network)
uv run poly-alpha research validate           # contract invariant check over all markets
```

## Research

```bash
uv run poly-alpha research research --json    # provenance-tagged notes + uncertainty
uv run poly-alpha research research --real    # research over real markets (network)
uv run poly-alpha research screen             # rank by the conservative edge lower bound
uv run poly-alpha research screen --require-real
uv run poly-alpha research overview           # cross-market ranking by absolute edge
uv run poly-alpha research size               # conservative fractional-Kelly sizing
uv run poly-alpha research strategy           # the four named heuristic strategies
```

Every note carries `model_yes: Uncertainty`, cited sources, and caveats. Model estimates are
always marked simulated even when the market data is real.

## Comparison and simulation

```bash
uv run poly-alpha research compare            # in-sample strategy comparison (demo data)
uv run poly-alpha research simulate           # paper equity curve over demo resolutions
