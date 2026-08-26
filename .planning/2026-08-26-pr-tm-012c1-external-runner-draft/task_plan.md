# Task Plan: PR-TM-012C1 External Runner Draft

## Goal

Implement and verify a repository-only, uninstalled external execution control-plane draft that can invoke only the reviewed C0/C1 entrypoints under exact fail-closed boundaries, then independently review and remediate it until the decision is APPROVE.

## Scope Boundaries

- Phases 1–5 were repository-only: no launchd/sandbox installation, automation mutation, provider/DSN access, or C0/C1 execution occurred.
- The 2026-08-26 continuation authorizes readiness items 1–7 and conditional item 8, but every installation/execution transition remains fail-closed behind its preceding immutable review gate.
- Do not invent secrets, DSNs, provider endpoints, review approvals, inputs, fills, or evidence.
- Do not install/enable or run C0/C1 unless the rendered package is independently approved, the reviewed calendar/window and canonical inputs pass, and unattended external access is proven.
- Do not add order, fill, Position, CA, trade-callback, or broker-order capability.
- Preserve unrelated dirty-worktree changes and the legacy immutable packet.

## Phases

### Phase 1: Contract and repository audit

- [x] Read the external execution design and operational runbook.
- [x] Locate reusable calendar, artifact, runtime-identity, and test conventions.
- [x] Freeze exact supervisor inputs, states, argv, process graph, and non-goals.
- **Status:** complete

### Phase 2: Control-plane implementation

- [x] Implement a pure supervisor core and narrow filesystem/subprocess adapters.
- [x] Enforce reviewed calendar, immutable lock, clean/pinned runtime identity, input presence, and exact C0/C1 sequencing.
- [x] Write immutable disposition artifacts without creating partial Shadow evidence.
- **Status:** complete

### Phase 3: Disabled deployment drafts

- [x] Add an uninstalled sandbox profile template.
- [x] Add an unloaded launchd plist template and installation review checklist.
- [x] Ensure every draft states NOT APPROVED / NOT INSTALLED / NOT ENABLED.
- **Status:** complete

### Phase 4: Verification

- [x] Add pure fixture tests for closed dates, missing inputs, locks, C0 block, C1 sequencing, argv allowlist, crash retention, and forbidden imports.
- [x] Run focused tests, static checks, CLI help, and relevant regressions without executing C0/C1.
- [x] Confirm no out-of-scope files or runtime effects.
- **Status:** complete

### Phase 5: Adversarial review and remediation loop

- [x] Review security, TOCTOU, immutable retry, review promotion, execution boundary, process graph, and documentation.
- [x] If REQUEST CHANGES, fix only blocking findings and repeat verification/review.
- [x] Stop only at APPROVE and record the final decision.
- **Status:** complete — final decision `APPROVE`

### Phase 6: Current-state admission audit

- [x] Verify commit, dirty-worktree isolation, reviewed calendar coverage, dependency state, existing input promotion state, secret-path posture, sandbox support, and automation state.
- [x] Freeze absolute runtime paths and identify every external permission or unavailable prerequisite before mutation.
- **Status:** complete

### Phase 7: Clean pinned runtime checkout

- [x] Create an independent clean checkout starting from commit `19d4489bceab9e2cf06c12d31acf32e454428dd7` outside the concurrent source worktree.
- [x] Prove clean status, absence of checkout `.env`, and path separation from future config/state roots; sandbox write-denial proof remains Phase 10.
- **Status:** complete

### Phase 8: Dependency and virtualenv identity

- [x] Select or create a reviewable dependency lock without silently changing application dependencies.
- [x] Build the isolated virtualenv and record interpreter plus full-tree SHA-256 identity.
- **Status:** complete

### Phase 9: Secure runtime roots and rendered drafts

- [x] Create owner-only external config/runtime roots and validate existing secret/DSN material without printing values.
- [x] Render sandbox and launchd candidates with exact absolute paths while keeping them disabled and uninstalled; the approval spec remains Phase 12 because installation evidence is incomplete.
- **Status:** complete

### Phase 10: Sandbox and egress rehearsal

- [x] Capture provider/loopback egress inventory from approved non-order operations only; preserve an empty provider allowlist and explicit connectivity blockers.
- [x] Rehearse source-write, arbitrary process, generic Python, forbidden network, and non-approved path boundaries against the exact rendered sandbox; record the generic-Python denial as a truthful failure.
- **Status:** complete — `BLOCKED` by unresolved provider endpoints and lack of OS-level Python argv enforcement

### Phase 11: Automation coordination

- [x] Inspect the existing `pr-tm-012c1-shadow` automation and preserve its full safety prompt.
- [ ] Pause it or convert it to monitor-only only after external runner installation eligibility is otherwise proven; read back persisted state and create immutable pause evidence.
- **Status:** blocked by Phase 10; existing automation intentionally remains active and unchanged

### Phase 12: Immutable installation review package

- [ ] Bind all file, runtime, denial, egress, automation, and reviewer evidence into a `0600` approval spec/sidecar.
- [ ] Perform autonomous adversarial review; remediate and repeat until `APPROVE`, otherwise remain `BLOCKED`.
- **Status:** blocked; no approval spec created because installation eligibility is false

