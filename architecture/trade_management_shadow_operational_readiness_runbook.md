# Trade Management Shadow Operational Readiness Runbook

Status: PR-TM-011 contract and drill procedure. This runbook does not authorize order creation,
SELL execution, broker integration, or real-money trading.

## 1. Purpose

Use finalized Live Shadow evidence to answer one question:

> Has the decision-only pipeline operated across enough complete real-market sessions, with durable
> evidence, replay parity, and demonstrated failure handling, to enter an execution-design discussion?

A `PASSED` validation report means only that the evidence gate passed. Both
`ShadowReadinessReport.execution_enabled` and `ShadowValidationReport.execution_enabled` remain
`false`.

## 2. Required evidence per market session

Before admitting a session to the extended validation set, record all of the following:

- unique Shadow `session_id` and Taiwan `market_date`;
- source class `LIVE_MARKET`;
- provider name, provider version, and connection-session identity;
- timezone-aware first and last coverage timestamps;
- finalized `ShadowOperationMetrics` with zero pending/lost evidence;
- replay parity `MATCHED`;
- durable Shadow projection digest;
- projection digest reconstructed from the finalized checkpoint.

The durable and recovered projection digests must match. Test fixtures and historical replay may be
used to test contracts, but they must be labelled `TEST_FIXTURE` or `HISTORICAL_REPLAY` and cannot
satisfy a live-production evidence policy.

## 3. Normal session procedure

1. Start an evidence-only Live Shadow Journal session with execution disabled.
2. Bind the canonical provider/version/connection identity before accepting the first event.
3. Freeze score, matched rules, typed entry evidence, strategy version, canonical timestamps, and the
   market-context digest through `LiveEntryDecisionBuilder`. Candidate/BuyScore do not construct the
   decision or Thesis directly.
4. Apply the reviewed `LiveThesisDraftPolicy` through `LiveTradeThesisDraftBuilder`; do not load a
   caller-authored Draft or active Thesis JSON.
5. Observe an existing local-paper BUY whose command already used the deterministic idempotency key
   returned by `paper_thesis_entry_idempotency_key(draft)`. C1 must never submit that BUY, create a
   fill, or simulate matching.
6. Activate the authoritative TradeThesis only from the observed Journaled fill. The fill must retain
   `fill_source=paper_simulation`, provider identity, and `execution_authority=false`.
7. Observe health, canonical backlog, evidence backlog, writer failures, and oldest pending ages.
8. If health becomes `BLOCKED`, follow the recovery procedure below; do not skip the failed event.
9. At the end of the market session, drain every admitted canonical message before finalization.
10. Finalize once, persist parity evidence and checkpoint, then rebuild the Shadow projection.
11. Compare durable and rebuilt projection digests. A mismatch is an incident, not a warning.
12. Create the immutable `ShadowValidationSession` only from the finalized evidence above.
13. Run the base readiness evaluator and extended validation evaluator over the complete session set.

Old `local_paper_fill.v1` records without explicit provenance remain valid for accounting recovery but
cannot activate a TradeThesis. SELL fills, mismatched symbols/sessions, fills before draft creation, and
fills whose command idempotency key is unrelated to the draft must fail closed.

## 4. Journal failure and recovery drill

The drill is successful only when all of these are observed and retained as evidence:

- the append failure was detected;
- the operation failed closed and did not process a later canonical message;
- the pending decision evidence remained available for retry;
- retry persisted the original evidence idempotently;
- checkpoint rebuild matched the durable projection;
- no decision evidence was lost or duplicated.

Record the result as `JOURNAL_RECOVERY`. A failed or missing required drill keeps the validation
report in `FAILED`.

## 5. Replay divergence drill

Use a controlled non-production copy of sealed session evidence. Introduce one explicit, traceable
input or expected-digest mismatch and verify:

- divergence is detected;
- the first divergent sequence is positive and reproducible;
- processing/qualification fails closed;
- the investigation identifies whether the mismatch is input, version, decision, or digest related;
- the original authoritative Journal is never edited to make replay pass.

Record the result as `PARITY_DIVERGENCE`. Never manufacture divergence in a live authoritative
session.

## 6. BLOCKED response

When the operation reports `BLOCKED`:

1. stop accepting downstream qualification of the session;
2. preserve the pending record and current Journal head;
3. classify the failure as decision, append, finalization, or checkpoint recovery;
4. repair only the external cause; do not mutate existing Journal history;
5. retry the idempotent operation;
6. verify projection/checkpoint digest equality;
7. retain the recovery duration and drill/incident evidence;
8. exclude the session if completeness or parity cannot be proven.

## 7. Divergence investigation

Start at `first_divergent_sequence` and compare, in order:

1. canonical event digest and ordering;
2. RiskSnapshot digest for that event;
3. strategy, thesis, exit, RiskGate, and validation policy versions;
4. ThesisEvaluation output;
5. ExitRecommendation output;
6. ExecutionEligibility output;
7. decision-chain and final projection digests.

Do not normalize, reorder, or rewrite evidence during investigation. A corrected engine or policy
must use a new version and a new validation run.

## 8. Gate interpretation

- `FAILED`: remain in decision-only Shadow, resolve typed reasons, and collect new evidence.
- `PASSED`: eligible only for a separately reviewed decision-to-command design discussion.
- Any report with `execution_enabled=true` is invalid by contract.
- No operator may translate a recommendation or validation report into an order through this runbook.

## 9. Current evidence status

Repository unit and regression tests verify the PR-TM-011 contracts and deterministic evaluator.
They do not prove that a real one-day or multi-day Shioaji Shadow session has occurred. Production
session collection, PostgreSQL smoke evidence, exporter/alerts, and any execution proposal remain
separate operational gates.

PR-TM-012 preflight on 2026-08-20 confirmed a successful data-only Shioaji 1.7.2 login with
`simulation=true`, `subscribe_trade=false`, and a clean logout. The probe ran after the regular market
session, so it is connection evidence only.

PR-TM-012A now defines authoritative Thesis activation from a provenance-bound local-paper BUY fill.
PR-TM-012B has also initialized the dedicated PostgreSQL Journal schema and added a provider-neutral
live callback runner. The runner accepts only an existing `PaperFillThesisActivation`, binds provider,
SDK version, simulation mode, and connection-session identity into the Journal session, and waits for
paired Tick/BidAsk ACK before opening the Shadow boundary. Events seen before ACK are counted but not
admitted. It does not create a Thesis, submit a paper fill, load a DSN, import Shioaji, or own any order
capability.

PR-TM-012B1 now supplies the missing pre-fill authority: a canonical, content-bound
`LiveEntryDecision` and a pure versioned Draft builder. CandidateEngine and BuyScoreEngine remain
unchanged; neither can create a Thesis. The new builders have no Journal, order, fill, activation,
RiskGate, Shadow, provider, or broker authority.

PR-TM-012B2 now supplies the operational composition from a content-bound EntryDecision and Draft to
an observed local-paper fill, the existing activation builder, live Shadow operation, and a separate
evidence Journal. It does not create a fill or order and does not grant execution authority.

No full market session, live recovery drill, cross-day evidence, or production gate pass has been
recorded. Production Shadow Gate remains `NOT_PASSED`.

## 10. PR-TM-012C0 pre-market procedure

Run from the repository root before the scheduled market open:

```bash
.venv/bin/python scripts/preflight_trade_management_shadow.py \
  --market-date 2026-08-21 \
  --session-id tm-shadow-20260821-2330 \
  --connection-session-id shioaji-20260821-tm-shadow-a \
  --symbol 2330 \
  --output research/trade_management_shadow/premarket_20260821.json
```

The command performs only:

- reviewed-calendar and complete-window validation;
- Shioaji data-only login/logout with `subscribe_trade=false`;
- PostgreSQL read-only verification of server version, migration registry, exact Journal tables, and
  zero evidence rows for the proposed Shadow `session_id`;
- fixture/historical rehearsal of replay, operational composition, Journal recovery, parity, and
  deterministic readiness contracts;
- a redacted manifest/report plus `.sha256` sidecar.

It must exit non-zero on any blocker. `--skip-provider-login` and `--skip-rehearsal` are diagnostic
options that intentionally produce a blocked artifact; they are not bypasses. Never point
`tests/test_postgres_journal.py` at the formal evidence DSN because that integration fixture drops the
Journal schema.

The reviewed C0 artifact for 2026-08-21 is:

```text
research/trade_management_shadow/premarket_20260821.json
report_digest=4e233ae941f9bef4d51752fb0ea6f33917fb25e31409c4ddf114bfdc89eda973
status=READY_FOR_SESSION
qualifying_real_session=false
production_shadow_gate=NOT_PASSED
```

`READY_FOR_SESSION` means only that the external dependencies and non-live rehearsals are ready for
the scheduled C1 collection. It is not live evidence and cannot advance the Production Shadow Gate.

## 11. TM-012C preflight blocking-fix evidence

The 2026-08-21 partial diagnostic exposed concurrent Tick/BidAsk callback delivery whose canonical
arrival order did not match the provider adapter's earlier observation order. The adapter now uses
one short shared market-callback ingress boundary for observation timestamp capture, provider
sequence assignment, event mapping, and canonical handler delivery. It does not clamp, increment, or
otherwise rewrite `received_at`; a genuine clock regression remains visible and fail-closed.

