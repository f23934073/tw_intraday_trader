# Findings

## Confirmed failure

- 同一 immutable Dataset 與相同 revision-2 contract 已完整失敗兩次；目前是第三次執行。
- 兩次都在 Dataset EOF 後回傳：
  `G3 eligible symbol/session ratio below 0.95`。
- launchd evidence：`runs=3`、`last exit code=1`。目前 worker 仍在重複掃描。
- PostgreSQL formal attempts 仍為 `0`；沒有進入 G4。

## Prefix evidence from the active third run

2026-08-27 讀取 active eligibility JSONL 的一致前綴快照，當時統計：

```text
observed symbol-sessions: 94,215
eligible:                 74,355
excluded:                 19,860
eligible ratio:           0.789205541

missing exact 12:45 only:          19,474
missing exact 12:45 and 13:30:        328
missing exact 13:30 only:              58
```

年度前綴比例穩定落在約 76.6% 至 79.7%，不是單一日期或短暫下載異常：

```text
2023  0.765571
2024  0.796761
2025  0.791083  (prefix)
```

Dataset manifest 同時宣告 dominant one-minute interval ratio 約 `0.8939`、
`132,234` symbol-sessions、每 session 最多 `266` bars。這與 sparse
trade-derived minute bars 相符：沒有成交的分鐘不一定存在 Kbar。

## Root cause

Revision 2 把「exact 12:45 Kbar 存在」當成所有入場訊號可在 deadline 前取得
next bar 的充分條件。它是充分但不必要的條件，且不適合 sparse minute Dataset。

多數 excluded session 只缺 exact `12:45`，仍可能存在較早的最後一根 Kbar，並能讓
更早訊號在同 session、deadline 前使用 next-observed-bar 成交。因此目前失敗是
Dataset cadence 與 eligibility contract mismatch，不是理由去補 bar 或降低品質門檻。

## Recommended contract

對每個 `(symbol, session_date)`，只從 source timestamps 推導：

```text
entry_reserve_at = max(observed Kbar timestamp <= 12:45)
terminal_exit_at = exact observed 13:30 Kbar
runtime signal eligibility = signal_at < entry_reserve_at
entry = next observed same-symbol Kbar strictly after signal
entry_at <= entry_reserve_at <= 12:45
exit = exact same-symbol 13:30 close
```

這個 cutoff 可以隨 symbol-session 的 sparse cadence 改變，但完全不讀策略輸出、價格、
return 或 P&L，且七個 slot 共用同一 source-derived mask/cutoff。

## Rejected alternatives

- 直接把 coverage floor 從 `0.95` 降到約 `0.79`：會讓門檻追著結果走。
- forward-fill exact `12:45`：會製造不存在的成交流動性與價格。
- 允許隔日或 13:30 後 entry/exit：破壞當沖與 no-overnight 契約。
- 每個策略各自忽略 unfillable signal：會造成策略間樣本不一致。

## Chosen remediation and containment

- Preserve the `0.95` floor and exact `13:30` exit.
- Do not synthesize or forward-fill Kbars.
- Derive `entry_reserve_at` from the last observed same-symbol Kbar at or before
  `12:45`, require an earlier source observation, and apply one common mask to
  all seven strategies before runtime.
- Make the change additive as revision 3; revision 2 remains sealed negative
  evidence.

## Operational containment

- The repeated launchd job is unloaded and PID 1978 is absent.
- The 488 MB third-run staging tree was moved intact under `interrupted/`.
- New workers atomically claim a run root once; a second launchd invocation
  returns before environment, PostgreSQL, or Dataset access.

## A2 independent Review

First-pass disposition was `REQUEST CHANGES`:

- the source audit was Dataset-bound but not bound to the exact family,
  revision-2 matrix, baseline, registration, head, attempts, candidate protocol,
  or audit implementation;
- audit and preflight shared only the final decision function while duplicating
  source-anchor accumulation.

Remediation introduced the exact `r6-eligibility-source-audit-v2` scope,
year/symbol projections, expected-scope verification, and one shared source
accumulator. Scope substitution, symbol-total substitution, mixed sparse
boundary parity, revision-2 replay, and supervisor one-shot coverage pass.

Independent re-review disposition:

```text
A2: APPROVED / CONTRACT FROZEN
Source-only full audit: AUTHORIZED / NOT YET EXECUTED
Migration 018: BLOCKED ON AUDIT RATIO >= 0.95
```

## Source-only full audit result

The one authorized traversal completed without strategy runtimes, preflight
registration, attempts, or PostgreSQL mutations:

```text
Dataset bars / source EOF: 28,325,340 / verified
Observed symbol-sessions:  132,234
Eligible:                  131,691
Excluded:                      543
Coverage:                  0.995893643087254413
Floor:                     0.95
Missing entry reserve:         17
Missing prior signal bar:      43
Missing exact 13:30 exit:     520
```

Canonical audit digest:
`2e4f8590d0de3f963e4d41bc17d87fd859809053f9f2206015ba69d46863131d`.
The independently reloaded artifact has four yearly rows, 182 sorted symbol
rows, exact canonical bytes, and family head/attempt evidence `0/0`.

Disposition: coverage exceeds the frozen floor, so Migration 018 design is now
authorized. This does not authorize a seven-slot preflight or any attempt.

## Migration 018 disposition

The forward-only migration was independently validated against a populated
revision-2 graph on disposable PostgreSQL 17, including a negative head-drift
case. Formal application used the accepted audit as a precondition and then
verified the production Backtest database in a read-only transaction.

```text
Migration count:             18
Latest:                      018_r6_dynamic_entry_reserve.sql
Active matrix revision:      2
Family head / attempts:      0 / 0
Release:                     NOT_READY
Revision-3 matrix count:     0
Preflight count:             0
Audit registration count:   0
```

Migration 018 is complete. Durable audit registration and revision-3 matrix
activation remain separate, unapplied transaction boundaries.
