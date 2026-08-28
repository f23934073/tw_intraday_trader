# Findings: R6 Atomic Strategy Benchmark

## 2026-08-26 intake

- User explicitly authorized R6 work with a mandatory contract-first sequence.
- The research question is atomic-signal edge, not portfolio allocation or
  strategy-combination performance.
- All seven attempts must use the same Dataset, one-lot exposure, entry fill,
  session-close exit, costs, metrics, and decision thresholds.
- The seven hypotheses and parameters must be sealed before their results are
  observed; repeated tuning on this Dataset is prohibited.
- R5 v2 Replay acceptance proves the reusable one-lot replay integrity pattern,
  but it does not by itself define how new strategy signals are extracted or
  how seven attempts share one authoritative research family.
- R6 v1 is superseded. R6 revision 2 requires an independently reviewed
  contract before implementation or formal execution.

## 2026-08-26 authoritative design inventory

- Historical R6 v1 already named the seven remaining ENTRY hypotheses:
  `breakout_previous_high_entry`, `rolling_return_entry`,
  `volume_acceleration_entry`, `opening_range_breakout_entry`,
  `ema_crossover_entry`, `rsi_oversold_entry`, and
  `bollinger_lower_reentry_entry`.
- The deployed registry contains exactly these seven plus the rejected
  `above_vwap_entry`; R6 must not substitute legacy monolithic strategy IDs.
- Existing server-owned research-family policy remains
  `planned_attempts=20`, family alpha `0.05`, Bonferroni-adjusted alpha
  `0.0025`. The seven R6 hypotheses can occupy sealed sequences 1-7, while
  sequences 8-20 remain unavailable until a separately reviewed registration.
- Historical R6 v1 assumes a portfolio Backtest Run and cash-admission control.
  Revision 2 must instead use independent one-lot signal ledgers and must not
  use the R5 replay ID as a `baseline_run_id`.
- Current atomic Templates expose parameter defaults in code, but exact
  executable Strategy Versions and their durable parameter/implementation/
  Feature identities must be read from the authoritative Strategy Catalog
  before the matrix can be sealed.
- The current shell exposes no `BACKTEST_DATABASE_URL`, `DATABASE_URL`, or
  `POSTGRESQL_DSN`. Application PostgreSQL discovery therefore needs a
  read-only container inventory or another reviewed DSN handoff; no fallback
  SQLite authority is acceptable.

## 2026-08-26 application PostgreSQL inventory

- The authoritative application database is `tw_intraday_trader` in the local
  `tsg-single-db` PostgreSQL container. Discovery and schema inspection were
  read-only.
- Strategy Catalog authority is stored in `backtest.strategy_versions`,
  `strategy_version_state`, and `strategy_version_events`; R6 must bind the
  immutable Version row plus lifecycle projection evidence without changing
  lifecycle status.
- Existing experiment governance uses `backtest_experiment_families` and
  `backtest_experiment_attempts`. It already persists planned attempts, alpha,
  adjustment method, policy/comparability/definition digests, head sequence,
  research baseline digest, protocol identity, monotonic attempt sequence, and
  hypothesis ID.
- The existing family row still requires a `baseline_run_id`. R6 revision 2
  must define that field as a stable source/Dataset lineage anchor only, not as
  a portfolio performance comparator, and must bind the accepted R5 v2 replay
  separately in `research_baseline_digest`/protocol identity. A Replay ID must
  never be stored in `baseline_run_id`.

## 2026-08-26 exact Version inventory

- The authoritative Strategy Catalog currently has published immutable
  Versions for only three of the seven R6 hypotheses:
  - `rolling_return_entry` →
    `c95ade9e-09e2-443d-a6cd-40d576c07e6e`, parameters `2m / 1.5% /
    09:02-12:45`.
  - `rsi_oversold_entry` →
    `701483dc-6efe-446a-aa76-1b5526c07d07`, parameters `period 14 /
    threshold 30 / 09:15-12:45`.
  - `bollinger_lower_reentry_entry` →
    `9cc0c8e9-2e4f-4245-9307-533a1927bbfd`, parameters `period 10 /
    multiplier 2 / 09:20-12:45`.
- All three lifecycle projections are `PUBLISHED` at sequence 1. R6 research
  must not mutate those lifecycle states.
- No durable Version currently exists for `breakout_previous_high_entry`,
  `volume_acceleration_entry`, `opening_range_breakout_entry`, or
  `ema_crossover_entry`. Template identity alone is insufficient for an exact
  sealed hypothesis slot.
- Bollinger's published period `10` differs from its current Template default
  `20`; silently replacing it with the default would be a new hypothesis.
- Application PostgreSQL currently contains zero experiment families and zero
  experiment attempts, so no attempt budget has been consumed yet.
- G0 cannot seal seven exact Version IDs until the four missing Versions and
  the intended Bollinger hypothesis are explicitly resolved under Review. No
  Draft, Version, lifecycle event, family, slot, or Run was created by this
  inventory.

## 2026-08-26 common protocol lineage

- The only full formal source Run is
  `run-91ad87981676414da87b928398fa43c9`. Its `baseline_run_id` field is null;
  for R6 it can serve only as the immutable Dataset/cost/engine lineage anchor,
  not as a performance comparator.
- Common Dataset identity is
  `dataset-finmind-sponsor-sha256-88712fb2b5e7def4f87948f0e7c584d6b9fe89f87ebff0d5e214386ecbda37e6`,
  manifest digest
  `ced1e2d7c95f8f5bd402556b022eeecdf771deedd410e3319618b9d96a141b29`,
  payload SHA-256
  `216d306d2df5ec3f6221e6e96c3998129774c966f844e9d923634d96f275c31d`,
  binding revision 1.
