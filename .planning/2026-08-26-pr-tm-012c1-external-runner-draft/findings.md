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
- Phase 9 provisioned `/Users/stevehuang-work/.config/tw_intraday_trader_shadow/trade_management_shadow.env` as exclusive owner-only `0600`; safe metadata confirms exactly one API alias, one secret alias, separated DSNs, forced simulation, and no value disclosure.
- Phase 9 created the four dedicated `0700` state roots and rendered exact sandbox/plist candidates in the dedicated checkout. The plist remains disabled/uninstalled, the sandbox denies all network pending review, and all execution/gate flags remain false/`NOT_PASSED`.
- Filesystem read-back confirms the external config directory and all state roots are `0700`, the filtered environment is `0600`, and the rendered plist passes `plutil -lint`.
- Phase 9 rendered commit is `d7c26c0a76e7cb7d489ca63b60d789c4aac442d8`; worktree is clean. Runtime identity is `git:d7c26c0a76e7cb7d489ca63b60d789c4aac442d8:source-sha256:3ef1a621d659c3baacfe146793d52cd2b5457cf9a7c0dcea70bde3063f07a937`; venv tree remains `951ac42e...969e`, sandbox digest is `80531a4b...704`, and plist digest is `5602d2ff...4f1`.
- Initial text-only search found no Shioaji/Solace endpoint strings at the assumed site-packages path. Do not infer an empty egress inventory; resolve the actual uv venv layout and inspect locked package metadata/binaries without login.
- The actual package is under `.venv/lib/python3.12/site-packages/shioaji`; the initial `rg` respected `.venv` ignore rules. A no-login import attempted to create `shioaji.log` in the checkout, was denied by the current Codex filesystem boundary, and fell back to stdout. Formal sandbox rehearsal must confirm this source-write denial is nonfatal and does not expose secrets.
- The locked Shioaji 1.7.3 wheel contains a single compiled runtime module (`shioaji/_core.abi3.so`) plus Python facades; endpoint behavior is therefore not reviewable from Python source alone.
- A broad metadata scan was dominated by CycloneDX dependency URLs and again exceeded the output budget. Those are package provenance URLs, not proven provider egress destinations; endpoint discovery must isolate strings from `_core.abi3.so` and exclude SBOM metadata before any allowlist claim.
- Compiled-module strings confirm Shioaji contains remote site-configuration discovery, fallback Prod/Stag/VPN configuration, Solace transport, an `SJ_ADMIN_GATEWAY_URL` override, and an embedded private-address admin gateway. They do not expose a complete stable production hostname/port allowlist suitable for a sandbox profile.
- The first compiled-string filter also matched non-network API/order symbols and large static resources. Treat the observed URL fragments as discovery evidence only; do not copy opaque embedded tokens or infer that fallback/admin endpoints are the complete provider egress contract.
- The rendered sandbox permits only the pinned runtime Python targets and `/usr/bin/git`, read access to system/runtime/config inputs, writes to the four dedicated state subtrees, and explicitly denies all network pending endpoint review.
- The first `/usr/bin/sandbox-exec` rehearsal was itself rejected by the enclosing Codex sandbox (`sandbox_apply: Operation not permitted`, exit 71), before the candidate profile could evaluate `/usr/bin/true`. This is host-boundary evidence, not a pass or fail for the rendered profile; the same narrow command must be retried outside the enclosing sandbox.
- Host-level deny-exec rehearsal passed: candidate sandbox rejected non-allowlisted `/usr/bin/true` with `Operation not permitted` (exit 71).
- The first pinned-Python source-write rehearsal exited 134 with no stdout/stderr before reporting the expected denial. Do not classify source-write behavior from this result; isolate whether the deny-default profile lacks Python startup/Mach-service allowances before changing any profile.
- A fixed-output Python startup probe also exits 134 only inside the candidate sandbox, while the exact pinned interpreter starts normally outside it. The rendered profile is therefore not runnable as written; source-write, allowed-state-write, and network-denial probes cannot yet reach test code.
- macOS generated two Python crash reports for the rehearsal. The newest shows `SIGABRT` during dyld shared-cache discovery (`dyld4::CacheFinder` / `boot_boot`) before Python initialization, confirming a missing loader-level sandbox allowance rather than application code failure.
- Crash PID is 98287. A broad unified-log predicate produced unrelated host sandbox noise and was truncated before a reliable PID-specific denial could be isolated; no additional permission may be inferred from that output.
- A precise PID/time-bounded log query identifies the startup blockers: denied `sysctl-read` for `security.mac.lockdown_mode_state` and `kern.bootargs`, followed by denied `file-read-data /`. The crash frame and final denial support adding only root-path read data plus the two named read-only sysctls, then rerunning from a freshly rendered immutable profile.
- The current template has no root literal or sysctl allowance, and focused tests only assert deny-network/placeholder/header properties. Any fix requires explicit least-privilege assertions for the two named sysctls and root literal; it must not add wildcard sysctl or broader filesystem subpaths.
- The template now adds only `(literal "/")` for `file-read-data` and the two observed `sysctl-name` values. Tests explicitly reject root `subpath` and unrestricted `sysctl-read`; focused readiness tests pass (`8 passed`) and the two-file diff passes whitespace validation.
- The prior final readiness verification baseline was `42 passed` focused and `1659 passed, 65 skipped` full; rerun that broader baseline after the sandbox-startup correction before committing/cherry-picking a new runtime candidate.
- Post-correction verification matches the prior baseline exactly: focused readiness/supervisor suite `42 passed`; full current-worktree suite `1659 passed, 65 skipped`. No regression was introduced by the literal root-read/two-name sysctl allowances.
- Scoped main commit `1576bf6` contains only the sandbox-startup fix and test; dedicated runtime branch cherry-pick is `42c45ad`. The previously rendered profile remains preserved in parent commit `d7c26c0`, and the current candidate revision carries the deterministic seven-line rendered delta.
- Host-level pinned-Python startup now succeeds inside the corrected deny-default profile (`PYTHON_STARTED`, exit 0), validating that the three observed loader allowances are sufficient without broader filesystem/network/execution access.
- The first post-startup source-write command had invalid `python -c` newline quoting and exited with `SyntaxError`; it did not reach `os.open` and is excluded from denial evidence. The corrected harness attempts only a write descriptor on existing `pyproject.toml`, performs no write, and passes with `SOURCE_WRITE_DENIED` (exit 0).
- A fixed-IP, two-second TCP connect probe passes with `NETWORK_DENIED` (exit 0); it does not perform DNS, provider login, or order/trade activity.
- An exclusive-create probe under the dedicated `0700` state `tmp` root passes with `STATE_WRITE_ALLOWED` and leaves `sandbox_allowed_write_probe_v2.txt` as a bounded runtime-write artifact. This confirms the corrected profile remains usable only inside the intended write subtree.
- Corrected-profile revalidation still rejects non-allowlisted `/usr/bin/true` (exit 71) and rejects opening the repository `.env` outside the one allowlisted owner-only secret path (`NONAPPROVED_READ_DENIED`, exit 0); no secret bytes were read or printed.
- macOS sandbox process rules match executable paths, not argv. Because the pinned Python executable must be allowed, `python -c` is also technically launchable under the profile; the fixed disabled plist and supervisor constrain the installed path but cannot prove OS-level generic-Python denial. Record this as an installation blocker rather than claiming Phase 10 complete.
- Current corrected sandbox digest is `25b927c...a86b`; plist remains `5602d2ff...4f1`; Shioaji core binary digest is `931ae62a...04f3`; lock digest remains `a58d39fb...5896`. Config/state directories remain owner-only and the secret file remains `0600`.
- The positive-write probe was created with default mode `0644` inside a `0700` directory. Although inaccessible to other users through that directory, it is not suitable as an owner-only evidence file; normalize this exact probe to `0600` before citing it. The enclosing Codex sandbox rejected the first chmod, so retry only the exact path at host level.
- The exact positive-write probe was normalized to `0600` without content change. Dedicated runtime focused regression passes `42 passed`; the sole warning is expected outer-Codex denial of `.pytest_cache` writes in the external checkout and does not affect test results or source state.
- The corrected rendered profile is committed alone as dedicated runtime commit `d828979ef0e01a73393910a2d81931983ca4cc66`; the worktree is clean. An initial identity helper call supplied an obsolete positional path and failed before producing identity; rerun the current zero-argument API from the pinned checkout.
- Final corrected candidate runtime identity is `git:d828979ef0e01a73393910a2d81931983ca4cc66:source-sha256:3ef1a621d659c3baacfe146793d52cd2b5457cf9a7c0dcea70bde3063f07a937`. The source digest remains stable because the runtime identity intentionally covers execution code, while the approval template separately binds sandbox/plist/evidence digests.
- The approval template requires immutable provider-egress and sandbox-rehearsal JSON files, but the current findings force both the approval and installation gates to remain `NOT_APPROVED`/blocked; no placeholder digest may be replaced by an approval claim.
- Sanitized parsing of the provisioned env reveals both DSNs are unresolved quoted `${PostgreSQL_DSN}` expressions, not usable URLs. They compare unequal only because the Shadow form appends parameters; the earlier `dsn_separation_verified=true` result was insufficient and must be withdrawn for this target.
- Root cause: readiness provisioning deliberately calls `dotenv_values(..., interpolate=False)`, filters out the base `PostgreSQL_DSN`, then validates only non-empty/distinct strings. Tests cover literal DSNs but not source-local variable references. Fix must resolve only source dotenv references before allowlist filtering, validate final URLs, and never add base/helper variables to the child environment or result payload.
- On the actual source `.env`, python-dotenv interpolation resolves both DSNs to PostgreSQL URLs with host/database/port present and no remaining `${...}` reference, without printing values. This supports using the library's reviewed interpolation behavior before filtering.
- Prior validation checked only presence/string inequality. The fix admits only a PostgreSQL scheme, hostname, valid optional port, no unresolved variable token, and distinct final DSNs; it keeps database defaults and query parameters valid because the dedicated Shadow schema may be bound through PostgreSQL options and is verified by formal preflight.
- DSN remediation review Round 1: `APPROVE`. The implementation resolves references from the parsed source mapping only, detects cycles/unresolved or unsupported forms with non-secret error codes, validates the final PostgreSQL scheme/host/port, filters helper keys from output, and leaves connectivity/schema proof to the formal preflight rather than attempting it during provisioning.
- `dsn_separation_verified` is consumed only as readiness metadata in this builder; the formal adapter independently rechecks literal separation and the C0 preflight remains responsible for actual connectivity/schema. No code path treats provisioning alone as C0 readiness or approval.
- Post-fix full current-worktree suite result is `1671 passed, 65 skipped, 2 failed`. Both failures are unrelated concurrent migration-list expectations that stop at migration 015 while an untracked/adjacent migration 016 is present; no readiness/external-supervisor test failed. Focused scope remains `45 passed`.
- Scoped DSN remediation commit is main `39431a8`, cherry-picked to the dedicated runtime branch as `d2af445`. The reviewed entrypoint created a new immutable `trade_management_shadow_v2.env` rather than overwriting broken v1; it reports exactly five allowlisted keys, one provider API/secret alias, forced simulation, `0600`, and no value disclosure.
- Sanitized v2 read-back confirms both final values are actual `postgresql` URLs at `localhost:5090`, database `tw_intraday_trader`, no remaining variable reference, distinct DSN digests, and file mode `0600`. Connectivity/schema are still unproven until formal preflight.
- The rendered plist does not directly name the environment file; it names only the future approval spec. The sandbox read allowlist has been updated from immutable v1 to v2, while the old env and old rendered version remain preserved for audit.
- Host-level sandbox v2 binding passes: it can read v2 and validate the exact five keys, resolved references, distinct DSNs, and `SJ_SIMULATION=true` while emitting only `V2_ENV_BOUND_AND_VALID`; it denies even opening the old v1 path and emits `V1_ENV_READ_DENIED`.
- Final v2 sandbox binding commit is `9ee72a11876ed15dab19d7362c338f76c78b72e8`; dedicated worktree is clean. Runtime identity is `git:9ee72a11876ed15dab19d7362c338f76c78b72e8:source-sha256:2dba738559fa24b6ecddd5db9084017975604f8c9e03b7ea174dfdf1addd202b`.
- Current binding digests: sandbox `596d94ab...89e5`, plist `5602d2ff...4f1`, lock `a58d39fb...5896`, pinned/resolved Python both `64808b3b...8276`, owner-only v2 env `77012d2a...842b`, Shioaji core `931ae62a...04f3`, and positive-write probe `80f0b0da...c0c`.
- The first venv digest helper call used a relative path and correctly failed `ABSOLUTE_PATH_REQUIRED`; the corrected absolute-path call reports the unchanged venv tree digest `951ac42e...969e`.
- Evidence capture timestamp is `2026-08-26T14:10:25+08:00`. Sanitized query inspection shows Local Paper has no query override while Shadow has a single `dbname` query key; neither uses a `search_path` option. Validate the `dbname` override as a safe identifier before describing schema/database separation.
- The Shadow `dbname` override is the safe identifier `tw_intraday_trader_shadow` (SHA-256 `53765799...3624`) and occurs exactly once, while Local Paper resolves to base database `tw_intraday_trader`. This proves configured database separation without disclosing credentials; connection availability remains unproven.
- `architecture/deployment/review_evidence/` does not yet exist in the dedicated checkout. Add only truthful blocked inventory/rehearsal artifacts; do not create automation-pause evidence or an approval spec while installation eligibility is false.
- Added two untracked candidate evidence JSON files. Structural assertions pass: both are `BLOCKED`, unreviewed, installation-ineligible, execution-disabled, and Gate `NOT_PASSED`; provider allowlist is empty; sandbox artifact includes exactly one explicit generic-Python failure.
- Ordinary `git diff` does not display these untracked artifacts, so final review must inspect their complete parsed content and staged diff before commit; no approval spec or automation-pause artifact exists.
- Exact final-profile revalidation has begun because equivalence to the prior env-literal revision is not sufficient evidence. Commit `9ee72a1` again rejects `/usr/bin/true` (exit 71) and source write-descriptor access (exit 0, `SOURCE_WRITE_DENIED`).
- Exact final profile also returns `NETWORK_DENIED` for the fixed-IP TCP probe and creates a new bounded state marker using `O_EXCL` with descriptor-verified `0600` (`STATE_WRITE_ALLOWED_0600`). Replace the earlier v2 probe binding in evidence with this exact-profile v3 artifact.
- Exact final profile again denies opening the repository `.env` without reading bytes. The v3 positive-write artifact is owner-only `0600` with SHA-256 `7cd39689...61c2`.
- Evidence review Round 1 requested one binding correction: prior explicit `PYTHON_STARTED` predated the v2 literal revision. The exact final profile now also returns `PYTHON_STARTED` (exit 0), so every retained PASS result is directly exercised on sandbox digest `596d94ab...89e5`.
- Evidence review Round 2: `APPROVE` for truthful blocked evidence. Both JSON artifacts distinguish the candidate base commit from their future containing commit, disclose excluded attempts, retain the generic-Python failure/provider allowlist blocker, and make no approval, installation, execution, connectivity, or Production Gate claim.
- Blocked evidence commit is `15a852cc15734051ea0ce6dc6b149af5a0c1f7d2`; dedicated worktree is clean. Final runtime identity is `git:15a852cc15734051ea0ce6dc6b149af5a0c1f7d2:source-sha256:2dba738559fa24b6ecddd5db9084017975604f8c9e03b7ea174dfdf1addd202b`.
- Final evidence digests are provider inventory `38e48631...d686` and sandbox rehearsal `eedd898f...e58`; sandbox/plist digests remain `596d94ab...89e5` and `5602d2ff...4f1`.
- Final read-back at `2026-08-26T14:17:56+08:00` confirms the existing automation is still `ACTIVE`, weekdays 08:35, targets the original project checkout, and retains the full safety prompt; it was intentionally not mutated because installation eligibility is false.
- The canonical `session_inputs/2026-08-27/` directory remains absent. The only draft packet remains `PENDING_REVIEW`, `formal_c1_eligible=false`, and unbound. Current time is outside pre-open, so formal item 8 is independently blocked even apart from sandbox/egress blockers.

