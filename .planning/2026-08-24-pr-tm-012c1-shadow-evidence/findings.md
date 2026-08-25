# Findings and Decisions

## 2026-08-25 Run

- Automation memory records that the PostgreSQL empty-table blocker was cleared after the prior run.
- The prior independent blockers remain subject to current-checkout verification: no complete executable C1 composition, pre-open/full-window activation contradiction, incomplete dirty-worktree identity, and no explicit C0 `execution_authority=false` binding.
- Host time at intake was 2026-08-25 08:45 Asia/Taipei, before open.
- Reviewed calendar accepted 2026-08-25 with schema `twse_calendar_2026_v1` and digest `1671338c8247f7f5344657912f469fce111b82b9be0dea1d61d21eb6d3a3593a`.
- Current-checkout Python references to `TradeManagementOperationalComposition`, `LiveShadowCaptureRunner`, and `LiveTradeManagementShadowOperation` remain limited to runtime modules and tests; no executable complete C1 composition exists.
- Formal C0 prepared at 08:47:27 returned `BLOCKED` with `POSTGRES_PREFLIGHT_FAILED`, `POSTGRES_NOT_READ_ONLY`, `POSTGRES_SCHEMA_MISMATCH`, and `POSTGRES_MIGRATION_MISMATCH`.
- PostgreSQL DSN was configured and psycopg 3.3.4 was present, but the connection failed with redacted `OPERATIONALERROR`; reported zero row counts are fallback placeholders and are not authoritative emptiness evidence.
- Provider preflight passed: `shioaji:1.7.2:simulation=true`, login/logout true, `subscribe_trade=false`.
- C0 manifest retained `execution_enabled=false` but still lacks an explicit prospective `execution_authority=false` field; code identity remains Git HEAD only on a dirty worktree.
- Fixture/historical rehearsal passed all five checks but is non-qualifying and cannot substitute for live C1 evidence.
- Formal artifact is `research/trade_management_shadow/premarket_20260825.json`; readiness digest `5f0ed4f0df44e4066a20f964b30a32932b48b65fb385ea07099992d73d54cb1c`; file SHA-256 `9e8ce4e78815378d5aaeb69ff8f6da5cf3b76222902de881da1b9512a8271caf`.
- No C1 session started. Live event/decision/journal counts, lost evidence, parity, recovery, and finalization are `N/A`, not successful zeros.

## Requirements

- Scope is Production Shadow Gate evidence collection only: data-only and decision-only.
- Before 09:00, the reviewed calendar and every C0 item must pass.
- Required safety values are `simulation=true`, `subscribe_trade=false`, `execution_authority=false`, and `execution_enabled=false`.
- PostgreSQL journal schema/DSN and complete provider/runtime identity are mandatory.
- No code repair, order/fill creation, simulated matching, Position mutation, broker order API, or execution-capability expansion is authorized.
- Full-session evidence must cover 09:00-13:30 and finish with finalize, recovery, replay parity, deterministic readiness, absolute paths, and digests.
- One successful day cannot mark Production Shadow Gate `PASSED`.

## Prior Reviewed Evidence

- Prior short capture proved canonical ingress/replay determinism only; it did not qualify a full session.
- Qualification requires a finalized canonical session, zero lost evidence, authoritative existing local-paper BUY-fill activation, PostgreSQL restart reconstruction, recovery digest match, and exact replay `MATCHED`.
- With no existing BUY fill, market-session qualification may pass but trade lifecycle stays `INSUFFICIENT_EVIDENCE` and the Production Shadow Gate remains `NOT_PASSED`.
- The originally rendered one-time 2026-08-24 automation was not confirmed active in the prior rollout; this run is the first confirmed automation execution.

## Current Environment

