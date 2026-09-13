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
uv run poly-alpha research curves             # walk-forward over deterministic histories
uv run poly-alpha research costs --fee-bps 100 --slippage-bps 50   # net-edge view (--side buy|sell)
uv run poly-alpha version                                          # package version
uv run poly-alpha research calibration        # interval coverage vs demo outcomes
```

`compare`, `simulate`, and `curves` are in-sample, not annualized, and not forecasts. The
calibration metric is scored against point (0/1) outcomes and is normally zero for interior
intervals; it is not evidence of real-world calibration.

## Risk

```bash
uv run poly-alpha research risk               # HHI, exposure, historical VaR/drawdown
uv run poly-alpha research stress             # additive price-shock scenarios
```

## Reports and audit

```bash
uv run poly-alpha research report --output dossier.md   # Markdown dossier
uv run poly-alpha research journal --path runs.jsonl    # append a provenance summary
uv run poly-alpha research history --path runs.jsonl    # list recorded runs
```

## API and dashboard

```bash
uv run poly-alpha research serve --port 8000
# GET /              -> read-only HTML dashboard
# GET /health /markets /research /risk /compare /overview /validation
# GET /curves /calibration /stress
```

The server is GET-only, binds loopback by default, and returns 404/405 for unknown paths and
methods. `/curves`, `/calibration`, and `/stress` are computed from the packaged fixture/demo
data, not the injected provider.

## Interpreting output

- `provenance.kind` is `REAL` only for Polymarket Gamma data fetched via `--real`.
- `FIXTURE` is deterministic hand-authored data; `SYNTHETIC` is derived from supplied series;
  `SIMULATED` is model output.
- Never present fixture/simulated/synthetic output as observed market data, and never present
  in-sample metrics as forecasts. See `docs/DATA_PROVENANCE.md`.

## Testing

The project uses pytest (`uv run pytest tests/`). On the authoring workstation test suites were
not executed; behavior was verified with bounded import/smoke checks. Run the suite in a normal
development environment before merging.

Open work and deliberate gaps are listed in `docs/ROADMAP.md`.