## Native launcher and provider-contract continuation

- User authorized the next gated stage. Scope is a repository-only native fixed-launcher candidate plus official/locked-package provider-contract research; no installation, automation mutation, provider login, C0, or C1 is authorized by this continuation.
- Architecture boundary hypothesis to validate: a native executable can embed the pinned CPython runtime and set one fixed supervisor argv without permitting the standalone Python executable in the sandbox. Reject the approach if the pinned runtime lacks a reviewable shared-library/embed toolchain or if any pre-sandbox execution gap remains.
- Provider egress remains fail-closed: only primary official documentation and locked package evidence may inform the inventory; absence of a complete hostname/port contract keeps the allowlist empty.
- Review routing for this stage includes the complete C, architecture, security, and universal-quality guides because the candidate crosses native embedding, executable identity, secret access, and sandbox boundaries. Success requires a surgical fixed-argv design with no new trading/provider capability.
- Architecture constraint from the selected skill: keep the native launcher as a single infrastructure adapter with one responsibility, while the existing Python supervisor remains the application core. Do not move calendar, DSN, provider, or trading rules into C.
- Review method is severity-first and test-driven: executable/argv bypass, pre-sandbox code paths, environment leakage, dynamic loader search, memory/UB, TOCTOU, and artifact identity are blocking; formatting and unrelated migrations remain outside scope.
- Native launcher acceptance additionally requires warnings-as-errors, sanitizer coverage where compatible with embedded CPython, checked return codes, explicit resource ownership, no unbounded copies/formatting, no secret-bearing errors, and an immutable build recipe bound to the pinned Python headers/library.
- The launcher must not become a second supervisor or configurable command runner: no user paths, flags, shell, environment expansion, child argv passthrough, or optional modes. Any reusable helper must already exist or be justified by a concrete duplicate.
- TOCTOU rule for native admission: verify the executable/build artifacts by file descriptor or immutable digest at the approval boundary; do not check a path and later load a replaceable binary/library from that path without revalidation.
## Phase 14 native fixed-launcher feasibility (2026-08-26)

