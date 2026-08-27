# No-Overnight Local Paper Operational Runbook

Status: integrated Local Paper operating contract. This runbook covers only the repository's
`LOCAL_PAPER_SIMULATION` account scope. It does not authorize broker access, Shioaji order APIs,
credentials, certificates, real-money execution, HA handoff, or direct database repair.

## 1. Safety boundary

- `DISABLED` and `OBSERVE_ONLY` never send no-overnight commands.
- `ENFORCING` is valid only with settings v2, the reviewed PostgreSQL Journal, successful migrations
  and health check, a single-worker deployment manifest, and an owned healthy PostgreSQL
  advisory-lock guard.
- PostgreSQL startup failure never falls back to memory mutation.
- The controller may cancel managed BUY remainder and submit bounded Local Paper SELL exits only.
- Only `AUTO_INTRADAY` and `MANUAL_INTRADAY` are managed. `AUTO_SWING`, `MANUAL_LONG`, and
  `UNCLASSIFIED_LEGACY` must not be liquidated by this controller.
- An open breach blocks every exposure-increasing BUY in the account scope. SELL, cancel, query,
  recovery, and reconciliation remain available through their existing safety checks.
- Kill Switch final admission, exact-revision reset, and `RECOVERY_REQUIRED` remain independent and
  fail closed.

## 2. Normal close procedure

1. Confirm the Dashboard card says `ENFORCING` and does not show recovery failure.
2. Before the cutoff, confirm the controller worker and guard remain healthy.
3. During the close window, observe cancellation of managed BUY remainder and bounded Local Paper
   exit attempts. Do not start a second controller or manually duplicate its exit commands.
4. At final reconciliation, inspect controller state, reconciliation status/digest, managed quantity,
   pending quantity, unresolved execution count, and result status.
5. Treat `CONFIRMED_FLAT` as valid only when its terminal SELL fact, managed quantity zero, fresh
   reconciliation `MATCH`, durable strict-flat proof, and checkpoint replay all agree.
6. Treat `OVERNIGHT_BREACH` or `RECONCILIATION_REQUIRED` as a CRITICAL incident and follow section 3.

`EXIT_SUBMITTED`, a partial fill, cancellation, rejection, retry exhaustion, or an unknown execution
fact is never flatness proof.

## 3. Open-breach response

1. Stop creating BUY attempts. The central admission latch should already block them; a blocked BUY
   is not proof that the position is resolved.
2. Preserve the Journal and checkpoint. Never edit, delete, or rewrite a breach, result, fill, order,
   reconciliation, resolution, acknowledgement, or immutable monetary record.
3. Record the displayed `breach_id`, originating session date, latest `breach_revision`, reason,
   managed/pending quantities, evidence-through Journal sequence, and reconciliation digest.
4. Allow the controller to continue risk-reducing Local Paper SELL/cancel/recovery work.
5. Investigate structural recovery errors separately. Do not acknowledge while evidence is missing,
   corrupt, stale, or reconciliation is not `MATCH`.
6. Wait for the latest breach revision to show a strict flat proof and `resolved=true`.

Every late/recovered execution fact or reconciliation-digest change creates a newer monotonic breach
revision and invalidates an older resolution or acknowledgement.

## 4. Acknowledgement procedure

The Dashboard exposes acknowledgement only for the latest resolved revision. Before pressing it:

1. Compare the displayed revision and digest with the incident record.
2. Confirm managed open quantity, pending entry/exit quantity, and unresolved execution count are all
   zero and that strict flat proof is present.
3. Confirm `resolved=true` and `acknowledged=false`.
4. Press **確認最新已解決 breach** once. The loopback-only request carries actor identity, CSRF,
   idempotency key, latest revision, and exact reconciliation digest.
5. Re-read the card. It must show `acknowledged=true` for that exact revision.

Acknowledgement does not resolve a position, delete history, clear the breach, or release BUY in the
same session. Admission can reopen only after a later reviewed trading session starts and the latest
revision still has a valid resolution followed by its matching acknowledgement.

HTTP `409` means the request is stale, unresolved, already acknowledged under another operation, or
otherwise conflicts with the latest durable chain. Re-read status; do not change the request fields to
force acceptance.

## 5. Restart and recovery

After process or machine restart:

1. PostgreSQL Journal initialization, migrations, health, guard acquisition, immutable identity-anchor
   and active settings-session metadata, and all required checkpoints must pass before ENFORCING can
   start.
2. Compare the recovered breach identity, originating reason, latest quantities, evidence sequence,
   revision, and reconciliation digest with the pre-restart incident record.
3. Confirm resolution and acknowledgement Journal ordering is unchanged.
4. Confirm `local_paper_fill.v1`, v2, and v3 monetary facts were not rewritten. New identity-rich
   monetary facts must be `local_paper_fill.v4` and retain fill.v3 settings/instrument/tax/slippage
   truth.
5. If any checkpoint, referenced snapshot/reconciliation, scope/family identity, append order, or
   immutable fill is invalid, keep BUY fail closed and investigate the evidence. Do not switch to
   memory.

## 6. Critical alerts

Durable breach revisions use `severity=CRITICAL`. Runtime also emits structured CRITICAL records for
Journal initialization, controller guard, recovery/controller startup, and worker failures. At minimum
retain event name, mode/stage, error type, scope/family or breach identity when available, revision,
active Local Paper session identity, and evidence session date.

## 7. Explicitly prohibited actions

- No clear-breach API or direct SQL update/delete.
- No acknowledgement before resolution or against a stale revision/digest.
- No memory fallback for ENFORCING.
- No second worker, HA lease/fencing claim, broker execution, or real-money interpretation.
- No synthetic fill, CA activation, trade callback, or unattended promotion.
- No claim that PostgreSQL restart/concurrency UAT passed when it was waived, skipped, or ran without
  a demonstrably fresh disposable database.

Focused fixtures and disposable PostgreSQL implementation UAT do not qualify the formal full-session
campaign. DISABLED, OBSERVE_ONLY, supervised ENFORCING, and the three operational drills remain
separate reviewed trading-session Gates.
