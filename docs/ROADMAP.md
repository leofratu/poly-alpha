# Roadmap and Open Work

This lists what is deliberately not done. Everything below is a research/simulation direction;
none of it is validated performance.

## Near term

- **Run CI and record a receipt.** `pytest`, `ruff check`, `ruff format --check`, and `mypy`
  were not executed on the authoring host (host rule). Run them in a normal environment before
  merging and paste the output into the PR.
- **Rotate the leaked `.env` credentials.** `master` tracked a `.env` with Polymarket keys;
  this branch stops tracking it, but the values remain in git history. Rotate and rewrite
  history, then remove the working-tree copy.
- **Widen the type gate.** CI type-checks only `strategy.py`. Point `mypy` at `src/poly_alpha`
  once the new modules are clean under `--strict`.

## Adapters and data

- **Second real venue.** Only Polymarket is implemented (`PolymarketAdapter`). A Kalshi or
  Manifold adapter would broaden coverage; both need an injectable client plus fixture-mapped
  tests so nothing hits the network in CI.
- **Persist research runs.** The journal is JSONL; a SQLite-backed history would support richer
  queries. Keep provenance labels on every stored row.
- **Wire `validation.py` into ingestion** so adapters reject malformed snapshots at the source.

## Research and evaluation

- **Calibrate against real outcomes.** `calibration.py` currently scores interval coverage over
  labeled demo resolutions only. A real-outcome run (with provenance) would make the metric
  meaningful rather than illustrative.
- **More uncertainty-aware strategies** and a portfolio-level backtest that feeds `allocate`
  into `simulate_portfolio`/`walk_forward` over real histories.
- **Slippage/fee realism**: `costs.py` is a simple basis-point model; a depth-aware fill model
  (reusing L2 walking from `execution/paper_engine.py`) would be more realistic.

## Interface

- **Browser UI over the JSON API**: the current dashboard is a single read-only HTML page;
  a richer client could add filtering, comparison charts, and run history.
- **CLI ergonomics**: `--source` unification (today `--all`/`--real`), and JSON output for the
  legacy `scan`/`status` commands.

## Explicitly out of scope

- Live order execution, fund movement, or public deployment.
- Any performance, Sharpe, or return claim: none is validated anywhere in this repository.