- The pinned CPython distribution is embedding-capable in principle:
  - root: `/Users/stevehuang-work/.local/share/uv/python/cpython-3.12.6-macos-aarch64-none`
  - `include/python3.12/Python.h` exists;
  - `lib/libpython3.12.dylib` exists;
  - `bin/python3.12-config --embed` is available;
  - Apple clang 17.0.0 targets arm64.
- `python3.12-config --embed --ldflags` emits `-lpython3.12` but does not emit the pinned distribution's `lib` search path. Any accepted build recipe would therefore need an explicit, digest-bound library path/rpath and a post-link `otool -L` verification; relying on ambient linker or loader search would be fail-open.
- A single native wrapper around `run_trade_management_shadow_external_supervisor.py` does not yet establish the requested execution boundary. The existing supervisor delegates C0/C1 to `spec.python_executable`, and the preflight path may itself launch additional Python processes (provider worker and focused tests). If Python remains admitted by the same sandbox profile, arbitrary Python argv remains available; if Python is removed, the reviewed process graph no longer runs.
- Therefore implementation is gated on proving that the complete existing child-process graph can remain unchanged while every Python invocation is fixed-purpose. Replacing subprocess boundaries with embedded/in-process execution, rewriting C0/C1, or adding broad multi-role native wrappers would exceed the narrow repository-only launcher scope and risk changing reviewed semantics.
- The source confirms four separate Python child roles under the formal path:
  1. supervisor -> `python scripts/preflight_trade_management_shadow.py` (C0);
  2. C0 -> `python scripts/preflight_trade_management_shadow.py --provider-preflight-worker`;
  3. C0 -> `python -m pytest -q <five exact rehearsal targets>`;
  4. after C0 readiness, supervisor -> `python scripts/run_trade_management_shadow_c1.py` (C1).
