# PR-TM-012C1 narrow external-sandbox execution design

Status: **REPOSITORY IMPLEMENTATION DRAFT — NOT APPROVED — NOT INSTALLED — NOT ENABLED**
Production Shadow Gate: **NOT_PASSED**

## 1. Objective

Run the existing committed entrypoints outside the Codex network-restricted sandbox while preserving
their data-only and decision-only boundaries:

- `scripts/preflight_trade_management_shadow.py` is the only C0 entrypoint;
- `scripts/run_trade_management_shadow_c1.py` is the only C1 entrypoint;
- no supervisor component may create inputs, orders, fills, matches, Positions, or Shadow decisions;
- no process may call a broker order API, enable CA, or subscribe to trade callbacks.

The repository-only implementation draft described in section 11 is now present. This document still
does not authorize installation, scheduling, permission changes, or a formal session.

## 2. Recommended deployment boundary

Use a dedicated user-level launchd service whose process runs inside a separately reviewed macOS
sandbox profile. The service must execute from a clean runtime checkout pinned to one approved commit
and a pre-built virtual environment. It must not execute the current concurrent dirty worktree.

```text
launchd calendar trigger (08:35 Asia/Taipei)
        |
        v
fixed-hash external supervisor (control plane only)
        |
        +-- reviewed TWSE calendar gate
        +-- atomic date/session ownership lock
        +-- exact argv / path / commit / input checks
        +-- C0 process, wait for terminal exit
        +-- C1 process only when C0 exits 0
        +-- watchdog and immutable process log
        |
        v
existing repository C0/C1 entrypoints (data plane)
```

The supervisor is not a fallback or partial C1 runner. It has no imports from provider, Journal,
Risk, order, fill, Position, or trading decision modules. Its only responsibilities are process
admission, exact command construction, exit-code sequencing, and termination monitoring.

## 3. Exact process allowlist

The reviewed sandbox and supervisor must admit only the following executable/argv
graph:

1. one fixed-hash supervisor executable as the control plane; it cannot import trading modules;
2. the pinned checkout's `.venv/bin/python scripts/preflight_trade_management_shadow.py` with the
   exact reviewed C0 argv;
3. the same Python executable and C0 script with only `--provider-preflight-worker`, as a child of the
   admitted C0 PID;
4. the same Python executable with `-m pytest -q` plus C0's frozen `REHEARSAL_TARGETS`, as a child of
   the admitted C0 PID;
5. `/usr/bin/git rev-parse HEAD`, only as a child of the supervisor, C0, or C1 for commit/runtime identity;
6. `/usr/bin/git status --porcelain --untracked-files=all`, only as a child of the supervisor for the
   clean-checkout gate;
7. the pinned checkout's `.venv/bin/python scripts/run_trade_management_shadow_c1.py` with the exact
   reviewed C1 argv.

The only admitted trading/data-plane child processes are the existing C0 and C1 entrypoints.
The provider worker and rehearsal are existing internal C0 modes, not alternate entrypoints.

No shell expansion, interactive command, package install, source mutation, migration command, generic
Python `-c`, unrestricted `-m`, arbitrary script, or alternate runner is permitted during a formal
run. A macOS sandbox rule can constrain executable paths but cannot by itself prove argv or parent-child
relationships; the fixed-hash supervisor/exec wrapper must enforce both and emit their digests in its
terminal disposition.

Current implementation note: the repository draft performs exact argv checks inside Python, but the
rendered sandbox must still admit the same standalone interpreter for C0, the provider worker, the
rehearsal, and C1. A separate process can therefore invoke that admitted interpreter with different
argv. The required OS-level generic-Python denial is **not implemented** and cannot be inferred from
the application checks.

## 4. Admission state machine

| State | Required evidence | Allowed transition |
|---|---|---|
| `LOCK_ACQUIRE` | Atomic owner-only lock for market date/session was created with `O_CREAT|O_EXCL` | `CALENDAR_CHECK` or terminal `ALREADY_OWNED` |
| `CALENDAR_CHECK` | Current date is accepted by the pinned reviewed TWSE calendar | `C0_READY_TO_START` or terminal `SKIPPED_CLOSED_DATE` |
| `C0_READY_TO_START` | Before 09:00, clean approved commit, fixed venv, owner-only secret file, output paths absent | start only C0 |
| `C0_RUNNING` | One child PID, immutable stdout/stderr path | wait; no retry |
| `C0_COMPLETE` | Exit 0, immutable C0 artifact and sidecar exist, and no C0 `.write.lock` remains | `C1_READY_TO_START`; otherwise terminal `BLOCKED` |
| `C1_READY_TO_START` | No per-date promotion lock remains; canonical bundle manifest, review approval, sidecars, and four exact approved input digests pass; no draft path is accepted | start only C1 |
| `C1_RUNNING` | One recorded child PID; 09:00–13:30 capture owns its lifecycle | wait for natural terminal exit; emergency termination remains outside the supervisor |
| `TERMINAL` | C1 terminal exit plus artifact inventory | stop; never start another child |

