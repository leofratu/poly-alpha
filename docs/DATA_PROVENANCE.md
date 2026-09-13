# Data Provenance

Reference for how `poly_alpha` records where data came from. The goal is simple: generated
or fixture data must never be mistaken for a real observation.

## `DataSourceKind` values

Defined in `src/poly_alpha/contracts.py`.

| Kind | Meaning |
|------|---------|
| `REAL` | Observed from a live external source. The only kind not derived from scratch. |
| `FIXTURE` | Hand-authored, deterministic data for development and tests. Not market data. |
| `SIMULATED` | Model-generated output, such as the research engine's heuristic adjustment. |
| `SYNTHETIC` | Derived or generated series, such as probabilities from supplied price tails. |

`DataSourceKind.is_real` is `True` only for `REAL`, so callers can gate on it directly.

## The provenance rule

Every `MarketSnapshot` carries a `Provenance` (`source`, `kind`, `retrieved_at`, `url`,
`note`), and every `ResearchNote` carries the snapshot's `Provenance` plus per-claim
`sources`. Model estimates also record `Uncertainty.simulated` so an interval can be
labeled honestly even when the underlying data is real.

Consequently there is no code path that produces a snapshot or a note without a
`DataSourceKind`. Downstream consumers should treat a missing or `REAL`-less provenance as
non-real data.

## Which module produces which kind

| Producer | Kind | Notes |
|----------|------|-------|
| `adapters/polymarket.py` | `REAL` | Polymarket Gamma API; `Provenance.url` set to the API base. |
| `adapters/kalshi.py` | `REAL` | Kalshi Trade API v2, read-only `GET /markets`; YES bid/ask midpoint in dollars, liquidity/volume are contract counts (see the provenance note). |
| `data/kalshi.py` | (n/a) | Read-only Kalshi client; no auth headers, no secrets. |
| `adapters/fixtures.py` | `FIXTURE` | Static `_SPECS`; fixed `FIXTURE_AS_OF` timestamp. |
| `adapters/series.py` | `SYNTHETIC` | Probabilities derived from the last two points of a supplied series. |
| `adapters/registry.py` | (carries) | Concatenates labeled snapshots; `markets_by_kind` counts them by kind. |
| `adapters/history.py` | `FIXTURE` | Deterministic multi-step price paths; not real history. |
| `research/calibration.py` | (consumes) | Reports interval coverage over supplied outcomes; simulated unless notes are real. |
| `backtesting/simulation.py` | (consumes) | Equity curve from supplied resolved markets; fixed caveat, no provenance claim. |
| `research/analyst.py` | `SIMULATED` | Heuristic adjustment provenance; model/edge `Uncertainty.simulated=True`. |
| `research/notes.py` | (carries) | Re-exposes the snapshot's `Provenance`; `source_kinds()` lists all kinds cited. |
| `research/screen.py` | (consumes) | Ranks by `note.edge.low`; `Opportunity.is_real` reflects the note's provenance. |
| `research/report.py` | (exposes) | Renders a provenance summary and labels every note's kind in the dossier. |
| `research/overview.py` | (consumes) | Row-level `simulated` flag combines model simulation with provenance kind. |
| `research/journal.py` | (records) | Append-only JSONL with per-kind counts and an explicit `simulated` flag. |
| `validation.py` | (consumes) | Flags malformed provenance or out-of-range values; returns issues, never raises. |
| `portfolio/sizing.py` | (consumes) | Uses `Uncertainty` bounds; emits a rationale, not a market-data claim. |
| `portfolio/risk.py` | (carries) | Each `Position` carries a `Provenance`; the report summarizes positions. |
| `backtesting/comparison.py` | (consumes) | Reads snapshot provenance; `StrategyMetrics` carries a fixed caveat string, not a `Provenance`. |
| `api/server.py` | (exposes) | Serializes provenance as-is; `/research` includes a top-level `simulated` flag. |

## Display guidance

Any UI, report, or exported artifact that shows a snapshot, note, metric, or risk report
must display its `kind` alongside the value. At minimum:

- Show the `DataSourceKind` label and `source` for every market and research note.
- Surface the `/research` response's `simulated` flag, or recompute it from the kinds.
- Never present `FIXTURE`, `SYNTHETIC`, or `SIMULATED` output as observed market data.
- Never present in-sample backtest metrics as forecasts or as evidence of future returns.

If a display cannot attribute a value to a `DataSourceKind`, treat the value as non-real
and label it as such until provenance is available.
