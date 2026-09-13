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