- Common execution economics are one lot (`1000` shares), next observed
  same-symbol Kbar open, `5` bps per side slippage, commission `0.001425`, sell
  tax `0.003`, and `end_of_day_exit_v1` session-close exit.
- Common engine lineage is `backtest-engine-v2`; R6's signal-level replay must
  preserve the accepted R5 v2 cost and matching identities rather than invoke
  shared cash/equity sizing.
- The Dataset amount contract is a derived close-times-volume proxy. It is
  relevant to the rejected VWAP strategy but the seven R6 strategies do not
  request VWAP; the Dataset identity and amount contract still remain in the
  shared protocol snapshot for comparability/audit.
- Existing Strategy Sets are test/research combinations or the one-member VWAP
  set. None is a valid exact one-member set for the seven R6 slots. G0 must
  decide whether R6 persists one-member sets or seals Version identities
  directly in its research matrix; it must not reuse multi-member test sets.

## 2026-08-26 G0 Version-resolution decision

- R6 will seal immutable Strategy Version identities directly; it will not
  create redundant one-member Strategy Sets because aggregation has no role in
  a single-signal replay and would add an unrelated identity layer.
- The already-published Bollinger hypothesis remains period `10`, multiplier
  `2`, `09:20-12:45`. The current Template default of period `20` is a distinct
  untested hypothesis and is excluded from this seven-slot family.
- The published rolling-return and RSI Versions are reused exactly as stored.
- The four missing Version IDs must be created from the G0-frozen current
  Template defaults only after independent G0 approval. Publishing them is a
  prerequisite for sealing the durable family matrix, not part of G0 design.
- No new Draft, Version, lifecycle event, Strategy Set, family, attempt, Run,
  or Replay has been created while making this decision.

## 2026-08-26 qualification boundary

- The FinMind current-snapshot Dataset is explicitly
  `research_eligible=false`; R6 can rank exploratory signal evidence but cannot
  produce lifecycle promotion eligibility from this Dataset.
- Existing Backtest Qualification is a baseline-versus-challenger portfolio
  contract and is not directly reusable as an absolute one-lot atomic-signal
  edge test. In particular, rejected VWAP performance must not become the
  comparator that makes another losing signal look acceptable.
- R6 therefore requires one frozen absolute screening contract shared by all
  seven slots. Multiple testing remains server-owned: family alpha `0.05`,
  planned attempts `20`, Bonferroni alpha `0.0025`, with exactly slots 1-7
  available in this revision.
- Any outcome is a research disposition only. `PASS_EXPLORATORY_SCREEN` cannot
  mutate Strategy Version lifecycle or authorize Local Paper; promotion would
  require a future point-in-time, research-eligible Dataset and a separately
  reviewed Qualification protocol.

## 2026-08-26 G0 contract result

- The G0 Review candidate freezes seven slots and uses absolute zero-edge
  screening; rejected VWAP is provenance only and cannot be a comparator.
- Signal semantics are `FIRST_TRIGGER_PER_SYMBOL_SESSION`, matching the
  existing Backtest engine's `entered_today` boundary. All episodes use 1,000
  shares, next observed same-session symbol open, same-session terminal close,
  and one common cost identity with no shared cash/equity.
- Existing Run-backed experiment attempts cannot model replay attempts without
  fake Run rows. R6 therefore uses a dedicated bounded context and PostgreSQL
  family ledger with the same server-owned 20-attempt/Bonferroni policy.
- All seven new ledgers are sealed before any result is created; all seven
  results remain redacted until the matrix reaches seven accepted attempts.
- The exploratory Dataset prevents lifecycle promotion regardless of result.
- G0 remains `NOT PASSED` until an independent Review accepts the candidate;
  no Version publication, migration, family, preflight, or replay is allowed
  before that decision.

## 2026-08-26 independent G0 Review findings

- G0 received `REQUEST CHANGES / CONTRACT NOT FROZEN`; formal Replay remains
  `0/7` and G1-G5 remain unauthorized.
- The initial identity graph was circular: `hypothesis_id` depended on a common
  protocol that depended on slot registrations, while slot registrations
  depended on the hypothesis identity. Open-ended `at minimum` projections
  also made the resulting digests implementation-dependent.
- The remediation must use exact, non-circular stages:
  `protocol_core_digest -> hypothesis_spec_digest -> G1 Version binding and
  hypothesis_id -> ordered slot digests -> matrix_id and registration_digest
  -> artifacts`. G0 can freeze hypothesis specifications for all seven slots
  even though four final Version IDs do not exist until G1.
- The initial attempt contract consumed FAILED/CANCELLED slots without a legal
  recovery transition. R6 will retain one attempt ID, sequence, hypothesis,
  and budget allocation while allowing only CAS-guarded technical retry
  generations; a retry never appends another attempt or exposes a result.
- Artifact `created_at` was immutable-digest input without a replayable source.
  Wall-clock and actor audit data must remain durable PostgreSQL operation
  evidence but must not affect any semantic artifact bytes or digest.
- API-only redaction was insufficient because filesystem artifacts, CLI output,
  logs, and exceptions could expose individual performance before the 7/7
  barrier. Pre-release result evidence must remain in a quarantined persistence
  boundary with no public artifact locator; every product reader must share one
  family release gate.
- The statistical contract itself passed Review: Bonferroni alpha, bootstrap
  index, zero-edge comparator, no pairwise-winner claim, quarter handling,
  Profit Factor special values, Dataset identity, and exploratory-only boundary
  require no semantic change in this remediation.

## 2026-08-26 G0 remediation result

- Identity is now an exact acyclic chain. Frozen values include
  `research_baseline_digest=75f9efda...d4543`,
  `protocol_core_digest=1cdd8bf6...4ac1`, and seven concrete G0
  `hypothesis_spec_digest` values. Final hypothesis/slot/matrix IDs are derived
  only after G1 supplies the four missing Version bindings and the benchmark
  implementation binding.
