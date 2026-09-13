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

The research commands run offline by default. `--real` flags reach the read-only Polymarket
Gamma and Kalshi Trade APIs and tag results `DataSourceKind.REAL`; `--limit N` caps each
source's request/page size (Polymarket caps events, Kalshi caps markets).

## Market data

```bash
uv run poly-alpha research markets            # 10 labeled FIXTURE markets
uv run poly-alpha research markets --all      # + crypto/equity SYNTHETIC series (13 total)
uv run poly-alpha research markets --real     # REAL Polymarket + Kalshi markets (network)
uv run poly-alpha research markets --real --limit 50   # cap each live source
uv run poly-alpha research validate           # contract invariant check over all markets
```

## Research

```bash
uv run poly-alpha research research --json    # provenance-tagged notes + uncertainty
uv run poly-alpha research research --real    # research over real markets (network)
uv run poly-alpha research research --ai      # optional AI provider (needs POLY_ALPHA_AI_API_KEY)
uv run poly-alpha research screen             # rank by the conservative edge lower bound
uv run poly-alpha research screen --require-real
uv run poly-alpha research overview           # cross-market ranking by absolute edge
uv run poly-alpha research size               # conservative fractional-Kelly sizing
uv run poly-alpha research strategy           # the four named heuristic strategies
```

Every note carries `model_yes: Uncertainty`, cited sources, and caveats. Model estimates are
always marked simulated even when the market data is real. The default engine is a deterministic
offline **heuristic**, not an AI model. `--ai` selects an optional OpenAI-compatible provider
when `POLY_ALPHA_AI_API_KEY` is set (`POLY_ALPHA_AI_MODEL`/`POLY_ALPHA_AI_BASE_URL` override the
model and endpoint); on a missing key or any error it falls back to the heuristic. AI estimates
are marked simulated, model-supplied citations are labeled unverified, and the key is only sent
as an Authorization header — never logged or written to a note.

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
uv run poly-alpha research experiment --path runs.jsonl # record a reproducible run (fingerprint)
uv run poly-alpha research experiments --path runs.jsonl # list recorded experiments
uv run poly-alpha research experiments --path runs.jsonl --verify  # re-run and check each
```

An experiment record stores a deterministic sha256 `run_id` over the exact market inputs and
parameters plus the resulting counts/allocations/stake/cash. `reproduce(experiment)` re-runs the
pipeline and compares the fingerprint and outputs, so fixture, parameter, or code drift is
detected; `research experiments --verify` does this for every recorded run. The journal remains
the lightweight aggregate audit trail.

## API and dashboard

```bash
uv run poly-alpha research serve --port 8000
# GET /              -> read-only HTML dashboard
# GET /health /markets /research /risk /compare /overview /validation
# GET /curves /calibration /stress /allocate /run /experiments
```

The server is GET-only, binds loopback by default, and returns 404/405 for unknown paths and
methods. `/curves`, `/calibration`, `/stress`, `/allocate`, `/run`, and `/experiments` are
computed from the packaged fixture/demo data or local records, not the injected provider.

## Interpreting output

- `provenance.kind` is `REAL` only for Polymarket Gamma or Kalshi data fetched via `--real`.
- `FIXTURE` is deterministic hand-authored data; `SYNTHETIC` is derived from supplied series;
  `SIMULATED` is model output.
- Never present fixture/simulated/synthetic output as observed market data, and never present
  in-sample metrics as forecasts. See `docs/DATA_PROVENANCE.md`.

## Testing

The project uses pytest (`uv run pytest tests/`), with `ruff check`, `ruff format --check`, and
`mypy src/poly_alpha/` as the other CI gates. Pass 2 ran all four gates on the designated Linux
runner against the project `.venv`, and all passed; run them in a normal development environment
before merging.

Open work and deliberate gaps are listed in `docs/ROADMAP.md`.
