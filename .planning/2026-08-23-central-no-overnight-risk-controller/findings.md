# Findings & Decisions

## Requirements
- Deliver an implementation plan only; do not change product code.
- Adopt central no-overnight option B and keep its domain/application contracts hostable by a future option C watchdog.
- Manage only `AUTO_INTRADAY` and `MANUAL_INTRADAY`; do not liquidate `AUTO_SWING` or `MANUAL_LONG`.
- Use an explicit state machine: `NORMAL`, `NO_NEW_ENTRY`, `CANCEL_ENTRY`, `FLATTENING`, `AGGRESSIVE_EXIT`, `FINAL_RECONCILIATION`, then `CONFIRMED_FLAT` or `OVERNIGHT_BREACH`.
- Cancel remaining entry quantity while treating partial BUY fills as managed positions that must be flattened.
- Aggressive exit must cancel, refresh authoritative state/book, reprice, submit idempotently, and retry within a bound.
- `CONFIRMED_FLAT` requires managed position quantity zero, pending entry zero, pending exit zero, unresolved executions zero, reconciliation match, and a snapshot after the last fill.
- `OVERNIGHT_BREACH` must be durable, critical, manually acknowledged, and block future entry across process/machine restart.
- Keep state transition times configurable; do not freeze example clock values without evidence.
- Keep strategy exit reasons separate from `SESSION_FLATTEN` or `NO_OVERNIGHT_POLICY` operational exits.
- Exclude synthetic fills, independent watchdog deployment, multi-host HA, broker production failover, and real-money activation from the first implementation scope.
- Close the review's four blocking contracts before authorizing `PR-NO-001`: durable scope identities, verifiable single-controller B startup, last-mile calendar admission, and a non-conflicting empty-session flatness rule.
- Persist the last execution-fact sequence, not only the last fill sequence.
- Bind operator acknowledgement to the latest breach revision and reconciliation digest.

