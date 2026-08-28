# Findings and Decisions

## Requirements

- Scope is data-only and decision-only Trade Management Shadow evidence.
- No Shioaji order API, trade subscription, CA, fill creation, simulated matching, Position mutation, or execution capability.
- Formal evidence requires reviewed calendar, pre-open READY C0, full 09:00-13:30 market coverage, PostgreSQL durability, recovery, replay parity, and deterministic reporting.
- Existing local-paper BUY fills may be observed; none may be manufactured.
- A single successful day cannot pass the Production Shadow Gate.

## Confirmed Blockers

- `LiveShadowCaptureRunner` requires `PaperFillThesisActivation` before `start()`.
- Its full-session predicate requires ACK readiness at or before scheduled open.
- Only runtime modules/tests instantiate the operational composer; there is no executable complete C1 entrypoint.
- C0 does not explicitly carry `execution_authority=false`.
- C0 runtime identity is only `git rev-parse HEAD`, despite a dirty worktree.
- C0 counts shared Journal tables globally, so Local Paper persistence can block unrelated Shadow evidence.
- The Codex automation sandbox could not reach the local PostgreSQL DSN, while the same read-only DSN succeeded outside sandbox.

## Safety Boundary

- Production Shadow Gate remains `NOT_PASSED`.
- No formal live session will be started during implementation.
- Test fixtures and historical replay remain non-qualifying.

## Technical Decisions

| Decision | Rationale |
|----------|-----------|
| Add one application coordinator around existing ports | Clean/hexagonal boundary keeps provider, DB, and CLI at the edges. |
| Keep market-session coverage independent of Thesis lifecycle | Allows truthful no-fill evidence and complete opening coverage. |
| Prefer session-scoped evidence checks over global emptiness | Shared Journal tables intentionally contain multiple runtime modes. |
| Hash runtime-relevant tracked and untracked source content | Git HEAD alone cannot identify executed dirty code. |
| Reuse the market-event JSONL evidence boundary for full-session coverage | It already seals canonical records and exact replay without requiring a Thesis. |
| Keep activated Shadow records in PostgreSQL | RiskSnapshot binding, append backpressure, restart recovery, and decision replay remain owned by the existing operation. |
| Poll existing fill authority at a bounded cadence after the decision signal | Avoids one PostgreSQL read per market Tick and never retroactively manufactures an activation. |
| Exclude absolute artifact paths from the C1 evidence digest | The report remains deterministic while still returning clickable absolute paths. |

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| Repository has broad concurrent dirty changes | Restrict edits to TM preflight/capture/CLI/tests/runbook and task-specific planning files. |
| Current `.env` has only a localhost shared Journal DSN | Do not create a database or fake separation; C1 requires explicit Local Paper and dedicated Shadow DSNs. |
| Unix-socket connection on `/tmp` failed with `OperationalError` | The existing Codex automation must remain fail-closed rather than assume sandbox-safe PostgreSQL access. |

## Resources

- `runtime/trade_management_live_capture.py`
- `runtime/trade_management_operational_composition.py`
- `runtime/trade_management_premarket.py`
- `scripts/preflight_trade_management_shadow.py`
- `architecture/trade_management_shadow_operational_readiness_runbook.md`