- Application-level argv checks in `runtime/trade_management_external_process.py` are useful defense-in-depth but do not constrain a separately invoked allowlisted Python executable. The macOS sandbox profile filters executable paths rather than Python argv, so keeping the interpreter admitted permits an independent generic interpreter process in the same profile.
- The readiness builder and approval binding explicitly require both `.venv/bin/python` and its resolved interpreter. A one-file outer launcher would therefore require coordinated changes to readiness, rendered launchd arguments, approval schema, sandbox execution rules, and all four Python child roles to claim closure. That is not the proposed narrow adapter.
- Feasibility conclusion for the single outer embedded-launcher hypothesis: **REJECTED / BLOCKED**. The embedding toolchain is available, but the candidate does not eliminate generic Python capability across the reviewed C0/C1 process graph. No native launcher implementation should be started under the current scope.

## Phase 16 official provider egress contract research (2026-08-26)

- Official Shioaji login documentation demonstrates that login establishes a Solace market-data connection and shows a redacted/dynamic `<IP>:80` in example output. It documents neither a stable hostname set nor a complete simulation-environment endpoint inventory suitable for a literal sandbox allowlist.
- Official callback documentation confirms Solace is the message broker and discusses session reconnect behavior, but does not publish the broker hostname/IP contract or all required ports.
- Official simulation documentation enumerates supported APIs, not network endpoints. The local HTTP server documentation (`127.0.0.1:8080`) describes the optional Shioaji server surface and is not a contract for the native Python client's upstream authentication, contracts, and quote connections.
- The locked Shioaji installation exposes its runtime core as `shioaji/_core.abi3.so`. A text search of the installed package yielded no reviewable endpoint manifest. Extracting incidental strings or observing one connection would not establish a complete, stable official contract and must not be promoted to an allowlist.
- Current conclusion: official/locked-package evidence is insufficient for a complete hostname/port allowlist. Provider egress must remain empty and Phase 10/12 installation eligibility remains `BLOCKED`.
- A second official-source search found no Shioaji firewall/egress specification. Official repository and docs describe product behavior, while endpoint-specific search results do not provide an authoritative allowlist.
- Locked package version is `shioaji==1.7.3`, installed by `uv`, with the previously recorded `_core.abi3.so` digest. Binary inspection shows that the core can fetch site information remotely, fall back among environment configurations, and accept admin URL/Solace overrides. Incidental embedded URLs, fallback values, or one observed redirect are implementation details, not a promised complete endpoint contract; using them would create a brittle and potentially incomplete egress allowlist.
- The provider blocker is therefore architectural rather than a missing local grep: endpoint discovery is dynamic inside a compiled core, while the proposed sandbox policy requires a static, complete, reviewable destination contract.

