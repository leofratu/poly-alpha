# Roadmap and Open Work

This lists what is deliberately not done. Everything below is a research/simulation direction;
none of it is validated performance.

## Near term

- **Rotate the leaked `.env` credentials.** `master` tracked a `.env` with Polymarket keys;
  this branch stops tracking it, but the values remain in git history. Rotate and rewrite
  history, then remove the working-tree copy. (Owner action; out of scope for the code passes.)
- **Publish the pass-2 PR stack.** The branch stack and draft PR bodies are ready; publication
  awaits a valid `gh` token.

Completed in the second improvement pass (2026-09-14): all four CI gates were run and recorded
on the designated Linux runner (`pytest`, `ruff check`, `ruff format --check`, `mypy`);
the type gate was widened from `strategy.py` to `src/poly_alpha/`; Kalshi was added as a second
real venue; reproducible experiment records were added alongside the journal; and
`validation.py` now filters ingestion in `aggregate_markets` so invalid snapshots are rejected
at the source.

## Adapters and data

- **Third real venue.** Polymarket and Kalshi are implemented; Manifold (or another venue)
  would broaden coverage further. It needs an injectable client plus fixture-mapped tests so
  nothing hits the network in CI.
- **Richer run storage.** Experiments are persisted as fingerprinted JSONL and the journal
  remains the aggregate audit trail; a SQLite-backed history for richer queries is still open.
  Keep provenance labels on every stored row.

## Research and evaluation

- **Calibrate against real outcomes.** `calibration.py` currently scores interval coverage over
  labeled demo resolutions only. A real-outcome run (with provenance) would make the metric
  meaningful rather than illustrative.
- **More uncertainty-aware strategies** and a portfolio-level backtest that feeds `allocate`
  into `simulate_portfolio`/`walk_forward` over real histories.
- **Slippage/fee realism**: `costs.py` exposes `walk_book` plus
  `CostModel.depth_effective_price`/`depth_net_edge`, and `research costs --size N` reports a
  depth-aware edge over the fixture order books. Feeding these into the strategy simulations
  is still open. A full L2 fill model reusing `execution/paper_engine.py` remains open.

## Interface

- **Browser UI over the JSON API**: the current dashboard is a single read-only HTML page;
  a richer client could add filtering, comparison charts, and run history.
- **CLI ergonomics**: `--source` unification (today `--all`/`--real`), and JSON output for the
  legacy `scan`/`status` commands.

## Explicitly out of scope

- Live order execution, fund movement, or public deployment.
- Any performance, Sharpe, or return claim: none is validated anywhere in this repository.
