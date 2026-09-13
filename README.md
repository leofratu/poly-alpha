# Poly-Alpha

**Systematic Alpha Engine for Prediction Market Microstructure Exploitation**

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](https://mypy-lang.org/)

---

## Abstract

Poly-Alpha is a quantitative trading system that extracts systematic alpha from the favorite-longshot bias on decentralized prediction markets. The engine implements a continuous-time Kelly criterion framework over a portfolio of binary options, converting retail order flow imbalances into positive expected value through probability debiasing (Shin 1992), semantic correlation clustering (Jaccard), and L2 order book microstructure execution.

Empirical calibration against Reichenbach & Walther (2025) — analyzing **124 million trades** across 77,000+ resolved markets on Polymarket — confirms the persistence of a statistically significant pricing anomaly ($d > 0.50$) in the No-side of markets priced below 15¢ Yes.

> **Correction (research-platform revision).** This line previously claimed a validated
> annualized Sharpe of 2.4–3.1. No such result exists. The historical backtest that produced
> it synthesized market resolutions and returns instead of replaying observed outcomes, so it
> cannot support any Sharpe, APY, or drawdown claim. Nothing in this document is a forecast
> or a performance result. See `docs/DATA_PROVENANCE.md` and section 5.

---

## 1. Hypothesis & Testable Predictions

### Primary Hypothesis

**H₁:** The risk-neutral measure $\mathbb{Q}$ implied by Polymarket prices systematically diverges from the physical measure $\mathbb{P}$ for markets with $P_{\text{Yes}} \in [0.05, 0.15]$, creating a persistent arbitrage in the complementary No-side:

$$\mathbb{E}_\mathbb{P}[\text{PnL}_{\text{No}}] = \underbrace{P_{\text{true}}(\text{No})}_{\text{Shin-debiased}} \cdot \frac{1}{P_{\text{market}}(\text{No})} - 1 > 0$$

### Secondary Hypotheses

**H₂:** Edge concentrates in the **terminal phase** of market lifecycle ($t/T > 0.75$) where informed traders have exited and residual order flow is noise-dominated.

**H₃:** Correlation clustering via Jaccard semantic distance prevents portfolio-level ruin from simultaneous adverse resolution of thematically-linked markets.

### Predictions Table

| # | Prediction | Metric | Acceptance Threshold | Legacy claim (unvalidated) |
|---|---|---|---|---|
| P1 | No-side win rate exceeds market-implied | $\hat{p} - p_{\text{mkt}}$ | > 0 (two-sided $t$-test, $\alpha=0.01$) | none verified |
| P2 | Edge concentrates in sports derivatives | Sectoral Sharpe contribution | Sports $S_i > 60\%$ of portfolio $S$ | none verified |
| P3 | Portfolio survives 3σ tail events | VaR₉₉ (MC, $N=300\text{K}$) | $> 0.85 \times K_0$ | synthetic only |
| P4 | Diversification eliminates absorbing barrier | $\Pr(\text{ruin}) < 0.01$ | Kelly fraction $< f^*/2$ | none verified |
| P5 | Strategy capacity before slippage erosion | Impact cost $< 2\%$ edge | Bankroll $\leq \$100\text{K}$ | none verified |

---

## 2. Mathematical Framework

### 2.1 Favorite-Longshot Bias (FLB)

The FLB is a well-documented anomaly in parimutuel and prediction markets (Griffith 1949; Thaler & Ziemba 1988). Market prices $q$ for longshot events satisfy:

$$q_{\text{longshot}} > p_{\text{true}} \implies q_{\text{favorite}} < p_{\text{true}}$$

In Polymarket's binary structure, buying "No" at price $q_{\text{No}}$ is equivalent to selling the longshot "Yes" at $q_{\text{Yes}} = 1 - q_{\text{No}}$. Expected profit per unit capital:

$$\pi = \frac{p_{\text{No}}}{q_{\text{No}}} - 1 = \frac{1 - p_{\text{Yes}}}{1 - q_{\text{Yes}}} - 1$$

### 2.2 Shin (1992) Power-Law Debiasing

We estimate $p_{\text{true}}$ from the market-implied probability using a category-specific power transform that accounts for the intensity of insider trading and retail noise:

$$\hat{P}_{\text{true}}(x) = \frac{x^{\,\gamma}}{x^{\,\gamma} + (1 - x)^{\,\gamma}}, \quad \gamma \in (1, 2]$$

This maps the risk-neutral $\mathbb{Q}$-measure to an estimator of the physical $\mathbb{P}$-measure. The parameter $\gamma$ is calibrated per asset class:

| Category | $\gamma$ | Calibration Source | $n$ (markets) |
|---|---|---|---|
| Sports | 1.20 | Cross-referenced with closing-line value | 42,000 |
| Crypto | 1.30 | Maximum retail noise, narrative-driven flow | 8,200 |
| Politics | 1.05 | Efficient — institutional polling arbitrage | 3,400 |
| Weather | 1.15 | Anchoring bias on extreme events | 1,800 |
| Esports | 1.18 | Fan loyalty overpricing | 5,600 |

> **Correction.** The $\gamma$ values are heuristic presets in `strategy.py`, not fitted
> estimates. The "Calibration Source" and $n$ columns were never produced by any artifact in
> this repository and are withdrawn; no category was calibrated on observed markets.

**Shin edge** (the signal we trade):

$$\varepsilon_{\text{Shin}} = \hat{P}_{\text{true}}(\text{No}) - q_{\text{No}}$$

We require $\varepsilon_{\text{Shin}} > \varepsilon_{\min}(\text{category})$ before deploying capital.

### 2.3 Kelly Criterion & Position Sizing

For a single binary bet with edge $\varepsilon$ and odds $b = 1/q_{\text{No}} - 1$:

$$f^* = \frac{bp - (1-p)}{b} = \frac{p - q}{1 - q}$$

where $p = \hat{P}_{\text{true}}(\text{No})$ and $q = q_{\text{No}}$.

For the full portfolio of $n$ correlated positions, the multivariate Kelly vector is:

$$\mathbf{f^*} = \Sigma^{-1} \cdot \boldsymbol{\mu}$$

In practice the platform's sizing helper (`portfolio/sizing.py`) applies a **capped**
fractional-Kelly rule and the research engine reports an uncertainty interval rather than a
single deployed fraction. Any specific $f_{\text{deployed}}$ figure would be illustrative,
not a measured result.

### 2.4 Covariance Estimation via Jaccard Distance

In the absence of historical return series for binary markets, we estimate the semantic covariance structure using Jaccard word-level similarity:

$$J(A, B) = \frac{|W_A \cap W_B|}{|W_A \cup W_B|}$$

The correlation matrix is approximated as:

$$\rho_{ij} \approx \begin{cases} J(i,j) & \text{if same category} \\ 0.5 \cdot J(i,j) & \text{cross-category} \end{cases}$$

Markets with $J > 0.30$ are treated as a **single risk unit** — only the position with maximum $\varepsilon_{\text{Shin}}$ is retained.

### 2.5 Black-Scholes Implied Probability (TradFi Overlay)

For markets referencing financial assets (BTC, ETH, SPY, etc.), we augment Shin debiasing with a model-free probability from the options market:

$$P(S_T > K) = N(d_2), \quad d_2 = \frac{\ln(S/K) + (r - q - \tfrac{1}{2}\sigma^2)T}{\sigma\sqrt{T}}$$

Volatility $\sigma$ is estimated via **VRP blending**:

$$\hat{\sigma} = 0.7 \cdot \sigma_{\text{IV}} + 0.3 \cdot \sigma_{\text{HV}}$$

This strips the volatility risk premium while retaining forward-looking information from the options surface.

---

## 3. Signal Generation Pipeline

```
                           ┌─────────────────────────────┐
                           │    POLYMARKET GAMMA API      │
                           │   ~3,000 active markets      │
                           └─────────────┬───────────────┘
                                         │
                    ┌────────────────────▼────────────────────┐
                    │         STAGE 1: CLASSIFICATION          │
                    │  NLP keyword → {category, market_type}   │
                    │  Regex + heuristic → temporal features    │
                    └────────────────────┬────────────────────┘
                                         │ ~2,400 classified
                    ┌────────────────────▼────────────────────┐
                    │         STAGE 2: TEMPORAL FILTER          │
                    │  lifecycle_pct > 0.75 ∧ days_left < 3    │
                    │  Rejects: long-dated, early-stage         │
                    └────────────────────┬────────────────────┘
                                         │ ~800 in window
                    ┌────────────────────▼────────────────────┐
                    │         STAGE 3: PRICE FILTER             │
                    │  yes ∈ [0.05, 0.15] ∧ no ∈ [0.85, 0.95] │
                    │  Liquidity > $250, Volume > $10           │
                    └────────────────────┬────────────────────┘
                                         │ ~200 candidates
                    ┌────────────────────▼────────────────────┐
                    │         STAGE 4: SHIN DEBIASING           │
                    │  ε_Shin = P_true(No) - q_No              │
                    │  Require ε > ε_min(category)             │
                    └────────────────────┬────────────────────┘
                                         │ ~80 with edge
                    ┌────────────────────▼────────────────────┐
                    │         STAGE 5: TOXIC FLOW DEFENSE       │
                    │  vol_24h / liquidity < 15× (HFT guard)   │
                    │  Rejects spiking markets (news arrival)   │
                    └────────────────────┬────────────────────┘
                                         │ ~60 deployable
                    ┌────────────────────▼────────────────────┐
                    │         STAGE 6: CORRELATION CLUSTER      │
                    │  Jaccard(i,j) > 0.30 → keep max edge     │
                    │  Category caps: sports≤20, politics≤8     │
                    └────────────────────┬────────────────────┘
                                         │ ~40 positions
                    ┌────────────────────▼────────────────────┐
                    │         STAGE 7: EXECUTION                │
                    │  L2 order book walk, ≤3% slippage cap    │
                    │  Position = 2.5% equity, half-Kelly       │
                    └────────────────────────────────────────────┘
```

---

## 4. Risk Management

### 4.1 Variance Decomposition

Portfolio variance decomposes into systematic (correlated) and idiosyncratic (diversifiable) components:

$$\text{Var}(R_p) = \underbrace{\sum_i \sum_j w_i w_j \rho_{ij} \sigma_i \sigma_j}_{\text{systematic}} + \underbrace{\sum_i w_i^2 \sigma_i^2 (1 - R_i^2)}_{\text{idiosyncratic}}$$

With $n \geq 40$ uncorrelated positions at equal weight, idiosyncratic variance $\to 0$ by the law of large numbers. The Jaccard clustering ensures $\rho_{ij} \approx 0$ across retained positions.

### 4.2 Maximum Drawdown Bounds

> **Correction.** The drawdown and ruin figures below came from the synthetic 300K-path
> simulation that fabricated resolutions and returns. They are withdrawn as evidence and
> retained only as legacy text. No validated drawdown bound exists.

From the empirical Monte Carlo (300K simulations), the drawdown distribution:

| Quantile | Max Drawdown | Recovery Trades |
|---|---|---|
| Median | -2.1% | 8 |
| 95th percentile | -8.4% | 25 |
| 99th percentile | -14.6% | 45 |
| 99.9th | -21.3% | 70 |

The absorbing barrier (ruin) probability under half-Kelly at 2.5% sizing:

$$\Pr(\text{ruin}) < 10^{-6} \text{ per 1,000 trades}$$

### 4.3 Regime Detection

The strategy monitors for regime shifts via:

1. **Rolling win-rate z-score**: If $\hat{p}_{30} < \bar{p} - 2\sigma$, reduce position sizes by 50%
2. **Volume-liquidity ratio**: HFT spike detection per-market
3. **Category concentration**: Halt deployment if any single category exceeds 60% of deployed capital

### 4.4 Parameter Sensitivity

> **Correction.** This sensitivity table is legacy synthetic output; the Sharpe deltas were
> not computed from observed data and are withdrawn. Current parameter meanings are documented
> in `strategy.py`.

| Parameter | Base | -20% | +20% | Sharpe Δ |
|---|---|---|---|---|
| $\gamma_{\text{sports}}$ | 1.20 | 0.96 | 1.44 | ±0.3 |
| Position size | 2.5% | 2.0% | 3.0% | ±0.15 |
| Jaccard threshold | 0.30 | 0.24 | 0.36 | ±0.2 |
| Min Shin edge | 3.0¢ | 2.4¢ | 3.6¢ | ±0.4 |

The strategy is most sensitive to $\varepsilon_{\min}$ — tighter edge thresholds dramatically improve Sharpe but reduce trade count.

---

## 5. Performance Analytics

> **Correction.** The tables in this section are **unvalidated legacy output** from a
> backtest that fabricated resolutions and returns for demonstration. They are kept only to
> document the original hypothesis and must not be cited as results. The current comparison
> harness (`poly_alpha.backtesting.comparison`) reports in-sample metrics only, is **not
> annualized**, and is explicitly not a forecast.

### 5.1 Legacy synthetic backtest (not evidence)

Configuration: 50 trades/cycle, 300K synthetic paths, 2% position sizing. **Synthetic paths,
not observed data.**

| Statistic | Value |
|---|---|
| Median cycle return | +2.8% |
| Mean cycle return | +3.1% |
| Annualized return (compounded) | +142% |
| Sharpe ratio (annualized) | 2.7 |
| Sortino ratio | 4.1 |
| Max drawdown (99th pctile) | -14.6% |
| Probability of profit | 72.4% |
| Calmar ratio | 9.7 |

### 5.2 Return Distribution

```
Cycle Return Distribution (300K simulations)
──────────────────────────────────────────────

         ▏   ╷
    -8%  ▏   │    ← 1st percentile
         ▏   │
    -3%  ▏  ╭┤    ← 5th percentile
         ▏  │├─╮
     0%  ▏  ││ │
         ▏  ││ │
   +2.8% ▏──┤│ │── ← MEDIAN
         ▏  ││ │
   +5.3% ▏  │├─╯  ← 75th percentile
         ▏  ╰┤
   +9.5% ▏   │    ← 95th percentile
         ▏   │
  +12.8% ▏   ╵    ← 99th percentile
         ▏
         └─────────
```

### 5.3 Edge Decay Analysis

> **Correction.** The lifecycle win rates and information ratios below are **legacy synthetic
> output** and are withdrawn as evidence; they were not computed from observed resolutions.

The favorite-longshot bias is not constant across market lifecycle:

| Lifecycle Phase | Win Rate | Shin Edge | Information Ratio |
|---|---|---|---|
| Early ($t/T < 0.25$) | 89% | +6.0¢ | 1.8 |
| Middle ($0.25 < t/T < 0.75$) | 85% | +0.0¢ | 0.0 |
| Late ($t/T > 0.75$) | 83% | -2.0¢ | -0.6 |

**Key insight:** We only trade the early-resolved portion of late-stage markets — those that entered our universe in terminal phase but whose fundamentals haven't shifted. The "middle" phase shows zero edge because prices are efficient in equilibrium.

---

## 6. Implementation

### 6.1 Installation

```bash
git clone https://github.com/yourusername/poly-alpha.git
cd poly-alpha
uv sync
```

### 6.2 Paper Trading

```bash
# Initialize paper wallet ($1,000 starting capital)
uv run poly-alpha init

# Execute one full cycle: settle resolved → scan → deploy new
uv run poly-alpha step

# Portfolio status and PnL
uv run poly-alpha status
```

### 6.3 Live Execution

```bash
# Requires POLY_KEY and POLY_SECRET environment variables
uv run poly-alpha live --capital 5000
```

### 6.4 Backtesting

```bash
# Synthetic Monte Carlo over hardcoded win-rate assumptions (not a backtest)
uv run poly-alpha backtest empirical --iterations 300000

# Synthetic market replay with fabricated resolutions (not a backtest)
uv run poly-alpha backtest mc --iterations 10000
```

### 6.5 Strategy Presets

| Preset | Max Slots | Edge Floor | Position Size | Use Case |
|---|---|---|---|---|
| `strict` | 15 | 3.5¢ | 2.5% | Conservative, high conviction |
| `balanced` | 30 | 2.5¢ | 1.5–2.5% | Default production |
| `acceleration` | 100 | 1.5¢ | 0.4–1.25% | Maximum diversification |
| `throughput` | 80 | 2.0¢ | 1.0% | High trade count |

```bash
export POLY_ALPHA_PRESET=acceleration
```

### 6.6 Research platform (offline, labeled data)

These commands run entirely on deterministic fixtures and demo data and make no network
calls. Every value carries `Provenance`; outputs are tagged `FIXTURE`, `SIMULATED`, or
`SYNTHETIC`, never presented as real observations. See `docs/DATA_PROVENANCE.md`.

```bash
uv run poly-alpha research markets --all      # labeled fixture + synthetic markets
uv run poly-alpha research research --json    # research notes with uncertainty + sources
uv run poly-alpha research screen             # rank by the conservative edge lower bound
uv run poly-alpha research size               # conservative fractional-Kelly sizing
uv run poly-alpha research report             # provenance-labeled Markdown dossier
uv run poly-alpha research compare            # in-sample strategy comparison (demo data)
uv run poly-alpha research simulate           # paper equity curve over demo resolutions
uv run poly-alpha research overview           # cross-market ranking by research edge
uv run poly-alpha research validate           # contract invariant check on all markets
uv run poly-alpha research journal            # append a provenance summary of a run
uv run poly-alpha research history            # list recorded research journal entries
uv run poly-alpha research risk               # demo concentration + historical risk
uv run poly-alpha research serve --port 8000  # read-only JSON API + dashboard at /
```

---

## 7. Architecture

```
src/poly_alpha/
├── contracts.py             # Contracts: provenance, snapshots, uncertainty
├── strategy.py              # Signal: classification, Shin debiasing, Kelly
├── cli.py                   # Interface: Typer CLI
├── cli_platform.py          # Interface: research/compare/risk/serve commands
├── adapters/                # Data: fixture, Polymarket (REAL), synthetic series
├── research/                # Research: provenance-tagged notes + uncertainty
├── portfolio/               # Risk: concentration, HHI, historical VaR
├── api/server.py            # Interface: stdlib read-only JSON API
├── execution/
│   ├── paper_engine.py      # Execution: paper trading (SQLite persistence)
│   └── live_executor.py     # Execution: live CLOB orders + risk filter
├── data/
│   ├── polymarket.py        # Data: Gamma API client
│   └── tradfi.py            # Data: Black-Scholes, yield curve, vol surface
└── backtesting/
    ├── comparison.py        # Validation: in-sample strategy comparison
    ├── demo_data.py         # Validation: labeled simulated demo dataset
    ├── empirical.py         # Validation: Reichenbach-calibrated MC (synthetic)
    └── monte_carlo.py       # Validation: synthetic replay (not a backtest)
```

---

## 8. References

1. Reichenbach, F. & Walther, M. (2025). *"Exploring Decentralized Prediction Markets: Accuracy, Skill, and Bias on Polymarket."* Working paper. Analysis of 124M trades, 77K resolved markets.

2. Shin, H.S. (1992). *"Prices of State Contingent Claims with Insider Traders, and the Favourite-Longshot Bias."* The Economic Journal, 102(411), 426–435.

3. Kelly, J.L. (1956). *"A New Interpretation of Information Rate."* Bell System Technical Journal, 35(4), 917–926.

4. Griffith, R.M. (1949). *"Odds Adjustments by American Horse-Race Bettors."* American Journal of Psychology, 62(2), 290–294.

5. Thaler, R.H. & Ziemba, W.T. (1988). *"Anomalies: Parimutuel Betting Markets: Racetracks and Lotteries."* Journal of Economic Perspectives, 2(2), 161–174.

6. Markowitz, H. (1952). *"Portfolio Selection."* The Journal of Finance, 7(1), 77–91.

7. Black, F. & Scholes, M. (1973). *"The Pricing of Options and Corporate Liabilities."* Journal of Political Economy, 81(3), 637–654.

---

## License

MIT
