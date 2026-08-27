# No-Overnight Evidence Campaign Runbook

Status: integrated evidence-only operating contract. It prepares a candidate for independent G6
review; it cannot enable unattended Local Paper, broker execution, real money, HA, or a second
execution pipeline.

## 1. Fixed authority boundary

- The fixed Local Paper identity anchor, exact active settings-bound Local Paper session,
  `no_overnight.v1` Journal session, strict projections, and current checkpoints are the only
  execution evidence.
- A report uses `no_overnight_session_evidence_v2` and binds the exact active
  `local_paper_session_id`, its settings digest, and the integrated code identity. Old PR-NO-006
  v1 reports and the old branch's 2026-08-27 artifacts cannot qualify this integration.
- An evidence report may derive metrics and seal digests. It cannot manufacture a command, order,
  fill, reconciliation, flat proof, breach resolution, or acknowledgement.
- Every artifact fixes `activation_authority=NONE_EVIDENCE_ONLY`.
- `READY_FOR_INDEPENDENT_REVIEW` means only that the sealed bundle may be reviewed. Both
  `unattended_local_paper_allowed` and `broker_live_ready` remain `false`.
- A skipped, waived, no-DSN, or non-disposable PostgreSQL run is `NOT_RUN_NOT_PASSED`; it must never
  be rendered as a pass.

## 2. Campaign identity and artifact layout

Freeze one `campaign_id`, exact clean code identity, `account_scope_id`, `policy_family_id`, active
Local Paper session/settings identity, reviewed calendar digest, provider identity, and reviewed
timezone. Supervised ENFORCING also freezes the policy version/digest, deployment-manifest digest,
and guard identity.

Store artifacts in a new campaign directory without overwriting an earlier file:

```text
<campaign>/
  sessions/<date>-disabled.json
  sessions/<date>-observe-only.json
  sessions/<date>-supervised-enforcing.json
  parameter_review.json
  drills/restart-recovery.json
  drills/duplicate-process.json
  drills/breach.json
  campaign_report.json
  review_notes.sha256
```

Writers use exclusive creation, canonical JSON, fsync, and exact-content idempotency. A different
payload at an existing path is an error; create a new campaign instead of editing the old one.

## 3. Durable evidence window

For each reviewed session, start the deterministic campaign/stage/date evidence session in the same
configured Journal repository and append `no_overnight_evidence_window_opened.v1` before runtime
startup and at or before the reviewed open. After the reviewed close and final controller pass, append
`no_overnight_evidence_window_closed.v1`. The close marker binds the open record ID, global Journal
sequence, and fingerprint.

Build the session report only after both markers exist. The builder strictly replays both projections,
requires current checkpoints, verifies the exact active Local Paper session/settings identity, and
checks marker fingerprints plus `open < every covered Local Paper/no-overnight fact < close` global
append order. A late open is preserved as `SESSION_OPEN_NOT_COVERED`; missing, duplicated, forged, or
contradictory markers fail closed.

Do not create markers after the session and backdate their `occurred_at`. Journal append order remains
visible, and independent review must compare marker sequence with the covered execution facts.

The repository-owned DISABLED capture command uses the project PostgreSQL Journal but always
constructs `MockProvider`; it never loads or logs into a broker provider:

```bash
PYTHONPATH=. .venv/bin/python \
  scripts/capture_no_overnight_disabled_baseline.py \
  --campaign-id <reviewed-campaign-id> \
  --session-date <reviewed-date> \
  --artifact-root <new-campaign-directory> \
  --env-file <project-env-file>
```

Start it on the reviewed session date no later than 09:00 Asia/Taipei. It opens the marker before
runtime composition, waits in bounded intervals through 13:30, seals and strictly re-reads the report,
and exits non-zero for any safety reason. After artifact preparation and PostgreSQL construction, the
runner performs a fresh application-clock preflight and then asks the Journal to atomically create the
evidence session and open record under the 09:00 cutoff. The PostgreSQL adapter uses
`clock_timestamp()` before, between, and after the two writes in one transaction and requires those
samples to be nondecreasing. If either database operation crosses 09:00 or the database clock moves
backwards, the transaction rolls back, producing no evidence session, record, runtime, or report. The
first accepted PostgreSQL server timestamp is persisted as both `session.started_at` and
`record.occurred_at`; a caller timestamp cannot backdate the durable marker.

An exact pre-cutoff retry is idempotent, while a session without its paired open record fails closed.
After commit and Journal cleanup, the runner checks its operational clock again immediately before
runtime construction. A backwards or post-09:00 value stops capture with no runtime or report, but
retains the already-durable open marker as incomplete evidence. Do not delete or rewrite that marker.

The CLI reads only the explicitly named, no-follow environment file; ambient database settings cannot
override it. The campaign and `sessions` directories are created with no-follow descriptors. Both
descriptors remain open and bind device, inode, type, link count, size, mtime, and ctime across capture
and around the report write, so replacing the root while moving the original `sessions` inode still
fails closed. A dirty worktree is rejected before PostgreSQL initialization. The runner reads the
exact clean `git rev-parse HEAD`; a supplied or historical code identity cannot override it.

If any later startup or capture step fails after the open append, retain that open record as incomplete
evidence; never reuse it with a different timestamp.

## 4. Stage sequence

1. **DISABLED baseline** — capture a full reviewed session. It may be `COMPLETE` but is always
   `NOT_APPLICABLE` for qualification. Any controller session or action is a safety finding. Any
   baseline safety reason makes the parameter review `INSUFFICIENT_EVIDENCE` and independently keeps
   the campaign `INCOMPLETE`; a caller-supplied `FROZEN` status cannot override it.