## Research Findings
- Review confirmed that the plan's state identity mentions `account_scope + session_date + policy_family`, but these are not yet immutable persisted identifiers shared by ExposureIdentity, configuration, transitions, results, breaches, and Journal session metadata.
- Review confirmed that a process-local RuntimeComposition singleton does not prove a single ENFORCING controller across multiple workers or duplicate processes. Because B excludes an execution lease, startup must fail closed unless a reviewed deployment identity proves one controller host, and PostgreSQL concurrency tests must exercise two compositions.
- Review identified that semantic exit action uniqueness currently includes a mutable input digest. The digest should remain evidence only; the action key must be stable for policy family, account scope, session, exposure, action generation, and attempt.
- Review identified a last-mile admission gap: a reviewed calendar at startup does not prevent a command planned before close from reaching the handler after the session phase changes. Session phase and instrument tradability must be re-read immediately before side effects.
- Review identified a flatness contradiction: an empty managed session should confirm flat without a SELL, while any session that held managed quantity must prove every decrement through terminal fills.
- The final snapshot fence must use the latest execution fact sequence, including fill, cancel, reject, expiry, unknown, and recovery events; last-fill sequence alone is insufficient.
- Breach acknowledgement must refer to the latest breach revision and reconciliation digest and must not survive a superseding late execution fact.
- Prior current-checkout review established that the existing controller performs a bounded 13:25 Local Paper flatten for its own automated position, but this is not a central all-origin policy.
- The current readiness rule is terminal SELL `FILLED` plus authoritative managed position quantity zero, not EXIT intent or EXIT_SUBMITTED alone.
- `OrderCommand` currently carries only `origin`, optional strategy identity, side, quantity, price, retry attempt, and predecessor. It has no holding-horizon, policy-scope, managed-lot, or operational-exit identity.
- `CommandOrigin` currently distinguishes only `MANUAL_WEB` and `STRATEGY_AUTOMATED`; origin alone cannot safely decide whether a manual or automated position is intraday versus swing/long.
- `OrderApplicationService.apply()` is the canonical journal-before-side-effect seam and is therefore the correct central admission boundary; no-overnight commands must reuse it rather than call `SimulationService` directly.
- `SimulationPosition` stores ownership at aggregated symbol-position level. This is insufficient when the same symbol can contain managed intraday and excluded long-horizon lots; the plan must introduce lot/exposure lineage or reject unsafe co-mingling.
- `LocalPaperCommandService` already provides journaled idempotent submit, cancel, bounded successor retry, terminal outcome recording, and checkpoint recovery. These are reusable controller ports.
- `LocalPaperCommandService._risk_snapshot()` currently hardcodes `market_open=True` and `instrument_tradable=True`; the review's last-admission blocker is confirmed in current source.
- `dashboard.server.get_runtime_composition()` protects composition creation with a process-local lock/global only. This does not cover multiple Uvicorn workers or duplicate processes.
- `OrderApplicationService.apply()` currently receives one caller-built `RiskSnapshot`; it has no server-owned final-admission provider invoked immediately before the handler. The plan needs a fail-closed port at that seam, with a journaled no-side-effect outcome when the session phase changes.
- `ReviewedEquityCalendar` currently proves trading-day coverage/closures only. It does not define exchange session open/close phase or per-instrument tradability, so PR-NO-003 must introduce a reviewed session-window contract rather than treating the existing day calendar as sufficient.
- `JournalSession.metadata` is immutable and PostgreSQL `start_session()` detects metadata conflicts. `account_scope_id`, `policy_family_id`, policy revision, calendar digest, and deployment guard identity can therefore be frozen without a new mutable table.
- The bundled `dashboard.__main__` starts Uvicorn with its default single worker, but no runtime guard prevents alternate `--workers` launches or duplicate processes.
- `OrderApplicationService.apply()` appends the command and then calls `handler.submit()` directly; there is a precise seam for a second, server-owned final execution-admission decision and Journal record before the handler.
- Current blocked/rejected handling in `LocalPaperCommandService` records a simulated rejected order. The reviewed race test should define zero adapter/simulation order/position side effects while still permitting append-only blocked-decision evidence.
- The current Journal session is the long-lived immutable `local-paper-runtime-v1`. Adding immutable scope metadata cannot rewrite it; PR-NO-001 needs a new linked v2 Journal session and a replay/import manifest for v1 legacy facts.
- PostgreSQL Journal already enforces uniqueness on record and idempotency identities. Stable action keys can make duplicate controller proposals fail before the handler even when their mutable input evidence differs.
- A B-specific singleton guard can be stronger than a process global without becoming C's renewable/fenced lease: acquire one dedicated PostgreSQL advisory lock for `(account_scope_id, policy_family_id)`, fail ENFORCING startup for the second composition, keep it for process lifetime, and make loss of guard health block final admission. C still owns lease expiry, fencing, and HA handoff.
- Existing retry preserves the source order origin and strategy identity. A policy-driven successor needs a distinct operational exit reason while retaining the position ownership lineage it is closing.
- Cancellation is journaled before local mutation and handles `PARTIALLY_FILLED`; the controller can cancel remaining BUY quantity, then derive the filled managed exposure from the authoritative projection.
- `LocalPaperProjection` is currently keyed only by symbol and rejects BUY fills with conflicting owner origin/strategy. That protects against silent ownership merging, but it also means safe `MANUAL_LONG` plus `MANUAL_INTRADAY` exposure in the same symbol cannot be represented. A managed-exposure key must be frozen before controller work.
- PostgreSQL already persists append-only journal records and monotonic projection checkpoints. No-overnight state can be added as versioned journal events plus its own projection checkpoint; a separate mutable breach table is not required for correctness, though a query index/materialized view may be added for operations.
- `RuntimeComposition.create()` is the sole local construction root and already restores local-paper fills, positions, order states, and checkpoints before constructing command services. It is the correct place to restore the no-overnight projection, apply the durable admission latch, and construct/start the controller.
- `RuntimeComposition.close()` and FastAPI lifespan currently stop workers and close simulation/journal/provider. The no-overnight controller must be stopped before its command/journal dependencies, without treating process shutdown as a successful flat result.
- `ContinuousPaperStrategyController` is a process singleton built in `dashboard/server.py`; its existing strategy-local 13:25 flatten should be removed or delegated after the central controller is proven, otherwise two controllers can race to cancel/retry exits.
- Current Dashboard presents only automated-strategy state. A separate account-policy status surface is needed because `CONFIRMED_FLAT` and `OVERNIGHT_BREACH` apply across managed intraday owners, not one Strategy Set.
- Existing strategy runtime checkpoints are owner/pipeline-specific and cannot serve as the account-level durable breach latch.
- `SimulationService` currently stores one position per symbol and rejects a BUY from a different owner. It also validates SELL availability against the entire symbol position. Supporting a long and intraday slice in the same symbol therefore requires exposure-level accounting, not just another field on the projected position.
- `RiskSnapshot` is symbol-aggregate. A no-overnight SELL must be checked against managed available quantity (`managed_position - managed_pending_sell`) while aggregate account reconciliation independently proves that excluded holdings were not consumed.
- The existing RiskGate intentionally allows risk-reducing SELL through entry-only daily-loss and strategy-origin guards, but still requires market/data/book/tradability evidence. The central controller needs explicit admission state for BUY and must not weaken executable-book safety for SELL.
- Exact session-transition times have no dedicated configuration module. Add a typed no-overnight policy config loaded at composition, validated in strict order, with reviewed-calendar coverage and Asia/Taipei semantics.
- The current test suite already has deterministic clock, partial fill, cancel/retry, recovery, risk, API, singleton-construction, and optional PostgreSQL UAT seams. New lifecycle tests should extend these rather than build a parallel harness.
- PostgreSQL UAT is skipped unless `TEST_POSTGRES_DSN` is explicitly available; the plan must distinguish focused in-memory verification from required durable restart acceptance.
- The worktree contains broad unrelated modified/untracked files. Any later implementation must use an isolated branch/worktree or stage only an exact reviewed file list.
- A separate live-trading mode-switch plan is already defining account identity, execution mode, broker ambiguity, leases, and PostgreSQL-only broker mutation. This no-overnight plan must remain LOCAL_PAPER-first and expose ports compatible with those future contracts rather than prematurely creating broker tables/adapters.
- `/api/simulation/*` is an established LOCAL_PAPER-only namespace. The current plan may add Local Paper policy/status routes there; future account-bound B-plus-C hosting should use the separately planned `/api/portfolio/{account_id}/*` surface.
- The atomic-strategy architecture already freezes owner-bound `RISK_REDUCING_EXIT`, position availability, pending-exit checks, Journal durability, and recovery semantics. No-overnight must compose those contracts and add a policy owner/reason, not invent an alternate sell pipeline.
- Existing architecture explicitly prohibits a third market-data pipeline. Future watchdog hosting may own scheduling/lease/reconciliation, but must invoke the same canonical application service and consume canonical projections/events.
- Reuse the frozen atomic execution classification: `ENTRY_OR_INCREASE` versus owner-bound `RISK_REDUCING_EXIT`. Add no-overnight admission as a code-owned system policy that blocks only managed entry/increase; it must not bypass schema, ownership, available quantity, idempotency, Journal, instrument, transport, reconciliation, or executable-book checks.
- Preserve `TradeIntent -> Execution Policy -> ProposedOrderCommand -> Hard Risk -> ApprovedOrderCommand -> Adapter`. A session-flatten action is an operational/risk intent upstream of the same proposed-command boundary, not a direct simulator mutation.
- Extend position-lot ownership with stable `exposure_id`, `holding_horizon`, and `no_overnight_policy_id`; retain existing strategy lineage (`entry_run_id`, Strategy Set version, decision/intent identity). Orders and fills must carry the target exposure identity.
- `PortfolioProjection` remains fill-derived. `CONFIRMED_FLAT` must compare its managed-exposure projection with the authoritative local simulation state now, and later with normalized broker reconciliation; accepted/submitted orders never count as flatness.
- A future watchdog is a different host for the same controller/application ports. It must not own a new OrderApplicationService, market-data callback queue, Portfolio projection, or broker adapter.
- The final design uses orthogonal owner origin plus holding horizon and a stable exposure ID, rather than a free-form managed boolean. This preserves the requested AUTO_INTRADAY/MANUAL_INTRADAY scope while preventing contradictory origin/policy combinations.
- Ordinary cutoff blocks only managed intraday entry; an open overnight-breach latch blocks all exposure-increasing BUY until both authoritative resolution and operator acknowledgement are present.
- `CONFIRMED_FLAT` is an as-of Journal/reconciliation claim, not an irreversible terminal flag. A later non-duplicate fill supersedes it and opens a breach.
- B enforcing remains single-process Local Paper. Main-host death cannot be fully covered until C; shutdown with managed exposure is evidence, not flatness.

