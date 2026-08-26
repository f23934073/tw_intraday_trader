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

## Installation-readiness continuation

- Commit `19d4489bceab9e2cf06c12d31acf32e454428dd7` contains the approved repository-only external runner draft; it was not pushed.
- The continuation authorizes items 1–8 as a gated sequence, not as permission to bypass missing secrets, review approval, sandbox denial evidence, market calendar/window, or canonical-input checks.
- The supported Codex automation API is available. Existing automation state must be inspected before any update, and any pause/monitor conversion must be read back rather than inferred.
- The main checkout remains concurrently dirty and cannot serve as the formal runtime checkout.
- Live Phase 6 audit confirms `main` is ahead of `origin/main` and extensively dirty; the committed external-runner target must be addressed by exact local commit SHA, not the remote branch tip or current worktree state.
- The reviewed `twse_calendar_2026_v1` calendar marks both 2026-08-26 and 2026-08-27 as trading days. This establishes calendar coverage only; it does not authorize an out-of-window run.
- No supported dependency lock exists; only `pyproject.toml` is present. Phase 8 cannot claim a reviewed/frozen dependency graph until a lock artifact is deliberately produced and reviewed.
- The canonical `session_inputs/2026-08-27/` directory is absent. Only the immutable draft review packet and sidecar exist under `session_input_drafts/2026-08-27/`; item 8 is currently ineligible and no promotion may be inferred.
- The 2026-08-27 draft packet is explicitly `PENDING_REVIEW`, `formal_c1_eligible=false`, has no binding, and lists all four canonical sources as missing. It is bound to older runtime commit `9abc89f...`, not the external-runner commit.
- `uv` is installed locally. The current `.venv` has exact broker/dev/PostgreSQL packages but is an editable install bound to the dirty source checkout, so its `pip freeze` can inform review but cannot itself serve as the formal immutable runtime.
- The proposed external checkout/config/state roots do not yet exist. The repository `.env` is source-local and mode `0644`, so it is formally inadmissible and must not be referenced by the rendered service.
- The existing `pr-tm-012c1-shadow` automation is `ACTIVE`, weekday 08:35, and still targets the dirty project checkout. It must remain unchanged until the external package is otherwise installation-eligible, then be paused or converted to monitor-only with read-back evidence before enabling any external collector.
- `/usr/bin/sandbox-exec` is available on this host, so a rendered denial rehearsal is technically possible after the clean runtime and profiles exist.
- The repository `.env` contains the required provider credential aliases and both named DSNs, but also unrelated keys and no explicit `SJ_SIMULATION`. It cannot be copied wholesale because formal child-environment admission rejects unknown non-empty keys; provisioning must filter only the allowlisted keys, force simulation, avoid printing values, and write a new exclusive `0600` file.
- The Phase 6 clock was 2026-08-26 13:25 Asia/Taipei, outside the pre-open window. No same-day formal C0/C1 attempt is allowed.
- Freeze proposed paths as `/Users/stevehuang-work/.local/share/tw_intraday_trader_shadow/runtime_checkout`, `/Users/stevehuang-work/.config/tw_intraday_trader_shadow`, and `/Users/stevehuang-work/.local/state/tw_intraday_trader_shadow/{artifacts,records,locks}`. None currently exists.
- Phase 7 created branch `codex/pr-tm-012c1-runtime-readiness-20260826` in the dedicated runtime worktree, starting exactly at `19d4489bceab9e2cf06c12d31acf32e454428dd7`. Git status is clean and no checkout `.env` exists.
- Phase 8 toolchain inventory: `uv 0.7.21` and system `Python 3.13.5`; the project declares Python `>=3.11`. The lock must preserve all broker/dev/PostgreSQL optional groups for formal C0/C1 validation.
- `uv lock --offline` succeeded from cache, selected available CPython 3.12.6 for resolution, and produced one untracked `uv.lock` with `requires-python = ">=3.11"` and registry hashes. It did not install packages or contact provider/DSNs.
- The lock explicitly contains the broker, dev, and PostgreSQL optional groups and all required packages. An external-sandbox `uv lock --check --offline` passed; the earlier failure was only Codex sandbox denial on uv cache metadata.
- The first online frozen sync installed the local project editable and changed tracked `tw_intraday_trader.egg-info/SOURCES.txt`. That violates clean-source admission, so the candidate venv is rejected until rebuilt with `--no-install-project` and the generated tracked change is removed.
- The venv was corrected with frozen/offline `--no-install-project`; the editable package was removed and only the known generated egg-info change was restored. Runtime entrypoints will import the pinned checkout from their fixed working directory.
- The clean runtime full suite produced `1566 passed, 61 skipped, 1 failed`. The sole failure is an unrelated price-coverage immutable artifact whose recorded `historical_download.py` digest matches later dirty-worktree work, not commit `19d4489`. Do not absorb that unrelated source change into the Shadow runtime branch without its own reviewed commit.
- The exact five frozen C0 rehearsal targets plus external-runner fixtures pass (`72 passed`) under the new isolated venv. Git status shows only the intended untracked `uv.lock`; its SHA-256 is `a58d39fb152db89f2710243b8f39032fc389c7c5a1fcec23d7afdafb888a5896`.
- The isolated venv tree SHA-256 is `951ac42e15f4dff23204fef3f0fc501e388463f96d573f44ee89bbfb93bc969e`. Staged scope is exactly one new `uv.lock`, and its cached diff passes whitespace validation.
- Phase 8 committed only `uv.lock` as `63bfe56ad8cbf54bacc84100aa1cf81bc12b8d96`; the worktree is clean. Runtime identity is `git:63bfe56ad8cbf54bacc84100aa1cf81bc12b8d96:source-sha256:e23061cb6625f944ca22019414bd5c3461d02da0c159f42e969162b1395cc45c`.
- No existing repository entrypoint provisions the filtered owner-only environment or renders the deployment/approval package. A reviewed narrow readiness builder is required; ad hoc shell filtering or manual digest editing would be non-reviewable and risks secret disclosure.
- The new readiness boundary has no subprocess/provider/DB/trading imports. It writes only exclusive owner-only environment/runtime paths and disabled/deny-network deployment candidates; focused tests pass (`41 passed`) and the current main worktree full suite passes (`1658 passed, 65 skipped`).
- Final readiness review applies security-first checks for secret/log leakage, command/path injection, symlink and TOCTOU behavior, least privilege, lockfile provenance, and exact disabled deployment arguments; architectural review keeps the core filesystem-only and the CLI thin.
- Static boundary scan finds no subprocess, provider, DB, order, CA, or trade-subscription capability in the readiness module/CLI. The tracked template diff is limited to binding a dedicated owner-only `TMPDIR`; direct review of the new untracked files remains required because ordinary `git diff` does not display them.
- Readiness review Round 1 decision: `REQUEST CHANGES`. **P1:** raw absolute paths are substituted into sandbox string literals; paths containing quotes, backslashes, newlines, or NUL could alter profile syntax. Reject unsafe sandbox path characters before rendering and verify the resolved interpreter target as a regular non-symlink file.
- Readiness review Round 2 decision: `REQUEST CHANGES`. **P1:** provisioning requested mode `0600` but did not verify the opened descriptor's actual owner/mode before reporting success. Add `fstat` verification and retain an empty immutable target on mismatch rather than claiming readiness.
- Readiness review Round 3 decision: `APPROVE` for the builder scope. No unresolved P0/P1/P2 remains after sandbox-literal path rejection, resolved-interpreter validation, descriptor owner/mode verification, partial-write handling, immutable targets, exact plist argv, deny-network enforcement, and no-execution import checks.
