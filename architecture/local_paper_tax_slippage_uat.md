# Local Paper Tax / Slippage v2 Verification Evidence

## Scope and boundary

- Date: 2026-08-26 (Asia/Taipei)
- Source base: Kill Switch candidate `34fb5250030d170b7909870f086c5693f728a9aa`
- Mode: `LOCAL_PAPER_SIMULATION`
- Cost scope: proved TWSE/TPEX common stock, cash, non-day-trade only
- No Shioaji order/account/CA/trade callback or real-money authority was added.
- Fixed 5 bps remains `ASSUMPTION_NOT_LIVE_CALIBRATED`; live calibration is not part of this evidence.

## Policy and schema identity

| Contract | Version |
|---|---|
| Settings | `local-paper-settings-v2` |
| Fill event | `local_paper_fill.v3` |
| Fee | `tw_stock_standard_v1` |
| Rounding | `twd_round_down_v1` |
| Slippage | `fixed_adverse_bps_v1` |
| Price tick | `tw_common_stock_tick_v1` |
| Instrument descriptor | `local-paper-instrument-descriptor-v1` |

## PostgreSQL restart UAT

The database was a disposable local PostgreSQL 16 container named
`codex-tw-local-paper-tax-slippage-pg-20260826`. The database name contains an
explicit `test` token. The DSN is intentionally omitted from this artifact.

Command shape:

```bash
TEST_POSTGRES_DSN='postgresql://.../tw_local_paper_test' \
  <existing-project-venv>/bin/pytest -q \
  tests/test_local_paper_postgres.py \
  tests/test_kill_switch_postgres.py \
  tests/test_phase5_paper_sell_postgres_uat.py \
  tests/test_postgres_journal.py
```

The existing project virtualenv executable was used read-only; the command cwd
and every source/artifact write remained in this isolated worktree.

Final result after the complete review/fix/re-review cycle:
`5 passed in 0.76s`.

The new tax/slippage case performed:

1. A 1,500-share BUY as two fills (1,000 + 500) using best ask 100, 5 bps
   adverse adjustment, and legal fill price 100.5.
2. A 1,500-share SELL as two fills (1,000 + 500) using best bid 110, 5 bps
   adverse adjustment, and legal fill price 109.5.
3. Exact accounting assertions: cash `10,012,560`, realized PnL `12,560`,
   commission `448`, tax `492`, and diagnostic slippage `1,500`.
4. Three complete reconstructions, each using a newly opened psycopg connection.
5. Exact comparison of session metadata, Journal kinds, checkpoint sequence and
   digest, cash, buy notional, realized PnL, cost totals, positions, order totals,
   and fill sequence on every reconstruction.
6. PostgreSQL payload corruption of the final SELL order-state tax; the next
   runtime construction rejected the canonical order-state digest mismatch.
7. PostgreSQL payload corruption of the final SELL fill tax; the next runtime
   construction rejected the invalid `local_paper_fill.v3` and did not mutate.

The review cycle additionally verified exact cumulative gross, commission, tax,
and fill-sequence lineage across partial fill.v3 events. Coherent commission/net
tampering, later-fill append failure, unresolved cancellation tails, duplicate
equal-timestamp BBO volume, invalid v2 tick admission, and negative SELL net cash
all fail closed without silently mutating cash or admitting a later intent.

The first formal execution exposed only an assertion that compared different
Decimal display scales as strings (`12560.000...` versus `12560.0`). The test
was corrected to compare Decimal values; no accounting policy or runtime value
was changed. The standalone rerun then returned `1 passed in 0.36s` before the
combined five-test PostgreSQL run above.

## Focused and browser evidence

- TS-G1 pure domain/provider: `56 passed`.
- TS-G2 core/replay: `125 passed`.
- TS-G2b composition/restart/Kill Switch: `94 passed in 0.61s`.
- TS-G3 settings/API/static: `88 passed in 1.42s`.
- Final focused verification: `241 passed, 1 skipped in 2.03s`; the skip was the
  expected no-DSN PostgreSQL test and was not treated as a PostgreSQL pass.
- Full no-DSN regression: `1500 passed, 43 skipped in 8.25s`; the formal
  PostgreSQL result above is separate and does not rely on these skips.
- JavaScript syntax and `git diff --check`: passed.
- Local browser smoke: desktop, 375x667 portrait, and 667x375 landscape.
  The settings drawer had no horizontal overflow, retained 44px inputs, was
  vertically scrollable, disabled apply for an unsaved v2 preview, and emitted
  no console errors. The cache-busted v2 CSS and JavaScript assets were served.

## Remaining non-gate work

- Real slippage calibration across multiple trading days, liquidity tiers, and
  opening/continuous/closing periods remains a separate evidence task.
- This simulator still has no real queue priority, multi-level depth, market
  impact, broker accounting, or real-money promotion path.
- The requested severity-first review/fix/re-review loop ended with `APPROVE`;
  no unresolved P1/P2 correctness finding remains in the reviewed candidate.
