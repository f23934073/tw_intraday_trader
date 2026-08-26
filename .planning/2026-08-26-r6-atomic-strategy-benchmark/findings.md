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