## Phase 14–16 adversarial re-review

- Scoped whitespace validation passes and the documentation diff is limited to the external execution design/checklist plus this phase's planning records.
- Security review found no execution-capability expansion: the sandbox template still admits the existing interpreter and Git only, still denies all network, and the plist remains disabled/unapproved.
- Consistency review confirms the design now distinguishes the required fixed-executable/argv boundary from the current application-level Python checks, and explicitly prevents a supervisor-only wrapper from being counted as closure.
- Evidence-quality review confirms official documentation and locked-package inspection are used only to support an insufficiency finding. No incidental endpoint, binary string, single-session observation, or local HTTP listener is promoted to a provider allowlist.
- Final review decision: **APPROVE** for the truthful documentation-only `BLOCKED` disposition. This is not approval to implement a broader launcher, create an installation approval spec, pause automation, install/enable launchd, connect the provider, or execute C0/C1.

## Phase 14–16 independent re-review remediation

- Independent re-review Round 1 decision: `REQUEST CHANGES` with one P1 and three P2 findings: the plan overstated nonexistent launcher identity completion, installation state used ambiguous `BLOCKED FOR REVIEW`, official-source provenance was not durable in the repository, and the child-role count said three while enumerating four.
- Remediation is documentation-only: describe identity requirements rather than nonexistent artifacts, use `BLOCKED — INSTALLATION INELIGIBLE`, bind the three official URLs plus retrieval date and compiled-core digest without changing immutable inventory, and state four child roles.
- No runtime, sandbox artifact, provider inventory, automation, approval spec, provider connection, C0, or C1 mutation is part of this remediation.
- Independent re-review Round 2 decision: **APPROVE** for the scoped documentation remediation. All four findings are resolved, no new P0/P1/P2 was found, and formal installation/execution eligibility remains false.