The separate rehearsal fixture now binds its envelope, payload, and test pipeline to the immutable
observed fill market date. Production event/session validation remains unchanged.

Post-fix evidence:

```text
research/trade_management_shadow/preflight_fix_validation_20260821.json
records/market_events/2026-08-21/tm-postfix-20260821-2330/
targeted ordering/replay/Shadow: 87 passed
full regression: 949 passed, 2 skipped
real postfix capture: 102 events, 0 rejected, FINALIZED
exact replay: MATCHED (10 repeats)
```

The postfix preflight has only `SESSION_WINDOW_NOT_FUTURE`; the prior rehearsal blocker is resolved.
The 60-second capture is market-data qualification evidence, not a complete Trade Management Shadow
session. Production Shadow Gate remains `NOT_PASSED`.

Review status:

```text
TM-012C-preflight-fix: APPROVED
Ingress Timestamp Gate: PASS
Rehearsal Fixture Gate: PASS
Real Stream Post-fix Diagnostic: PASS
Production Shadow Gate: NOT_PASSED
```

The next full-session qualification is conjunctive: the canonical session must be `FINALIZED`, lost
evidence must equal zero, at least one authoritative local-paper BUY fill must activate a thesis,
PostgreSQL evidence and checkpoints must reconstruct after restart, the controlled recovery digest
must match, and exact replay parity must be `MATCHED`. No successful gate can compensate for a failed
or missing gate. If the session has no authoritative BUY fill, record market-session qualification as
`PASS`, trade-lifecycle qualification as `INSUFFICIENT_EVIDENCE`, and keep the Production Shadow Gate
`NOT_PASSED`; never manufacture a fill or thesis to complete qualification.

## 12. PR-TM-012C1 executable session procedure

C1 uses `HistoricalQualificationCapture` as the only canonical market pipeline. Its immutable JSONL
Journal begins independently of any fill. The application coordinator observes only
`projection_applied` Tick results from that pipeline and creates `LiveTradeManagementShadowOperation`
only after `ExistingPaperFillObserver` sees one correlated local-paper BUY fill. A PostgreSQL append
failure closes market admission and leaves the market capture `INCOMPLETE`; no later event is sent to
Shadow.

Required pre-open inputs are reviewed artifacts, not values generated by C1:

```text
research/trade_management_shadow/session_inputs/YYYY-MM-DD/
  live_entry_decision.json
  trade_thesis_draft.json
  shadow_policy.json
  risk_snapshot.json
```

The EntryDecision and Draft use the existing versioned serialization envelopes. C1 derives the
`LiveThesisDraftPolicy` from the reviewed Draft and rebuilds it from the EntryDecision; unequal output
blocks before provider connection. The policy JSON supplies the reviewed `RiskPolicy` and Shadow
quantities. The RiskSnapshot JSON supplies read-only portfolio/risk evidence; canonical data health
and the regular-session market-open flag are rebound for each applied Tick.

Two distinct DSNs are mandatory:

- `LOCAL_PAPER_DATABASE_URL` is opened transaction read-only and is
  used only by `ExistingPaperFillObserver`;
- `TRADE_MANAGEMENT_SHADOW_DATABASE_URL` is a dedicated PostgreSQL database for immutable Shadow
  decisions and checkpoints.

C1 does not apply migrations. C0 must already have verified the dedicated database schema and the
proposed session scope. Run after C0 reports `READY_FOR_SESSION` and before 09:00:

```bash
.venv/bin/python scripts/run_trade_management_shadow_c1.py \
  --preflight-artifact research/trade_management_shadow/premarket_YYYYMMDD.json \
  --entry-decision research/trade_management_shadow/session_inputs/YYYY-MM-DD/live_entry_decision.json \
  --thesis-draft research/trade_management_shadow/session_inputs/YYYY-MM-DD/trade_thesis_draft.json \
  --shadow-policy research/trade_management_shadow/session_inputs/YYYY-MM-DD/shadow_policy.json \
  --risk-snapshot research/trade_management_shadow/session_inputs/YYYY-MM-DD/risk_snapshot.json \
  --connection-session-id tm-c1-YYYYMMDD-2330 \
  --output research/trade_management_shadow/c1_YYYYMMDD.json
```

The CLI verifies C0 digests and sidecar, current runtime source identity, reviewed trading date,
provider simulation identity, authority flags, session/symbol/policy bindings, distinct DSNs, and the
pre-open connection window before connecting to Shioaji. The output always retains
`production_shadow_gate=NOT_PASSED`. A complete no-fill day is
`INSUFFICIENT_EVIDENCE`; only an activated, full-coverage, zero-loss, replay-matched, recovered day is
`FINALIZED`, and that is still only one input to the existing multi-day policy.
