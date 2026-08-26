# Task Plan: PR-TM-012C1 External Runner Draft

## Goal

Implement and verify a repository-only, uninstalled external execution control-plane draft that can invoke only the reviewed C0/C1 entrypoints under exact fail-closed boundaries, then independently review and remediate it until the decision is APPROVE.

## Scope Boundaries

- Do not install or enable launchd or sandbox services.
- Do not modify Codex automation configuration.
- Do not connect to provider, PostgreSQL, or Local Paper DSNs.
- Do not run C0 or C1, generate inputs, promote reviews, or create evidence.
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