The supervisor must never retry C0 or C1 automatically. A rerun requires a new reviewed session/output
identity and separate authorization.

The ownership lock is acquired before checking any output or database session target and is keyed by market date; it records the session ID,
supervisor PID, start time, and commit without secrets. A different session ID cannot acquire a second
lock for the same market date. A stale lock
is never deleted automatically; operator review must prove the recorded PID and every C0/C1 child are
gone before a new session identity is authorized. Pausing the existing Codex automation remains a
separate installation prerequisite; the lock is defense in depth, not permission to run two schedulers.

## 5. Filesystem policy

Read access is limited to:

- the pinned runtime checkout and virtual environment;
- the reviewed calendar;
- the exact canonical `session_inputs/YYYY-MM-DD/` directory;
- the exact canonical `review_approval.json`, `bundle_manifest.json`, and their sidecars;
- an owner-only environment file containing provider credentials and the two explicit DSNs.

Write access is limited to date/session-specific immutable roots for:

- C0/C1 JSON artifacts and SHA-256 sidecars;
- canonical market Journal/records;
- supervisor stdout/stderr and terminal disposition.

The sandbox must deny writes to source, `.git`, virtual environment, calendar, canonical input files,
approval artifacts, bundle manifests, and existing artifact paths. Symlinks are rejected before
process start and by C1 admission. The current `.env` mode is
`0644`; approval requires an owner-only secret source (`0600`) without copying secrets into a launchd
plist or artifact.

The supervisor may read that file only to construct a minimal inherited environment for C0/C1. It
must not pass the secret-file path as an unrestricted CLI argument, print values, or inherit unrelated
environment variables. The existing entrypoints remain authoritative and must not be modified at
installation time.

## 6. Network policy

The reviewed profile must permit the minimum capabilities proven necessary by rehearsal:

- TCP and UDP loopback bind for Shioaji/Solace inter-thread initialization;
- loopback TCP connections to the explicit Local Paper and dedicated Shadow PostgreSQL endpoints;
- outbound TLS only to the reviewed Shioaji service endpoints needed for simulation login and market
  data.

Provider endpoint discovery and allowlist stability are unresolved. Do not substitute unrestricted
network access. Approval requires a captured, reviewed endpoint inventory and a rehearsal proving that
denied destinations remain blocked.

## 7. Runtime and identity gates

Before C0 starts, the supervisor must prove:

- the checkout commit equals the approved commit;
- `/usr/bin/git status --porcelain --untracked-files=all` returns empty output;
- Python, dependency-lock, and complete pre-built virtual-environment tree digests match the approved runtime;
- the environment file is owner-only and contains both named DSNs without printing values;
- Local Paper and Shadow DSNs are distinct;
- the runtime identity covers C0, C1, prepare, review, and promotion entrypoints plus their runtime modules;
- the canonical input approval and bundle manifest bind the exact four file SHA-256 values, market
  date, session, symbol, policy versions, RiskSnapshot provenance, reviewer, and current runtime identity;
- output, sidecar, Journal session, and process-log targets do not already exist.

C0 remains authoritative for provider simulation identity, `subscribe_trade=false`, explicit authority
flags, PostgreSQL schema/session scope, rehearsal, and source-content identity. C1 must execute from the
same unchanged checkout so its runtime identity equals C0.

## 8. Watchdog and failure behavior

- Pre-open child startup has one bounded timeout and no retry.
- C1 is allowed to run through the 13:30 close and post-close finalization window.
- The current C1 CLI has no independently approved cooperative signal-stop contract. Therefore the
  supervisor must not be approved to send automatic `SIGTERM` during a formal capture yet. It records
  the child PID and waits without a C1 timeout for natural post-close finalization.
- A later cooperative-stop change must first prove that SIGTERM closes admission, drains or accounts
  for pending evidence, writes `INCOMPLETE/BLOCKED`, and exits within a bounded grace period. Until
  then, emergency termination is an explicit operator action and the supervisor terminal disposition,
  artifact-pair lock, process log, and surviving Journal are retained as incomplete evidence.
- `SIGKILL` is never automatic.
- Never delete, truncate, rewrite, or relabel an `INCOMPLETE`, `BLOCKED`, or `PENDING_REVIEW` artifact.
- No failure path may start a fallback capture, generate inputs, clear PostgreSQL, or call an order API.

## 9. Installation gate

Independent review must approve all of the following before any installation:

- supervisor source and digest;
- launchd plist and calendar/timezone behavior;
- macOS sandbox profile and denial logs;
- clean-checkout provisioning and rollback procedure;
- secret-file permissions and rotation procedure;
- provider egress inventory;
- exact C0/C1 argv fixtures for a closed date, missing input, C0 blocked, no-fill, and synthetic-test-only
  activated session;
- exact child-process graph fixtures proving Git, provider worker, and frozen rehearsal are admitted
  while generic Python/script/module execution is denied;
- atomic ownership-lock contention, stale-lock, and crash-retention fixtures;
- a separately reviewed cooperative termination implementation, or an explicit approval that no
  automatic process termination is installed;
- proof that the Codex automation is paused or converted to a monitor so two collectors cannot start.

Current disposition: **BLOCKED — INSTALLATION INELIGIBLE**. The execution-boundary and provider-egress
gates are unsatisfied, and the current Codex automation remains active and unchanged; therefore an
external service must not be installed or enabled.

## 10. Rollback

Rollback removes or unloads only the proposed user-level service and its sandbox/supervisor files. It
does not delete evidence, canonical inputs, database rows, the runtime checkout, or the existing Codex
automation. After rollback, verify no supervisor/C0/C1 PID remains and keep Production Shadow Gate at
`NOT_PASSED`.

## 11. Repository implementation draft

The following reviewable files implement the control plane without installing or enabling it:

- `runtime/trade_management_external_supervisor.py`: pure no-retry state machine and exact C0/C1 argv construction;
- `runtime/trade_management_external_adapters.py`: reviewed-calendar, immutable lock/disposition, clean commit, source/runtime/venv digests, `0600` secret, canonical review-promotion, and C0/C1 artifact gates;
- `runtime/trade_management_external_git.py`: the Git-only read-only identity/status allowlist used by input workflows and formal admission;
- `runtime/trade_management_external_process.py`: the Shadow-only subprocess adapter for C0 provider-worker, frozen rehearsal, C0, and C1 commands;
- `scripts/run_trade_management_shadow_external_supervisor.py`: a thin CLI that accepts only one immutable independently approved spec;
- `architecture/deployment/`: disabled/unapproved approval, sandbox, launchd, and installation-checklist templates;
- `tests/test_trade_management_external_supervisor.py`: fake/stub-only state, race, digest, secret, argv, and deployment-boundary regressions.

C0's provider worker and frozen pytest rehearsal now use the shared child-process allowlist. Pytest plugin autoload is disabled. Git runs with its original reviewed argv plus a fixed environment that disables fsmonitor, optional locks, system/global configuration, and source-index writes. The supervisor rechecks the approved commit, clean status, source identity, approved files, reviewed calendar, and full virtual-environment tree immediately before each C0/C1 start.

The shipped approval JSON remains `NOT_APPROVED`; the launchd plist remains `Disabled=true`; the sandbox template denies all network because provider egress is unresolved. The CLI therefore has no valid repository-supplied approval artifact and cannot be used for a formal run from this checkout. No automation, secret permission, runtime checkout, provider/DSN connection, or C0/C1 session was changed or executed by this implementation phase.

## 12. 2026-08-26 feasibility disposition

Two installation blockers remain independently fail-closed:

1. **Execution boundary — BLOCKED.** The pinned CPython distribution is technically embeddable, but a
   single native wrapper around the supervisor does not remove the four standalone Python roles in
   the reviewed process graph: C0, C0 provider worker, frozen pytest rehearsal, and C1. Keeping Python
   in the sandbox allowlist preserves generic interpreter capability; removing it breaks the existing
   entrypoints. Implementing multiple embedded roles or moving the child boundaries in-process would
   change reviewed behavior and exceeds the narrow launcher proposal.
2. **Provider egress — BLOCKED.** The following official pages were retrieved on 2026-08-26
   (Asia/Taipei): [Login](https://sinotrade.github.io/tutor/login/) confirms a Solace connection and
   shows a redacted/runtime-selected `<IP>:80` example;
   [Event Callback](https://sinotrade.github.io/tutor/callback/event_cb/) confirms Solace broker use;
   [Simulation Mode](https://sinotrade.github.io/tutor/simulation/) lists supported APIs. These pages
   do not provide a complete stable hostname/port contract for simulation login, contract acquisition,
   and market data. The locked `shioaji==1.7.3` compiled core SHA-256 is
   `931ae62a76e1e5e7a88a4cfe00da6f3952a94a9e09ee0d296f58773911a004f3`; its embedded strings and any
   single observed session are not an authoritative, complete allowlist. This provenance is non-authorizing
   and does not modify or promote the existing immutable provider inventory.

Consequently the provider allowlist remains empty, the sandbox remains deny-network, the plist remains
disabled/uninstalled, the existing automation remains unchanged, and no approval spec may be promoted.
Phase 12 and any formal C0/C1 run remain `BLOCKED`; Production Shadow Gate remains `NOT_PASSED`.