2. **OBSERVE_ONLY** — capture a later full session. Require terminal projection, current checkpoint,
   reconciliation `MATCH`, and zero no-overnight handler side effects. A would-action is observation;
   an order/fill is not.
3. **Pre-enforcement parameter approval** — aggregate exactly the completed DISABLED and OBSERVE_ONLY
   reports. The artifact phase is `PRE_ENFORCEMENT_APPROVAL` and must be finalized strictly after both
   report fences but before the supervised ENFORCING evidence window starts. It must contain at least
   one verified sample for managed entry opportunity, cancel latency, partial fill, exit-fill latency,
   exit-retry latency, and executable-book availability. Review false positives and bind the notes
   digest. Metrics are derived from reports; the review API does not accept caller-supplied counts.
4. **Supervised ENFORCING** — only after policy and deployment identities are frozen. A human
   supervises Local Paper. PostgreSQL authority, manifest, guard, final admission, terminal result,
   and reconciliation must all be present.
5. **Drills** — after the supervised ENFORCING report is finalized, separately seal restart recovery,
   duplicate-process rejection, and durable breach evidence. `NOT_RUN` or `FAILED` never satisfies the
   gate. A drill timestamp at or before the supervised report fence is invalid.
6. **Campaign report** — aggregate the exact session-report set, frozen parameter approval, and three
   unique passed drills. A later three-stage review is sealed as `POST_UAT_VALIDATION` and cannot
   substitute for the prerequisite approval. The maximum result is
   `READY_FOR_INDEPENDENT_REVIEW`.

## 5. Required zero and completeness checks

A review-ready bundle requires:

- full open-to-close marker coverage and current strict checkpoints;
- complete `local_paper_fill.v4` provenance with all fill.v3 instrument/settings/tax/slippage truth,
  `fill_source=paper_simulation`, expected provider, and `execution_authority=false`;
- every no-overnight fill linked to its canonical command and exact `target_exposure_id`;
- every transition recoverable with its strict snapshot/reconciliation/result evidence;
- `synthetic_fill_count=0`;
- `duplicate_exit_side_effect_count=0`;
- `wrong_horizon_liquidation_count=0`;
- no policy, manifest, code, scope, family, active-session, provider, or report-set drift;
- no unresolved reconciliation or terminal breach in a qualifying normal session.

Incomplete provenance is not counted as zero. It makes the session incomplete.

## 6. Artifact inspection

Validate any artifact with the strict reader before review:

```bash
.venv/bin/python scripts/inspect_no_overnight_evidence.py session <path>
.venv/bin/python scripts/inspect_no_overnight_evidence.py parameter-review <path>
.venv/bin/python scripts/inspect_no_overnight_evidence.py drill <path>
.venv/bin/python scripts/inspect_no_overnight_evidence.py campaign \
  <campaign>/campaign_report.json
.venv/bin/python scripts/inspect_no_overnight_evidence.py bundle <campaign>
```

The leaf commands validate only that individual artifact. They cannot qualify a campaign. Both
`campaign` and `bundle` require the complete canonical directory, no-follow load every session,
parameter-review, drill, and campaign artifact, verify canonical filenames and exact digest mappings,
then rebuild the campaign with the same builder used before persistence. Sparse bundles, extra
artifacts, phase substitution, metrics/report-set drift, invalid chronology, or old evidence schema
fail closed.

The command prints canonical JSON only after exact fields, types, immutable digests, status
invariants, activation boundary, active Local Paper session/settings identity, and PostgreSQL
disposition all validate. It has no Journal, controller, order, or broker mutation authority.

A `FROZEN` parameter review records either `PRE_ENFORCEMENT_APPROVAL` or `POST_UAT_VALIDATION`; only
the former can satisfy campaign readiness. Its exact report set, metrics, required sample classes,
zero-safety metrics, and causal position between OBSERVE_ONLY and ENFORCING are all rechecked. A v2
campaign artifact also binds each report digest to one of the three stages and each unique drill
digest to its canonical drill kind; `READY_FOR_INDEPENDENT_REVIEW` is rejected unless both mappings
and the review/drill chronology are complete.

Artifact reads and idempotent writes reject symlink files and symlinked parent directories. A new
artifact is fsynced before its verified parent directory, so successful creation has both file and
directory durability. Bundle validation fences every root, session, and drill entry by device, inode,
type, link count, size, modification time, and change time. It repeats all three inventories after
semantic rebuild and fails closed if a name or fence changed during validation. If
`review_notes.sha256` is present, it must be a regular file containing exactly the parameter review's
bound note digest plus one newline.

## 7. False-positive and rollback procedure

Review each block, cancellation, exit, retry, breach, and wrong-horizon metric against its sealed
Journal sequence. Record the review note separately and bind its SHA-256 in `parameter_review.json`.

If any evidence is incomplete or contradictory:

1. do not edit or delete the Journal or artifact;
2. mark the campaign incomplete and retain all failed evidence;
3. rollback runtime behavior only to `OBSERVE_ONLY` or `DISABLED` through the existing reviewed
   configuration procedure;
4. do not clear an open breach or reopen BUY admission;
5. start a new campaign identity after the defect is fixed.

Rollback does not remove scope/family identity, breach state, or historical evidence. No campaign
result changes runtime configuration automatically.

## 8. Independent G6 decision

Independent review must verify the candidate diff, sealed artifacts, regression suite, scope audit,
and exact PostgreSQL disposition. Only a separate user authorization after that review may consider
unattended Local Paper. Broker/live readiness remains a future, separately designed and authorized
gate.
