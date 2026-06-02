# Poly-Alpha Clean Strategy Context

## What The Repo Learned

The repository started from an early-lifecycle paper thesis: retail overpays for longshot `Yes`, so `No` can be cheap. Real paper-trading and trade export analysis changed that view.

The live engine's strongest observed edge was **not** early lifecycle. It showed up in the **final quarter of short-dated markets**, especially in sports derivatives. The clean strategy in this repo now treats the original paper as inspiration for the bias model, but it follows the observed live edge instead of pretending the paper was perfectly portable.

## Clean Strategy Thesis

Buy expensive `No` shares only when all of these are true:

1. the market resolves within the next 3 days,
2. the market is already in the final 25 percent of its life,
3. the `No` price is between `0.85` and `0.95`,
4. recent volume is not overwhelming resting liquidity,
5. the Shin-debiased `No` probability is still above the paid `No` price by a category-specific edge threshold,
6. the market belongs to a category where emotional or recreational order flow is likely to dominate.

This is a **late-expiry No-side grinder**, not a broad all-market prediction engine.

## Markets To Trade

### Primary sleeve: sports derivatives

Allowed:
- spreads
- totals / `O/U`

Rejected:
- moneylines
- exact score
- halftime / first-half derivatives

Why:
- our live trade export showed the best realized PnL in spreads and totals,
- moneylines and exact scores produced the meaningful losses,
- derivatives are where emotional overreaction and tail-chasing appear to be strongest.

### Secondary sleeve: emotional headline markets

Allowed:
- politics / geopolitics binary headline markets
- emotionally charged entertainment / celebrity / narrative-driven binary markets

Examples:
- tariff / sanction / resignation / ceasefire headlines
- celebrity / entertainment headline binaries
- social-media-fueled narrative markets

Rejected:
- structured range contracts in these categories unless separately validated
- slow, long-dated narrative markets

Why:
- these markets often attract one-sided narrative flow,
- users chase stories, identity, and outrage more than expected value,
- politics deserves a lower edge threshold than sports because the Shin gamma is weaker there.

## Filters

### Time and lifecycle
- `max_days = 3.0`
- `min_lifecycle_pct = 0.75`
- `max_lifecycle_pct = 1.0`

Interpretation:
- only trade markets resolving in three days or less,
- only enter in the last quarter of market life.

### Price band
- `Yes` price must be `0.05` to `0.15`
- equivalently, `No` price must be `0.85` to `0.95`

Interpretation:
- we want heavily favored `No`, but not so expensive that tail loss destroys the profile.

### Toxic flow defense
- reject when `volume24hr / liquidity > 15`

Interpretation:
- if a market is trading far more notional than the displayed resting book, assume informed flow or stale depth and stay out.

### Minimum edge
Category-specific Shin edge thresholds:
- sports: `>= 0.03`
- politics: `>= 0.005`
- emotional other: `>= 0.025`

Interpretation:
- sports needs a larger edge because it is the main production sleeve and we want cleaner entries,
- politics gets a lower threshold because the Shin transform is milder there,
- emotional non-politics markets stay stricter because they are more weakly validated.

## Probability Model

We still use the category-aware Shin-style debiaser:

- politics: `gamma = 1.05`
- crypto: `gamma = 1.30`
- weather: `gamma = 1.15`
- esports: `gamma = 1.18`
- sports: `gamma = 1.20`
- other: `gamma = 1.18`

Formula:

`shin_no = (no_price^gamma) / (no_price^gamma + (1 - no_price)^gamma)`

Interpretation:
- this is a bias-correction heuristic, not a guarantee of true probability,
- it is strongest when combined with strict market-type filtering.

## Execution Rules

- scan active Gamma events continuously,
- build candidates only from the clean profile,
- rank by category priority and confidence,
- deduplicate similar questions,
- cap category counts,
- size each position at `2.5%` of current paper equity,
- stop book sweeping once the average paid price would cross the model edge,
- keep portfolio deployment capped so the account retains cash.

## Risk Rules

Hard rules:
- one underlying event cluster should not dominate exposure,
- avoid multiple positions on the same match or the same political headline unless explicitly modeled,
- keep a cash reserve,
- reject stale or toxic books,
- do not treat open exposure as profit.

Known hidden risk:
- expensive `No` trades win often but lose `100%` when wrong,
- correlated clusters can erase many small wins.

## What The Data Said

From the live paper-trading analysis shared in this repo:

- most closed trades were in the `0.85` to `0.95` `No` band,
- almost all entries happened in the final 25 percent of market life,
- spreads were the dominant profit source,
- totals also worked,
- moneylines and exact scores lost money,
- a normalized `$1000` replay of the closed-trade sample was positive, but the sample was short.

So the clean profile is intentionally narrower than the original thesis.

## What This Strategy Is Not

It is not:
- an early-lifecycle-only paper clone,
- a guaranteed `70% per month` machine,
- a broad all-category Polymarket alpha model,
- proof that every high-priced `No` is good.

It is a focused hypothesis:
- **late-expiry sports spreads/totals plus emotional binary headlines** can still contain favorite-longshot bias after filtering for price, liquidity, and toxicity.

## Current Repo Implementation

The clean strategy profile is codified in:
- `strategy_core.py`
- `paper_engine.py`

The main shared rules now enforce:
- short expiry,
- late lifecycle entry,
- sports-only derivative selection for the sports sleeve,
- politics and emotional-binary inclusion for the emotional sleeve,
- category-specific edge thresholds.

## What Still Needs Validation

Before trusting real money, validate these out of sample:
- longer non-overlapping windows,
- live fill realism versus displayed depth,
- correlation-capped bankroll paths,
- politics and emotional-market sleeve performance separately from sports,
- sensitivity to tighter price bands such as `0.88` to `0.94`.

## Practical Default

If you want the cleanest current production profile, use:
- sports spreads and totals,
- politics headline binaries,
- emotional entertainment / celebrity binaries,
- `No` between `0.85` and `0.95`,
- expiry under `3d`,
- final `25%` of market life,
- strict toxic-flow rejection,
- strict exposure caps.