- Every exact identity projection has a closed key set and canonical scalar
  types. Algorithm and cost contract projections are explicit; actor, note,
  key, locator, and wall-clock audit cannot feed semantic identity.
- Technical recovery is same-attempt only. Status/revision CAS, a four-generation
  ceiling, fixed retryable error-code allowlist, immutable input identity, and
  permanent final failure prevent retries from adding hypotheses or resetting
  the 20-attempt family budget.
- G4 performance evidence is quarantined in PostgreSQL and has no filesystem
  artifact/catalog locator before seven accepted attempts. All product paths
  use one `BenchmarkResultReader`; CLI/log/error/outbox projections are redacted.
  Release materializes one all-seven bundle only after the database proves the
  7/7 condition.
- Artifact/manifests/postflights contain no timestamps. Different-clock rebuild
  must produce byte-identical roots; audit time remains durable operation data.

## 2026-08-26 second independent G0 Review findings

- G0 remains `REQUEST CHANGES / CONTRACT NOT FROZEN`; formal Replay remains
  `0/7` and G1-G5 remain unauthorized.
- The generation-4 prose requires `RUNNING -> FAILED_FINAL` and
  `CANCELLING -> CANCELLED_FINAL`, but the exact transition table omitted both
  while declaring every omitted transition illegal. The table must include
  both with exact generation and error-code guards.
- The public bundle manifest names `bundle_payload_sha256` without defining
  the included paths, per-slot/chunk order, chunk boundaries, file framing, or
  exact concatenated hash input. A clean-root/response-loss rebuild therefore
  cannot yet independently reproduce the claimed payload bytes.
- The reviewer independently confirmed that the baseline, protocol, and seven
  hypothesis-spec digests rebuild exactly; the non-circular identity, clock
  exclusion, PostgreSQL quarantine, unified reader, and 7/7 release boundary
  require no semantic redesign in this remediation.

## 2026-08-26 second G0 remediation result

- The legal transition table now explicitly contains generation-4
  `RUNNING -> FAILED_FINAL` for retryable infrastructure codes and
  `CANCELLING -> CANCELLED_FINAL` for `OPERATOR_CANCELLED`.
- All transition rows have an exact generation guard and outcome-code guard.
  Infrastructure, integrity, cancellation, accepted, operator-seal, and
  unclassified codes now map to one deterministic terminal/retryable status;
  requests cannot reclassify them.
- Public payload membership is exact: seven ordered slot directories, one
  result manifest and postflight per slot, plus zero or more 10,000-row episode
  JSONL chunks with fixed names/boundaries and descriptor SHA/count evidence.
- `bundle_payload_sha256` now hashes path-length, UTF-8 path, content-length,
  and exact content frames using fixed-width big-endian integers. Member order,
  file bytes, LF rules, zero-episode behavior, clean-root reconstruction, and
  response-loss parity are frozen.
- A framing golden vector independently fixes path/content lengths, frame hex,
  and SHA-256, eliminating endian/framing interpretation differences.

## 2026-08-26 independent G0 approval

- Independent Review found no remaining finding and approved
  `R6 G0: APPROVED / CONTRACT FROZEN`.
- Generation-4 transitions, guards, and outcome-code mapping are accepted as
  deterministic and fail closed.
- Public-bundle members, chunk boundaries, canonical bytes, binary framing,
  and SHA-256 input are accepted as exact and independently reproducible.
- G1 alone is authorized: publish the four missing immutable Versions and
  implement pure domain/artifact primitives. PostgreSQL family/matrix state,
  full-Dataset scanning, formal Replay, Local Paper, broker, and real-money
  execution remain unauthorized.

## 2026-08-26 G1 durable evidence

- Newly published exact Version IDs are slot 1
  `ecbfe315-0a0c-400c-9005-d33bb1db7e62`, slot 3
  `f309ccc7-c181-4e69-a0b2-2ec53d48f008`, slot 4
  `1460fd64-37c3-4bc6-a2d1-53e89fc5f3b6`, and slot 5
  `31c55c80-ab96-4f81-8d5c-ed1c57ec471d`.
- Each new Version is number `1`, status `PUBLISHED`, lifecycle sequence `1`,
  and exactly matches its G0 configuration, Template, parameter schema,
  implementation, Feature Request, Feature Specification, Feature
  implementation, and runtime identity digests.
- Read-only replay reconstructed exact binding and slot roots for all seven
  slots. The complete values and four durable operation/result roots are
  recorded in Sections 3.3-3.4 of the implementation plan.
- No Strategy Set, R6 family, matrix, attempt, Dataset scan, replay result,
  Local Paper activation, provider call, broker call, or real-money path was
  created or invoked.

## 2026-08-26 independent G1 Review findings

- G1 received `REQUEST CHANGES`; G2-G5 and formal Replay remain unauthorized.
- The public bundle verifier trusted self-consistent outer member lengths and
  hashes without parsing and semantically rebuilding result, postflight, and
  episode members against the sealed family release roots.
- Postflight evidence construction used truthiness conversion. String and
  numeric aliases could therefore claim Dataset, lifecycle, EOF, or external-
  call verification instead of being rejected as non-boolean inputs.
- Durable Version replay trusted saved configuration/projection digests rather
  than rebuilding the immutable Version columns, publish event, actor, and
  operation result evidence from PostgreSQL.
- Daily equal-signal return was compounded before the frozen 18-decimal
  `ROUND_HALF_EVEN` quantization step, creating a disposition-boundary risk.

## 2026-08-26 G1 Review remediation result

- Public-bundle verification now requires the sealed family release and
  semantically rebuilds every canonical result manifest, postflight, and
  episode row. It checks lineage, multiplicity, summary, payload SHA, and all
  result/postflight roots against the ordered accepted attempts; recalculating
  only outer descriptors and hashes cannot legitimize inner tampering.
