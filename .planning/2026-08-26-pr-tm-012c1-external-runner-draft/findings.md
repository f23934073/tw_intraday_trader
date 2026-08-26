# Findings: PR-TM-012C1 External Runner Draft

## Confirmed constraints

- This phase is repository-only implementation and tests.
- Formal execution, installation, provider/DSN access, and evidence generation remain prohibited.
- Existing unrelated dirty-worktree changes must not be staged, reverted, or reformatted.
- Production Shadow Gate must remain `NOT_PASSED`.

## Repository findings

- The reviewed design permits only the existing C0 and C1 entrypoints. C0 internally starts exactly a provider worker and a frozen pytest rehearsal; C0/C1 runtime identity starts exact Git commands.
- A macOS sandbox profile can restrict executable paths but cannot prove argv or parent PID. Code-controlled subprocesses therefore need a shared exact allowlist adapter in addition to the OS sandbox.
- C1 already owns authoritative digest, review-promotion, canonical-path, symlink, DSN-separation, pre-open-window, data-only, and C0-binding checks. The supervisor should pre-screen obvious absence but must not duplicate or weaken those checks.
- `ReviewedEquityCalendar` is a data-only reusable calendar gate and has no provider/order imports.
- Existing artifact publication uses exclusive lock/staging/hard-link commit semantics and retains incomplete pair locks on partial publication.
- The current `.env` is `0644`; formal admission must require `0600` and force `SJ_SIMULATION=true` in the minimal child environment.
- No dependency lock file exists in the current checkout. A formal approval spec must bind at least one independently reviewed dependency-lock artifact, so the supplied template must remain `NOT_APPROVED`.
- The current worktree is dirty and is not eligible for formal execution. Production tests must use fakes/stubs and must not invoke either Shadow entrypoint.

## Frozen implementation decisions

- Add a pure supervisor application core with injected ports; keep filesystem, Git, subprocess, calendar, secret, and artifact operations in an infrastructure adapter.
- Derive exact session IDs, C0/C1 paths, input paths, records root, and argv from the market date and immutable execution spec; accept no arbitrary child command.
- Acquire a market-date lock with `O_CREAT|O_EXCL` before the calendar gate and never auto-delete it, including closed-date and crash paths.
- Add an immutable terminal disposition distinct from C0/C1 evidence. It always reports `production_shadow_gate=NOT_PASSED` and never represents partial Shadow evidence.
- Require an immutable digest-bound installation approval spec with status `APPROVED_FOR_INSTALLATION`; ship only a placeholder `NOT_APPROVED` template.
- Do not add automatic C1 termination. The adapter waits for natural completion; operator emergency termination remains outside this implementation.
- Route C0 provider-worker, frozen rehearsal, Git identity, and supervisor C0/C1 starts through named exact subprocess functions. No generic Python `-c`, arbitrary `-m`, shell, or alternate script interface is exposed.

## Review findings

### Round 1 — REQUEST CHANGES

- **P1:** Supervisor pre-admission compared approval/bundle claimed digests to sidecars but did not recompute canonical payload digests. C1 would fail closed before DB/provider access, but the supervisor's own `reviewed=true` claim was not independently justified.
- **P1:** Runtime/source digests were checked before C0 only. Source could drift after C0 and before C1 start; repeat the clean commit, approved-file, calendar, and runtime identity checks immediately before both child starts.
- **P1:** C1 terminal verification did not bind execution authority, evidence-only state, session ID, C0 path/digest, and allowed terminal status tightly enough.
- **P1:** Installation-gate digest strings were not tied to actual reviewed files. Bind egress inventory, sandbox denial rehearsal, and automation-pause evidence as exact approved files.
- **P1:** Supervisor `COMPLETE` can be mistaken for a one-day Production Shadow Gate pass. Rename it `C1_TERMINAL`; keep `production_shadow_gate=NOT_PASSED` everywhere.
- **P1 fixed during review setup:** A lock contender initially targeted the active session's disposition directory and could block the owner. Contenders now write only under a separate immutable `lock_contenders/` root.
- **P2 fixed during review setup:** Child stdout/stderr files initially inherited umask modes. They now use exclusive no-follow `0600` opens.

### Round 2 — REQUEST CHANGES

- **P1:** Python's `subprocess.run(timeout=...)` automatically kills the direct child and can leave a grandchild alive. That conflicts with the design's no-automatic-SIGKILL and crash-retention rules. Replace it with explicit `Popen` supervision: C0 in one process group, SIGTERM-only timeout, retained pending state if grace expires, no C1 signal/timeout, and PID evidence.
- **P1 fixed during Round 2:** Bind the complete virtualenv tree and resolved interpreter path/digest, not only the dependency lock and venv symlink.
- **P1 fixed during Round 2:** Reject future-dated external approval and require review approval version, reviewer/time, RiskSnapshot provenance, attempt/review-packet binding, exact source filenames, and canonical bundle version.

### Round 3 — REQUEST CHANGES

- **P1:** Runtime identity transitively loaded the Shadow process adapter, giving input prepare/review code access to C0/C1 launch capability. Split exact read-only Git identity/status into a Git-only adapter; only the formal supervisor and existing C0 import the Shadow process adapter.

### Round 4 — REQUEST CHANGES

- **P1:** The digest-bound execution approval spec and sidecar were not owner-only. Require both to be regular, non-symlink, current-user `0600` files on every load and runtime recheck.

### Round 5 — REQUEST CHANGES

- **P1:** C0 internal child and Git timeout paths fell back to `communicate()` without a timeout after SIGTERM grace elapsed. Both helpers now use a separate process group, SIGTERM only, one bounded grace wait, and a termination-pending result without SIGKILL or another wait.
- **P2:** The design described C1 watchdog termination/liveness although the implementation deliberately has no C1 timeout or automatic signal. Align the state table and failure contract with recorded PID plus natural completion.

### Round 6 — APPROVE

- No unresolved P0/P1/P2 findings remain in the repository-only implementation scope.
- Exact entrypoint/argv, immutable retry, review promotion, owner-only approval/secret handling, runtime TOCTOU rechecks, process import boundaries, bounded pre-open termination, and C1 natural-completion semantics are covered by fixtures and static checks.
- Approval applies only to the uninstalled repository draft. Formal installation/execution remains blocked; Production Shadow Gate remains `NOT_PASSED`.
