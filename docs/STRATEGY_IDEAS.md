# Strategy Ideas in Code

A catalog of the strategy ideas that exist in this repository, where each one lives, what it
consumes, how the harness scores it, and where it is weak. Everything here is research,
simulation, and paper-trading only. No idea in this catalog has a validated result. Any metric
the harness prints is in-sample over the supplied resolved markets, is not a forecast, and is
not a claim of profitability, expected return, win rate, Sharpe, or APY. Demo, fixture, and
synthetic data are labeled as such (see `docs/DATA_PROVENANCE.md`) and are not real observations.
Only the Shin (1992) reference is used here, as cited in code (`strategy.py`).

## market_implied

- **Thesis:** The de-vigged market mid is the best available fair-value estimate, so trade only
  when it differs from the quoted price.
- **Implemented by:** `market_implied` in `src/poly_alpha/backtesting/strategies.py`.
- **Data needed:** A two-sided `MarketSnapshot` (`yes_price`, `no_price`); uses
  `MarketSnapshot.implied_yes()` in `contracts.py`, which returns `yes_price / (yes_price + no_price)`.
- **Evaluated by:** `compare_strategies` and `simulate_portfolio`, which treat the returned value
  as a fair YES probability and buy the No side when the quoted No price is far enough below the
  fair No value.
- **Weaknesses:** It is the market, so it cannot by itself exploit mispricing; it carries the
  market's vig and any bias in the listed prices, and skips markets without two-sided quotes.

## shin_debiased

- **Thesis:** Quoted prices embed a favourite–longshot bias, so applying a Shin (1992) power-law
  transform moves the de-vigged price toward a fair probability.
- **Implemented by:** `shin_debiased` in `strategies.py`, delegating to `shin_debiasing` and
  `classify_category` in `src/poly_alpha/strategy.py`.
- **Data needed:** A two-sided snapshot plus its question text (for category classification);
  gamma is a fixed per-category constant table (`SHIN_GAMMA`).
- **Evaluated by:** The same No-side ledger as above through `compare_strategies` /
  `simulate_portfolio`.
- **Weaknesses:** The gammas and the category keyword classifier are fixed heuristics, not
  fitted parameters; classification is brittle; and the transform is an assumption about price
  formation that the repository has not validated.

## constant_half

- **Thesis:** A neutral 0.5 prior is a baseline control against which the price-based ideas are
  read.
- **Implemented by:** `constant_half` in `strategies.py`, which returns 0.5 for every snapshot.
- **Data needed:** None beyond the snapshot passed in.
- **Evaluated by:** `compare_strategies` / `simulate_portfolio`; it exists to anchor the
  comparison, not to trade.
- **Weaknesses:** It ignores all market information, so any apparent edge is for reference only
  and must not be read as signal.

## uncertainty_gated

- **Thesis:** Only act when the research model sits below the market across its whole interval,
  i.e. when the optimistic end of the edge is still negative.
- **Implemented by:** `uncertainty_gated` in `strategies.py`, calling `research_market` in
  `src/poly_alpha/research/analyst.py` and returning `note.model_yes.estimate` when
  `note.edge.high < 0.0`, otherwise `None`.
- **Data needed:** The full snapshot: prices, liquidity, and order book; the analyst derives the
  interval from de-vigged price, order-book depth/imbalance, and liquidity shrinkage.
- **Evaluated by:** `compare_strategies` / `simulate_portfolio`; a `None` return means the
  market is skipped, so trade count itself is part of the readout.
- **Weaknesses:** The interval and shrinkage are simulated heuristics marked
  `simulated=True`, not calibrated probabilities; the gate can skip most or all markets; and a
  narrow interval on thin data can still be overconfident.

## Conservative edge screener

- **Thesis:** Rank opportunities by the pessimistic lower bound of the model edge so a market is
  surfaced only if even the bad end clears the bar.
- **Implemented by:** `Opportunity`, `rank_opportunities`, `screen_markets`, and `summarize` in
  `src/poly_alpha/research/screen.py`.
- **Data needed:** `ResearchNote` objects from `research_markets`, each with an edge
  `Uncertainty`; optional `require_real` filters to `DataSourceKind.REAL` provenance only.
- **Evaluated by:** Score is `note.edge.low`; results sort by score descending with `market_id`
  as tiebreak, and `summarize` reports counts and mean/max lower-bound edge.
- **Weaknesses:** It is a selection filter, not a PnL test; the lower bound is only as good as the
  analyst's interval; and `require_real` filters provenance, not quality.

## Capped-Kelly sizing rule

- **Thesis:** Size positions from the conservative probability bound, then hard-cap the fraction
  so no single market can dominate the book.
- **Implemented by:** `SizingDecision`, `kelly_fraction`, and `portfolio_fractions` in
  `src/poly_alpha/portfolio/sizing.py`.
- **Data needed:** An effective probability (or an `Uncertainty` whose `low` is used when
  `use_lower_bound=True`), a price in `(0, 1)`, and a cap in `(0, 1]`.
- **Evaluated by:** For a binary paying 1.0 the full Kelly is `edge / (1 - price)`; the returned
  fraction is `min(full, cap)`, with zero when the price is invalid or the conservative edge is
  non-positive. `total_fraction` sums fractions but applies no normalization.
- **Weaknesses:** Full Kelly assumes the probability is correct, which it is not (the input is a
  heuristic bound); `portfolio_fractions` does not scale positions to a budget, so callers must
  impose portfolio limits; and a cap is a risk control, not an edge claim.

## How ideas are compared

`compare_strategies` in `src/poly_alpha/backtesting/comparison.py` replays a fixed sequence of
`ResolvedMarket` objects (a `MarketSnapshot` plus its known YES/NO resolution) through each
supplied strategy. A strategy returns a fair YES probability or `None` to skip. The harness buys
the No side only when `no_price < (1 - fair_yes) - min_edge` (default `min_edge = 0.01`), stakes
`stake_fraction` of the running bankroll (default `0.02`), and settles at 1.0 per share on a No
resolution, else 0.0. It emits `StrategyMetrics` (trades, hit rate, total stake, total PnL, ROI,
max drawdown), sorts best-total-PnL first, and attaches a fixed `CAVEAT` stating the metrics are
in-sample, non-annualized, and not a forecast.

`simulate_portfolio` in `src/poly_alpha/backtesting/simulation.py` runs the same No-side idea but
sizes with `kelly_fraction` (`use_lower_bound=False`, default `cap = 0.05`) and requires a
two-sided market and `(1 - fair) - no_price > min_edge`. It returns a `SimulationResult`
(start/end bankroll, equity curve, max drawdown, trades) with its own `CAVEAT`.

Both are exercised by the `research` CLI group in `src/poly_alpha/cli_platform.py` (`compare`,
`simulate`) over `demo_resolved_markets()` from `demo_data.py`: fixture markets resolved by a
deterministic SHA-256 hash of `market_id` against `yes_price`, provenance `DataSourceKind.FIXTURE`,
labeled simulated and not real. Identical inputs yield identical output.

## Honesty notes

- These are research and paper-trading artifacts. Nothing here places orders or reads live keys.
- In-sample comparison and simulation metrics describe the supplied resolved set only and are not
  forecasts of future performance.
- Fixture, simulated, and synthetic inputs are labeled via `DataSourceKind` / `Provenance`; the
  analyst's own intervals are marked `simulated=True`. None of it is real market data.
- No strategy in this repository has a validated result. This file states none.