- Postflight construction requires exact booleans for source EOF, Dataset,
  lifecycle, and no-external-call evidence. String, integer, Decimal, and other
  truthy/falsy aliases fail closed before any acceptance condition is built.
- The G1 publisher now reconstructs the stored Template, immutable Version,
  sealed Draft, lifecycle event/projection, publish request/result operation,
  and lifecycle outbox. The four new publications additionally bind the frozen
  actor, actor session, change note, and initial Draft revision.
- PostgreSQL tamper regressions cover self-consistent Version parameters,
  lifecycle actor, and publish operation result roots. The existing RSI Draft
  is correctly verified through its historical `expected revision + 1`
  invariant instead of an invalid fixed revision assumption.
- Daily equal-signal returns are quantized to scale 18 using
  `ROUND_HALF_EVEN` before compounding wealth. A threshold-boundary golden test
  fixes the resulting drawdown at exactly `0.2`.
- G1 is a re-review candidate only. No family, matrix, attempt, full-Dataset
  scan, formal replay, Local Paper, provider, broker, or real-money path was
  opened.

## 2026-08-26 second independent G1 Review findings

- G1 remains `REQUEST CHANGES`; G2-G5 and formal Replay remain unauthorized.
- Bundle verification checks concatenated episode bytes and canonical sequence
  continuity but does not compare each physical chunk's parsed row count and
  first/last sequence to its descriptor. A 10,001-row payload can therefore be
  repartitioned from `10000/1` to `9999/2` after rebuilding outer hashes.
- Daily returns are now correctly quantized before compounding, but the
  disposition compares the raw maximum drawdown while the summary serializes
  its 18-decimal quantization. One value just above `0.20` can serialize as
  `0.20` while being rejected by the raw comparison.

## 2026-08-26 second G1 Review remediation result

- Bundle verification now retains the parsed rows for every physical chunk and
  compares actual count plus first/last sequence with that chunk's descriptor.
  Every non-final chunk must physically contain exactly 10,000 rows.
- The Reviewer's 10,001-row `9,999 / 2` repartition probe is preserved as an
  integration regression: only chunk byte counts/SHA, framed payload SHA, and
  manifest digest are rebuilt while the sealed release stays unchanged, and
  verification fails closed.
- Summary construction quantizes maximum drawdown once to its canonical
  18-decimal `ROUND_HALF_EVEN` value. The disposition threshold and serialized
  metric use that same value.
- The boundary probe `0.200000000000000000400012` now serializes as `0.2` and
  is compared as `0.2`, eliminating contradictory pass/reject evidence.
- G1 remains a re-review candidate only. No G2 family/matrix work or formal
  Replay was opened.

## 2026-08-26 independent G1 approval

- Independent Review found no remaining finding and approved
  `R6 G1: PASSED`.
- The reviewer confirmed fail-closed `9,999 / 2` physical chunk repartition,
  actual per-chunk row/sequence/10,000-boundary verification, and one canonical
  drawdown shared by disposition and summary.
- Reviewer evidence is `2 passed` for the exact probes, `33 passed, 4 skipped`
  for G1 core, and `1659 passed, 65 skipped` for the current full no-DSN
  worktree; framework-free domain/artifact dependency direction remains intact.
- G1 approval only removes G2's prerequisite blocker. G2 is ready for a
  separate authorization but is not started; G3-G5, formal Replay, Local Paper,
  broker, and real-money execution remain unauthorized.

## 2026-08-26 G2 implementation findings

- Migration 016 was free and is now the authoritative PostgreSQL-only R6
  persistence owner. It does not reuse fake Backtest Runs or the R5 replay
  ledger for benchmark attempts.
- The stable family ID is independent of replaceable implementation bytes;
  implementation and Migration 016 byte digests enter the revision-1 matrix
  build binding, so code drift cannot reset the twenty-attempt family budget.
- Matrix seal revalidates the complete frozen G1 Version/configuration,
  lifecycle event/projection, publish result, and outbox roots in the same
  transaction before inserting family, matrix, seven slots, operation, release
  placeholder, and outbox.
- Attempt mutations use the family lock plus exact status/revision/generation
  guards. Retry preserves the same attempt/slot/head identity; cancellation
  preserves the greatest durable progress; final non-accepted status blocks
  family release.
- Same-key replay is rebound to the stored request and durable matrix/attempt
  scope. Same-key/different-digest, second matrix revision, self-consistent
  operation-result tamper, matrix/slot projection tamper, lifecycle tamper, and
  concurrent head consumption fail closed.
- Performance publication remains unavailable in G2. An `ACCEPTED` transition
  requires the future G4 postflight/quarantine use case, and all pre-release
  product reads are redacted.

## 2026-08-26 independent G2 Review and remediation findings

- Independent Review returned `REQUEST CHANGES` with four P1 boundaries:
  transition replay trusted a self-consistent mutable result, redacted
  diagnostics accepted arbitrary strings, matrix seal rebuilt only part of the
  G1 publication graph, and the application caller selected failure outcome.
- Transition outbox rows now contain one exact canonical operation-result
  projection. Replay verifies the immutable request, operation result, outbox
  payload, matrix/attempt scope, transition state machine, revisions,
  generations, outcome, and monotonic progress before returning the historical
  result. Synchronized result/outbox substitution is rejected by the original
  request projection.
- Diagnostic codes now use one exact server-owned allowlist. Migration 016
  enforces JSON array/type/membership/uniqueness at write time, while the public
  redacted reader independently revalidates the same list and rejects any
  observed-value string.
- Matrix seal now performs the complete G1 durable rebuild: current and stored
  Template roots, canonical parameters/configuration, sealed Draft body and
  revision, Version, publish request, lifecycle event/projection, publish
  operation result, lifecycle outbox, and the four new publications' frozen
  actor/session/change note.
