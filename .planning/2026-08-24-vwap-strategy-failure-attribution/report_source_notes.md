# Report Source Notes

> Contract update (2026-08-25): the canonical artifact and HTML report were
> regenerated with a visible superseded notice. R5 is a
> `cash-admission-neutral sensitivity control`, not a fully allocation-neutral
> estimator. The authoritative R6 family budget remains the server-owned 20
> attempts; the seven strategies are sealed slots 1-7. Baseline measurements
> are unchanged.

## Reporting job

- Question: Why did the completed `above_vwap_entry_v1` backtest lose almost all starting equity, and what research action is justified next?
- Audience: technical reviewer.
- Decision supported: whether to tune, retire, combine, or replace this atomic ENTRY hypothesis.
- Baseline: immutable Run `run-91ad87981676414da87b928398fa43c9` only.
- Delivery mode: portable HTML fallback because this runtime exposes no Data Analytics MCP artifact validation/rendering tools. The canonical artifact contract and packaged report builder remain required.
- Final canonical artifact SHA-256:
  `16877f66b81ecd937107498b18d6627dbd036f86d0f5ffff193d9a96d29822cf`.
- Final HTML SHA-256:
  `cdc50550503ea7a9790ca99aa32e7e23ed4c9a4bdd0f6069379a5d693157f15b`.
- Builder receipt: validation/package/browser verification passed; 20 blocks,
  3 charts, 5 metric cards, 1 table, source dialog and keyboard interaction,
  1440 px and 390 px viewports passed.

## Required technical-report structure mapping

1. Title — exact visible report title.
2. Technical summary — answer-first disposition and confidence.
3. Key findings — cost bridge, admission bias, and normalized period evidence.
4. Scope/data/definitions — Run, Dataset, strategy Version, order/trade grain, percent scales.
5. Methodology — read-only SQL and source-code contract inspection.
6. Limitations/robustness — exploratory Dataset, no independent exit attribution, no causal claim.
7. Recommended next steps — one sealed R5 control, then the atomic research
   matrix under a frozen exit/cost protocol.
8. Further questions — execution allocation and exit-path evidence needed before combinations.

## Chart map

### Cost decomposition

- Analytical question: How much of the net loss came from the signal/holding path versus slippage and explicit costs?
- Takeaway: costs amplified the loss, but the pre-slippage price path was already negative.
- Family/type: Decomposition & Progression / `waterfall`.
- Rows: pre-slippage price P&L, slippage drag, fees/tax drag, net P&L.
- Palette: hard two-root cap with neutral anchors; signed labels and zero context.
- Output: full-width native chart in the portable HTML report.

### Same-day admission rank

- Analytical question: Does deterministic signal order affect which symbols become trades?
- Takeaway: fill rate collapses from 39.37% in ranks 1-10 to 0.73% in ranks 101+.
- Family/type: Comparison & Ranking / `horizontalBar`.
- Rows: five mutually exclusive rank buckets; 128,802 total ENTRY signals.
- Palette: single-root blue, direct percent labels, no legend.
- Output: full-width native chart in the portable HTML report.

### Normalized performance by year

- Analytical question: Did trade-level performance recover after the early capital drawdown?
- Takeaway: average net return per trade stayed negative in every calendar year.
- Family/type: Comparison & Ranking / `bar` with zero reference.
- Rows: four calendar years, 6,321 trades total.
- Palette: single-root orange with neutral zero reference; no green/red semantics.
- Output: full-width native chart in the portable HTML report.

## Sources

- Reproducible SQL: `evidence_queries.sql` in this planning directory.
- Structured tables: `backtest.backtest_runs`, `backtest.backtest_results`, `backtest.backtest_result_chunks`, `backtest.backtest_decisions`, `backtest.backtest_trades`, `backtest.backtest_daily_equity`, `backtest.strategy_versions`.
- Runtime contracts: `backtest/engine.py`, `atomic_strategies/entries/above_vwap.py`.
- Immutable Dataset manifest and G5 acceptance plan are supporting provenance, not a substitute for Run evidence.

## Omitted analyses

- MFE/MAE and fixed-horizon exit counterfactuals require a 5.5 GiB bar-stream join. They are not inferred from entry/exit trades.
- A cross-up challenger is not automatically selected: under this Run's 09:01 start and one-attempt-per-symbol/day state, the first strict above-VWAP event is usually already the first cross-up event. It may not create a meaningfully different hypothesis.
- No parameter optimization is performed on this baseline because it would consume the same evidence for both hypothesis generation and validation.