## Technical Decisions
| Decision | Rationale |
|----------|-----------|
| Ownership and holding horizon are policy inputs, not inferred from account-wide symbols | A symbol can contain unrelated long-term and intraday exposure; symbol-level liquidation is unsafe. |
| Use one canonical order-command path for strategy, manual, and no-overnight commands | Prevents bypassing RiskGate, journal, idempotency, simulation, and eventual broker adapters. |
| Make breach acknowledgement distinct from breach resolution | An operator acknowledgement must not fabricate flatness or reopen entry while managed exposure remains. |
| Use immutable `account_scope_id` and `policy_family_id`, with version/digest as a separate policy revision | Restart and policy rotation retain the same exposure/breach management lineage. |
| Use a B-specific PostgreSQL advisory-lock startup guard | It prevents duplicate ENFORCING compositions without claiming C's renewable lease, fencing, or HA behavior. |
| Exclude mutable planner input from semantic action identity | Two controllers observing different snapshots must still collide on the same exposure/chain/attempt before any handler side effect. |
| Re-evaluate server-owned execution eligibility immediately before the handler | A previously approved order cannot cross a market-phase or tradability boundary on stale evidence. |
| Split flat proof into NEVER_EXPOSED and FILL_DERIVED_CLOSE | Truly empty sessions can close cleanly, while any managed reduction remains fill-derived. |
| Accept release acknowledgement only after the latest revision is resolved | A stale acknowledgement cannot be reused after late fills or reconciliation changes. |

## Issues Encountered
| Issue | Resolution |
|-------|------------|
| Request Changes found six contract gaps in the first plan revision | Added Phase 6 and will revise the plan before any product implementation. |
| A repository search used unmatched shell globs for optional deployment files | Recorded the partial output and switched to `rg --files`/explicit file discovery instead of repeating the glob. |
| A double-quoted search pattern contained Markdown backticks and invoked shell command substitution | The search was read-only; subsequent checks use safely quoted fixed patterns without backticks. |

## Resources
- User attachment: `/Users/stevehuang-work/.codex/attachments/19f896f8-e461-4f03-ad98-f4599b33783f/pasted-text.txt`
- Repository: `/Users/stevehuang-work/Documents/tw_intraday_trader`
- Deliverable: `architecture/no_overnight_risk_controller_implementation_plan.md`
- Request Changes attachment: `/Users/stevehuang-work/.codex/attachments/03e4c1b0-92d7-4024-9164-bf87fbe2f072/pasted-text.txt`