- The application no longer exposes a generic transition command. Explicit
  cancel/complete/retry/seal commands own operator transitions, and exact
  exception types map server-side to retryable infrastructure, final integrity,
  or unclassified failure outcomes.
- PostgreSQL adversarial coverage includes synchronized transition result plus
  outbox tamper, diagnostic write/read injection, self-consistent G1 actor graph
  substitution, and integrity-to-retryable substitution.
- G2 is a remediation/re-review candidate only. Formal progress remains
  `33.3%`; G3-G5, full-Dataset preflight, formal Replay, Local Paper, provider,
  broker, and real-money execution remain unauthorized.

## 2026-08-26 second independent G2 Review and progress remediation

- Independent re-review closed the diagnostic allowlist, complete G1 graph,
  and server-owned failure classification findings, but reproduced one
  progress-only response-loss substitution.
- A cancellation whose request progress is null preserved durable progress
  `0.300000`; synchronously changing only operation result and outbox progress
  to `0.900000` was accepted because replay copied progress from the result it
  was supposed to verify.
- Transition progress now has an independent transaction-local CAS projection
  keyed by operation and target attempt revision. It preserves from/requested/
  result progress plus status, generation, outcome, request digest, and result
  digest.
- Replay reconstructs canonical progress from this evidence and compares the
  operation result and outbox against it. Neither mutable outer projection is
  an authority for historical progress.
- The exact progress-only regression now fails closed with
  `R6_IDEMPOTENCY_CONFLICT`. G2 remains a re-review candidate only; formal
  progress stays `33.3%` and G3-G5 remain unauthorized.

## 2026-08-26 independent G2 approval

- Independent Review found no remaining finding and approved `R6 G2: PASSED`.
- The reviewer independently reproduced the `0.300000 -> 0.900000`
  progress-only substitution and confirmed `R6_IDEMPOTENCY_CONFLICT`.
- Transition evidence, mutation, operation, and outbox share one transaction;
  missing evidence, field drift, or digest drift fails closed.
- Formal progress advances to `50%`. G3 is separately authorized but not
  started; G4-G5, formal Replay, Local Paper, provider, broker, and real-money
  execution remain unauthorized.

## 2026-08-26 G3 implementation intake

- G2 was committed independently as `7b7ec7c`; unrelated shared-worktree files
  and `.planning/.active_plan` were excluded.
- G3 must evaluate all seven exact Versions against the same ordered 28,325,340
  bar stream with isolated Feature/runtime state, first-trigger-only admission,
  and same-session next-bar/session-close matching.
- G3 may publish only non-performance ledger/match artifacts and one all-or-none
  durable preflight root. It must not create attempts, advance family head,
  calculate episodes/metrics, or expose any performance projection.
- The existing pure domain already owns canonical ledger rows, bounded
  first-trigger admission, match rows, manifests, and parity primitives. G3
  should compose these rather than create a second strategy or matching formula.
- The existing `AtomicBacktestStrategyAdapter` already binds exact Version,
  Template, parameter schema, implementation, Feature Request, and isolated
  `CompletedOneMinuteKbarFeatureAdapter` state. G3 can instantiate one adapter
  per slot and reuse its strategy/Feature formulas.
- `HistoricalDatasetCatalog.iter_bars_ordered()` verifies count/checksum but
  exposes parsed bars, not exact source JSONL bytes. G3 needs a narrow canonical
  source reader over the immutable `bars.jsonl` so every ledger/match source
  digest is bound to the actual payload bytes while the overall line/SHA/EOF
  evidence is computed once.
- Match construction can remain one-pass: promote a waiting signal on the next
  later same-symbol bar, update active matches only on subsequent bars, then use
  the last later bar at session close. This reproduces `build_match_plan`
  without seven full Dataset rescans.
- Migration `017` is currently free. An all-or-none G3 preflight registration
  can be added without rewriting the already approved Migration 016 schema.

## 2026-08-26 G3 formal preflight failure evidence

- The one-pass G3 candidate composes seven isolated exact-Version runtimes over
  the canonical Dataset stream and keeps ledger/match publication atomic. It
  does not calculate episodes, costs, P&L, metrics, or disposition.
- The application PostgreSQL was idempotently prepared with the approved
  Migration 016 and sealed matrix. The matrix remains at family head `0` with
  zero attempts; this is a G2 prerequisite, not a G3 attempt mutation.
- The first formal execution failed closed at the first session boundary. The
  initial error was `G3 match sequence drift`; a regression showed that the
  actual condition was an omitted match caused by incomplete coverage, not an
  ordering race.
- The fail-fast replay identifies exact slot `1`
  (`breakout_previous_high_entry`, Version
  `ecbfe315-0a0c-400c-9005-d33bb1db7e62`) and signal sequence `101`: the signal
  obtains a later same-session entry bar, but that entry is already the final
  observed bar for the symbol/session, so no strictly later terminal exit bar
  exists.
- Section 5 requires every admitted signal to have both a later same-session
  entry and a still-later same-session exit. The candidate therefore must not
  skip the signal, invent an exit, carry it overnight, publish partial
  artifacts, or enter G4.
- Both formal executions exited non-zero. The preflight root contains no final
  artifact, and no R6 attempt, episode, metric, comparison, Local Paper,
  provider, broker, or real-money state was created.
- This is a frozen-contract versus observed-signal boundary, not authority to
  revise the contract. G3 remains formally blocked pending independent Review
  and an explicit contract-remediation decision.

## 2026-08-26 G0 Amendment A1 contract analysis

- All seven exact Versions already enforce an end-exclusive entry window no
  later than `12:45`; ORB ends at `11:00`. The G3 failure is therefore not a
  late-afternoon trigger and must not be remediated by a `13:28` cutoff.