### Phase 13: Conditional installation and formal session

- [ ] Install/enable only the exact approved rendered artifacts with no shell or alternate runner.
- [ ] On a reviewed trading day inside the pre-open window, run only the existing C0 then C1 supervisor path; preserve truthful terminal artifacts and never retry.
- [ ] Keep a single day at Production Shadow Gate `NOT_PASSED` and report any missing fill as `INSUFFICIENT_EVIDENCE`.
- **Status:** blocked — conditional gates are not satisfied; C0/C1 not executed

### Phase 14: Native fixed-launcher feasibility and contract

- [x] Verify the pinned CPython embedding prerequisites and determine whether a non-shell fixed supervisor invocation could close the complete child-process boundary.
- [x] Define the required source/build/runtime identity checks, sandbox transition, argv/environment contracts, and explicit rejection criteria before coding; no launcher identity was created because the candidate was rejected before implementation.
- **Status:** complete — `BLOCKED`; a single outer launcher leaves four allowlisted Python child roles and does not close the OS-level generic-interpreter boundary

### Phase 15: Repository-only launcher implementation and review

- [ ] Implement the smallest native infrastructure adapter and immutable build/rehearsal entrypoints without adding provider, DB, C0, C1, or trading capability.
- [ ] Prove generic standalone Python denial, fixed in-process supervisor argv, warnings-as-errors, sanitizer/static checks, exact digests, and fail-closed error behavior.
- [ ] Run autonomous severity-first review; remediate every P0/P1/P2 until `APPROVE` or preserve a truthful `BLOCKED` disposition.
- **Status:** blocked by Phase 14; implementation intentionally not started because the proposed adapter cannot satisfy its acceptance contract without changing reviewed child-process semantics

### Phase 16: Official provider egress contract research

- [x] Inspect only official Shioaji/Sinotrade primary documentation and locked-package evidence for a complete runtime hostname/port contract; do not login or connect.
- [x] Update the immutable provider inventory only if sources establish a complete reviewable allowlist; otherwise retain an empty allowlist and `BLOCKED`.
- **Status:** complete — `BLOCKED`; no official complete stable hostname/port contract exists in the reviewed sources, so the immutable empty allowlist was retained unchanged

## Success Criteria

1. The supervisor can only construct and invoke the two reviewed entrypoints with exact argv.
2. Calendar/input/runtime/lock failures stop before subprocess execution and leave a truthful immutable disposition.
3. C1 can start only after a newly produced C0 disposition is READY_FOR_SESSION and identity-bound.
4. Tests use stubs only; no provider, DB, C0, or C1 execution occurs.
5. Deployment material remains explicitly uninstalled and disabled.
6. Final independent review decision is APPROVE; Production Shadow Gate remains NOT_PASSED.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| Import-boundary fixture applied the control-plane no-trading-import rule to the existing C0 data plane | 1 | Scope the no-trading rule to supervisor modules while retaining the subprocess-import assertion across C0 and identity code. |
| New lock-retention assertions were inserted below the following test during a combined patch | 1 | Move them back into the ownership-lock test; no production file was affected. |
| First Popen refactor compile had positional argv after keyword role | 1 | Name the `argv=` argument in all four allowlisted captured-process calls. |
| Phase 6 input inventory returned a missing-directory error for canonical 2026-08-27 inputs | 1 | Record the absence as a formal execution blocker; inspect the existing draft packet without generating or promoting inputs. |
| Phase 6 external-root inventory reported the three proposed roots absent | 1 | Treat absence as expected pre-provisioning state; do not fall back to the repository `.env` or dirty checkout. |
| Exact readiness branch lookup returned an invalid/missing ref | 1 | Treat this as proof the scoped branch name is available; create it once from the approved draft commit. |
| Runtime checkout inventory reported `.env` absent | 1 | This is the required fail-closed source/config separation, not a missing-secret fallback; provision a separate filtered `0600` config in Phase 9. |
| `uv lock --check --offline` could not read uv cache internal `.git` under Codex sandbox | 1 | Classify as a local sandbox read restriction, then rerun the same non-mutating offline check with narrowly scoped external permission. |
| Frozen offline venv sync lacked cached `httpx2==2.12.0` | 1 | Preserve the lock and partial venv as non-evidence; switch to one network-enabled `uv sync --frozen --all-extras` so downloaded artifacts remain hash-bound to the reviewed lock. |
| Default frozen sync installed the local project editable and modified tracked egg-info source inventory | 1 | Reject that venv for formal use; sync with `--no-install-project` and restore only the generated tracked file change before clean-status verification. |
| Dedicated clean runtime full suite has one price-coverage source-digest failure | 1 | Do not import unrelated dirty source changes; isolate the failure, run the exact frozen C0 rehearsal plus external-runner fixtures, and retain the full-suite mismatch as an installation-review finding. |
| First venv tree digest call passed relative `.venv` | 1 | The adapter correctly requires absolute paths; rerun once with the frozen absolute runtime checkout path. |
| First readiness fixture treated the metadata key name `provider_secret_alias_count` as a secret-value leak | 1 | Use a distinctive fixture value and assert that exact value is absent; keep safe alias-count metadata. |