- Automation memory did not exist at run start.
- Host time at initial intake was `2026-08-24T08:35:55+08:00`, before the TWSE open.
- The worktree already contains broad unrelated modifications; this run will not touch product code.
- No repository `AGENTS.md` was found.
- The reviewed calendar is `config/twse_calendar_2026.json`, loaded by `ReviewedEquityCalendar`.
- A dedicated C0 CLI exists at `scripts/preflight_trade_management_shadow.py`.
- Core runtime modules exist for premarket readiness, live capture, operational composition, Shadow operation, validation, replay, and PostgreSQL journals.
- The initial inventory did not identify an obvious full-session C1 runner; this must be confirmed from the runbook and CLI modules before any session starts.
- The operational runbook describes the desired normal-session procedure but states that the PR-TM-012B provider-neutral live callback runner accepts only an already-existing `PaperFillThesisActivation`; it does not create a Thesis, submit or observe a paper fill, load a DSN, or own order capability.
- The runbook says PR-TM-012B2 provides operational composition from EntryDecision/Draft to an observed fill and separate evidence Journal, but no full market session has been recorded.
- `scripts/run_momentum_shadow.py` is a realtime momentum alert-only runtime, not the required TM-012C1 Trade Thesis/live-operation evidence runner.
- No CLI inventory result connected C0 output, PostgreSQL evidence Journal, observed-fill activation, live canonical stream, finalization, recovery, parity, and readiness into one full-session entrypoint.
- Formal C0 ran at `2026-08-24T08:38:47+08:00` and returned `BLOCKED` with the sole blocker `POSTGRES_EVIDENCE_NOT_EMPTY`.
- Reviewed calendar passed implicitly: no `UNREVIEWED_TRADING_DATE` blocker was emitted, and the manifest bound `twse_calendar_2026_v1` digest `1671338c8247f7f5344657912f469fce111b82b9be0dea1d61d21eb6d3a3593a` to 2026-08-24.
- Provider C0 passed data-only safety: `shioaji:1.7.2:simulation=true`, login/logout true, `subscribe_trade=false`.
- PostgreSQL was configured, connected read-only, schema/migrations matched, server major 17, but existing counts were `journal_sessions=2`, `journal_records=3`, `projection_checkpoints=2`; the frozen evaluator requires all authoritative evidence tables empty.
- Rehearsal evidence passed all five fixture/historical checks, but remains explicitly non-qualifying and cannot replace a live session.
- Preflight readiness digest is `fbe77771a8f3574d16775531a674b273a2248af559794ddfebcb5aec8bf29110`; artifact file SHA-256 is `42074c08fbee28b1dfa739af1b657e9b132d85d0b854ecef97250ac549b3b925`.
- Definitive Python-reference inventory found `TradeManagementOperationalComposition` and `LiveShadowCaptureRunner` only in their runtime modules and tests; no executable script imports or instantiates the complete C1 flow.
- `LiveShadowCaptureRunner` requires a pre-existing activation and only starts after that fill, while its full-session predicate requires subscription readiness no later than 09:00. This cannot safely provide normal 09:00 boundary coverage when the authoritative observed fill occurs after open.
- The C0 artifact does not bind an `execution_authority` field for the prospective real session. That safety property exists on an eventual activation, but no activation exists at preflight, so the automation's explicit `execution_authority=false` C0 condition is not proven by this artifact.
- Runtime code identity is incomplete for this dirty worktree: the preflight records only `git rev-parse HEAD`, not a clean-tree assertion or digest of uncommitted runtime changes.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Use only an existing reviewed live entrypoint | The prompt forbids adding a missing C1 runtime during the formal run. |
| Preserve a BLOCKED or INCOMPLETE result verbatim | Formal evidence failures cannot be patched or replaced with synthetic evidence. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Automation memory missing | Treat as first run and create it at handoff with this run's concise outcome. |
| Initial sandboxed C0 crashed in the Shioaji native SDK with `Operation not permitted` | Re-ran the identical approved data-only command outside the sandbox; it completed and returned the formal BLOCKED artifact. |
| PostgreSQL evidence tables are not empty | Stop before session start; do not clear, rewrite, or reuse formal evidence. |
| Process-list verification was denied by the sandbox | The C0 command itself returned a completed exit code and no C1 command was ever launched; do not escalate a nonessential diagnostic. |

## Resources

- Reviewed repository memory for the TM-012C preflight and full-session qualification policy.