- The rejected slot-1 signal had a later entry but no still-later exit because
  its symbol/session lacked a complete tail. Skipping only that signal would
  create a strategy-dependent universe and invalidate the seven-slot fairness
  claim.
- Amendment A1 uses one Dataset-only eligibility mask shared by every slot.
  Exact `12:45` and `13:30` Kbars are required before any strategy signal is
  admitted. The rule consults timestamp existence only, never price, Feature,
  return, P&L, or strategy outcome.
- The `12:45` anchor guarantees a next observed entry no later than the common
  deadline for any signal produced before the end-exclusive cutoff. The exact
  `13:30` anchor supplies a strictly later terminal exit. Overnight, same-bar,
  last-partial-bar, and synthetic exits remain prohibited.
- Missing anchors produce a common excluded symbol/session with exact reason
  codes. Duplicate anchors remain Dataset corruption. Eligible coverage must
  be at least `0.950000000000000000` after 18-place `ROUND_HALF_EVEN`.
- The common mask is an explicit canonical artifact bound into all seven
  ledger/match/result/postflight roots. An admitted incomplete signal still
  fails closed and cannot be reclassified as Dataset exclusion.
- The amended protocol core digest is
  `a4d645b5ea59fca5a90a00c9e14ca117366d87e4f310b88354fc73d03272f471`;
  the amended algorithm contract digest is
  `d0d3b66395a06f600c698bad7890ad39f2dceec2963727814e5d3198643df0b6`.
  Exact per-slot downstream roots are frozen in Section 14 of the main plan.
- The stable research family and 20-attempt budget remain unchanged. Matrix
  revision 1 stays immutable with head/attempt zero. A reviewed Migration 017
  is required to admit matrix revision 2 because Migration 016 currently
  hard-codes revision 1 and uniqueness by `(family_id, slot_sequence)`.
- This is a contract-only candidate. No product code, migration, database row,
  matrix, attempt, artifact, provider, broker, Local Paper, or lifecycle state
  was changed.

## 2026-08-26 G0 Amendment A1 independent Review remediation

- Independent Review accepted the common `12:45`/`13:30` eligibility concept
  and all candidate identity roots, but returned `REQUEST CHANGES` for two P1
  persistence gaps and one P2 runtime-state ambiguity.
- The first P1 was that a filesystem G3 root had no exact top-level member
  contract, durable PostgreSQL acceptance registration, response-loss mapping,
  or mandatory G4 admission precondition.
- The second P1 was that removing `UNIQUE(family_id, slot_sequence)` would leave
  attempt `matrix_id` and `hypothesis_id` as independent foreign keys, allowing
  a revision-2 attempt to reference a revision-1 hypothesis.
- The P2 was that excluded sessions had no frozen effect on source-only
  previous-close evidence versus strategy/Feature runtime state.
- Remediation freezes an exact 31-file root, v2 preflight and slot-root schemas,
  one immutable accepted-preflight aggregate, transactional operation/outbox,
  and an exact accepted-preflight requirement before family-head mutation.
- Migration 017 now requires composite matrix/family/revision,
  matrix/family/slot/hypothesis, and preflight/matrix constraints. Attempts
  cannot cross-bind a matrix revision, slot, hypothesis, family, or preflight.
- A further schema audit found that `protocol_core` currently lives on the
  family. Because A1 changes its digest, overwriting that row would destroy
  revision-1 reconstruction. This first remediation proposed protocol columns
  on each matrix and a revision-1 backfill; the next re-review section records
  why that proposal was superseded by an additive companion table.
- Revision-2 activation now has an exact request/result schema, expected active
  revision/head/attempt preconditions, one CAS transaction, complete revision-1
  and G1 publication rebuild, and operation/outbox replay behavior.
- Excluded rows still count toward Dataset count/SHA/EOF/order and the
  source-only previous-close map. They never enter strategy/Feature runtime,
  evaluation, signal, or match evidence.
- The remediation changes only planning/Review documents. Migration 017,
  product/tests, matrix revision 2, PostgreSQL, G3, attempts, and trading paths
  remain untouched and unauthorized pending independent re-review.

## 2026-08-26 G0 Amendment A1 second re-review remediation

- Independent re-review found that the first remediation simultaneously
  prohibited revision-1 row mutation and required protocol columns to be
  backfilled into the revision-1 matrix row. Those requirements could not both
  be implemented.
- Migration 017 now uses the additive
  `atomic_entry_benchmark_matrix_protocols` companion table. It inserts one
  fully rebuilt revision-1 projection without updating/deleting any existing
  revision-1 row; revision 2 inserts its own companion row transactionally.
- The companion is keyed and constrained by exact matrix/family/revision
  identity. The family protocol remains immutable revision-1 inception evidence,
  and all active reads fail closed unless the selected matrix has its exact
  canonical companion projection.
- Eligibility anchor lineage now defines the precise digest input as the exact
  canonical Dataset source JSON object bytes excluding the JSONL LF. Timestamp
  serialization, full `HistoricalBar` round-trip equality, and invalid
  LF/reformatted/reduced projections are also frozen.
- These contract clarifications do not change the already recomputed A1
  protocol, hypothesis, Version-binding, hypothesis, slot, or algorithm roots.
  A1 remains not frozen pending another independent re-review.

## 2026-08-26 G0 Amendment A1 third re-review remediation

- The third independent re-review confirmed the companion-table and anchor-byte
  findings closed, but found one PostgreSQL DDL blocker: the contract required
  operation, outbox, and slot `(matrix_id, family_id)` foreign keys without an
  exact two-column referenced unique key.
- Migration 017 now requires matrices to own both
  `UNIQUE (matrix_id, family_id)` and
  `UNIQUE (matrix_id, family_id, matrix_revision)`. The pair backs operation,
  outbox, and slot relationships; the triple separately backs protocol,
  release, and preflight relationships.
- The acceptance matrix now requires PostgreSQL catalog proof of both keys and
  negative inserts that substitute a foreign family across the two-column
  operation/outbox/slot boundary. Cross-revision triple substitutions remain
  independently rejected.
- This is contract-only remediation. It does not create Migration 017, mutate
  PostgreSQL, activate matrix revision 2, rerun G3, or change any identity root.
  A1 remains `RE-REVIEW REQUIRED / NOT FROZEN` pending independent approval.

## 2026-08-26 G0 Amendment A1 autonomous review cycle 1

- The next adversarial pass found an activation-boundary ambiguity: the
  migration list prohibited every family-row update while the later activation
  contract required a family `active_matrix_revision` CAS.
- The contract now separates those operations. Migration 017 performs schema
  and additive revision-1 companion work without changing the family. The
  separately invoked activation transaction may update only
  `active_matrix_revision: 1 -> 2` and operational `updated_at`, with an exact
  affected-row count of one.
- Activation must compare canonical before/after family projections and roll
  back if source lineage, baseline/protocol inception evidence, attempt policy,
  head, release state, actor, or creation time changes.
- The clarification does not change any frozen A1 identity root and does not
  authorize migration, activation, PostgreSQL mutation, or G3 execution.

## 2026-08-26 G0 Amendment A1 autonomous review cycle 2

- Schema-to-contract comparison found that merely saying revision 2 is
  permitted did not freeze replacements for the existing matrix/release
  `matrix_revision=1` checks or constrain the family active revision. The
  amended DDL contract now permits exactly revisions 1 and 2 and rejects every
  other value at PostgreSQL.
- Existing operation/outbox `matrix_id` columns are nullable, so a composite
  pair foreign key alone could be bypassed. Migration 017 must first verify all
  historical values, then set them non-null and bind outbox to the exact
  operation matrix/family aggregate.
- `atomic_entry_benchmark_transition_evidence` and attempt-bound operation/
  outbox rows previously retained independent attempt references. The contract
  now adds an exact `(attempt_id, family_id, matrix_id)` target and requires all
  three paths to reference it when an attempt is present.
- These changes close database substitution paths only; they do not change A1
  research identity roots or authorize Migration 017/G3.

## 2026-08-26 G0 Amendment A1 autonomous review cycle 3

- Concurrency review found that validating head/attempt zero before DDL was not
  enough unless Migration 017 held the same family-row serialization boundary
  used by attempt admission and activation.
- The migration must now acquire `SELECT ... FOR UPDATE` on the exact family
  before reading mutable preconditions and retain it through schema validation
  and commit. Activation, preflight registration, and attempt start are all
  required to acquire that row before family-owned mutation.
- A concurrent old-revision attempt either commits first and makes migration
  preflight reject, or waits behind migration and then fails the superseded
  revision/preflight contract. Both operations can never observe and consume
  the same zero-attempt state.

## 2026-08-26 G0 Amendment A1 autonomous review cycle 4

- Identity review found that G3 saved `preflight_implementation_digest` in its
  manifest but the matrix build binding did not seal an authoritative expected
  value. A different runtime could therefore self-declare a new implementation
  digest during publication.
- The A1 build binding now advances to schema v2 and includes the preflight
  implementation digest. Its exact source manifest freezes three ordered paths,
  canonical row/body schemas, byte counts, and SHA values.
- Persistence identity is now an exact ordered two-file source manifest for
  Migration 016 and future Migration 017 rather than an undefined
  concatenation. Algorithm identity retains the six-file Section 3.5 manifest.
- Matrix activation, G3 publication, PostgreSQL preflight registration, and G4
  admission all rebuild and compare the sealed digests. Matrix/build IDs remain
  intentionally unfrozen until reviewed implementation bytes exist; upstream
  protocol and hypothesis roots do not change.

## 2026-08-26 G0 Amendment A1 autonomous final review

- No Blocking or Important finding remains after four autonomous adversarial
  review/remediation cycles.
- Independent reconstruction matched the frozen protocol root, seven
  hypothesis-spec digests, seven Version-binding digests, seven hypothesis IDs,
  seven slot digests, and algorithm-contract root.
- The final contract closes database aggregate substitution, family-row
  serialization, revision-CAS, build-binding, source-manifest, and preflight
  implementation-identity gaps without changing the research semantics.
- Disposition: `PASSED / CONTRACT FROZEN`.
- This disposition does not authorize Migration 017, matrix revision 2,
  PostgreSQL mutation, G3 execution, Local Paper, provider, broker, or
  real-money work.

## 2026-08-26 A1 implementation intake

- User explicitly authorized the next phase after scoped A1 commit `ec41932`.
- Migration 016 is revision-1-only: matrix/release checks require revision 1,
  family active revision is nullable, slots are unique by family/sequence, and
  operation/outbox/attempt references are not yet aggregate-safe across matrix
  revisions.
- Existing G3 candidate already has a provider-free one-pass preflight and
  canonical artifact verifier, but its protocol/build binding and preflight
  schemas are revision 1 and it has no durable accepted-preflight repository
  operation.
- Implementation must keep domain/application ports independent of PostgreSQL:
  A1 eligibility and exact build-binding verification belong in pure modules;
  Migration 017 and transaction/CAS behavior remain adapter responsibilities.
- G4, result metrics, lifecycle, Local Paper, provider, broker, and real-money
  paths remain prohibited.
- A1 changes the pure identities rather than only filtering output: protocol
  schema becomes v2, algorithm contract becomes v2, all seven hypothesis/
  Version-binding/hypothesis/slot roots change, matrix revision becomes 2, and
  build binding adds the preflight implementation digest.
- The common eligibility mask must be computed before any strategy runtime is
  opened. Exact 12:45 and 13:30 observed source rows determine eligibility;
  excluded sessions still contribute to Dataset SHA/count and source-only
  previous-close state but never enter Feature or strategy state.
- Current application/repository APIs expose revision-1 matrix sealing and a
  read-only preflight context only. A1 requires separate activation and
  preflight-registration commands rather than overloading the historical seal
  operation.

## 2026-08-26 A1 implementation verification

- Migration 017 now installs additive matrix-protocol history, revision-2
  matrix ownership, accepted-preflight persistence, composite foreign keys,
  and attempt-to-preflight admission without mutating revision-1 evidence.
- Matrix revision 2 activation, accepted-preflight registration, operation and
  outbox replay, and attempt admission all use PostgreSQL serialization and
  exact identity preconditions. Historical revision-1 seal replay remains
  available after activation.
- The A1 preflight computes the common Dataset-only eligibility mask before any
  strategy runtime state, enforces exact 12:45/13:30 anchors and the 0.95
  coverage floor, excludes ineligible symbol-sessions from all seven runtimes,
  and publishes the exact 31-member provider-free artifact tree.
- Artifact reload rejects unknown members, non-canonical bytes, symlinks,
  non-regular files, lineage drift, and slot/Version substitutions. Accepted
  preflight bytes are reverified again before the first attempt can consume a
  slot.
- Disposable PostgreSQL 17 focused acceptance passed `28 passed`; bounded
  no-DSN A1 tests passed `65 passed, 1 skipped`; the complete no-DSN suite
  passed `1688 passed, 86 skipped`. Python compilation, both CLI help paths,
  and scoped `git diff --check` passed.
- Formal G3 remains unexecuted. The configured backend is PostgreSQL but no
  `BACKTEST_DATABASE_URL` or shared PostgreSQL DSN is available, so no
  application matrix activation, full 28,325,340-bar scan, durable formal
  preflight registration, family-head mutation, or attempt was performed.

## 2026-08-26 formal Backtest database handoff and G3 start

- The dedicated formal Backtest PostgreSQL is
  `localhost:5090/tw_intraday_trader_backtest`; it is not a test database and
  was never exported as `TEST_POSTGRES_DSN`.
- Read-only verification found 49 Backtest tables: the 47 copied historical
  tables plus the two Migration-017 relations. All 17 migrations are applied,
  with `017_r6_matrix_revision_and_preflight.sql` latest.
- Before activation the copied R6 state rebuilt exactly: one family at head
  sequence 0 and active revision 1, one sealed revision-1 matrix, seven slots,
  zero attempts, zero preflights, one operation, and one outbox row.
- The `ATOMIC_BACKTEST_DEFAULT` binding and completed source Run both match the
  frozen Dataset ID and manifest digest; the expected payload SHA remains
  `216d306d2df5ec3f6221e6e96c3998129774c966f844e9d923634d96f275c31d`.
- A1 activation succeeded through the frozen CAS: active revision `1 -> 2`,
  head sequence remains 0, attempts remain 0, and revision-2 matrix ID is
  `r6-matrix-sha256-aaab7731d6f5f1fa6fed4cfe932637d8a097dad34fec23ee4d7ff44932817a20`.
- The formal G3 dry-run resolved exactly 28,325,340 bars and seven slots. The
  single execute traversal reached its first durable-free progress checkpoint
  at 1,000,000 bars without error; publication and PostgreSQL preflight
  registration occur only after EOF and artifact verification.

## 2026-08-26 formal G3 interruption diagnosis

- The original process is no longer running and its terminal session cannot be
  resumed. The last temporary eligibility write was at 19:18 Asia/Taipei.
- The incomplete staging tree contains 42,020 eligibility rows and occupies
  approximately 211 MB. It has no final manifest and cannot be accepted or
  resumed as immutable formal evidence.
- Formal PostgreSQL remains fail closed: preflight rows 0, attempt rows 0,
  family head sequence 0, active matrix revision 2, release state NOT_READY.
- The exact external termination cause is not proven by the remaining files.
  A clean re-execution must use a supervised long-lived process and must not
  reuse the incomplete staging tree as authority.
- Follow-up system diagnostics found no Python crash report, reboot, traceback,
  or memory-pressure termination evidence. macOS only records the process
  connection closing at 19:18:32. The strongest supported inference is that
  the foreground Python child was terminated with its Codex exec session;
  this is an orchestration-lifetime failure, not evidence of Dataset or
  strategy-runtime rejection.

## 2026-08-26 launchd-supervised G3 re-execution

- Added a dedicated fixed-command supervisor for the formal G3 preflight. It
  uses `launchctl submit` with one fixed label and `caffeinate -i`; it exposes
  no arbitrary shell or command arguments and has no automatic retry.
- The worker loads the gitignored project `.env`, requires the exact
  `localhost:5090/tw_intraday_trader_backtest` identity, removes any inherited
  `TEST_POSTGRES_DSN`, and never serializes credentials.
- Submission, current-run, RUNNING/COMPLETED/FAILED status, stdout, stderr,
  worker PID, exit code, and timestamps are durable under the supervisor run
  root. The existing frozen preflight implementation remains unchanged.
- The interrupted 211 MB staging tree was moved intact to the dedicated
  `interrupted` directory. It was not deleted or reused as authority.
- Supervised run `r6-g3-20260826T112555Z-f64bdce1` is loaded in launchd under
  `com.tw-intraday-trader.r6-g3-preflight`; worker PID 44474 has parent PID 1,
  proving it is no longer tied to the Codex exec session.
- After launch, PostgreSQL remained preflights 0, attempts 0, head 0, active
  revision 2, release NOT_READY. A fresh staging directory was created and the
  worker was consuming one CPU core.
