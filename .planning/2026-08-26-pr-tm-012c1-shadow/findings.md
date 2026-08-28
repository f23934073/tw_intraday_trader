# Findings: PR-TM-012C1 Shadow evidence 2026-08-26

- Prior automation memory reports the reviewed C1 entrypoint was implemented after the 2026-08-25 session.
- Current repository state is dirty with concurrent user work; the C0 runtime identity must bind current source content without modifying it.
- Calendar, daily inputs, DSN separation, C0 seal, and the pre-open connection window remain hard gates.
- Reviewed `twse_calendar_2026_v1` covers 2026-08-26; it is a weekday and is absent from both closure lists, so today is a reviewed trading day. Calendar SHA-256 is `1671338c8247f7f5344657912f469fce111b82b9be0dea1d61d21eb6d3a3593a`.
- `.env` declares non-empty `LOCAL_PAPER_DATABASE_URL` and `TRADE_MANAGEMENT_SHADOW_DATABASE_URL` names; values were not printed.
- All four required reviewed inputs are absent under `research/trade_management_shadow/session_inputs/2026-08-26/`. This is a hard C1 blocker and must not be repaired during the run.
- The reviewed C0 command was invoked exactly once before open. Shioaji's native SDK exited the process with code 139 before the script could persist its exclusive artifact or sidecar.
- Both intended C0 paths and both anticipated C1 paths were confirmed absent. No failure artifact was manufactured after the native crash.
- PostgreSQL readiness, provider identity, rehearsal, journal/event/decision counts, lost evidence, replay parity, and recovery are all unavailable rather than passing.
- C1 was not invoked. Production Shadow Gate remains `NOT_PASSED`.

## Exit 139 diagnosis at 08:52-08:54

- `import shioaji` succeeds under Python 3.13.5; installed Shioaji version is 1.7.2.
- A minimal process that only imports Shioaji and executes `sj.Shioaji(simulation=True)` reproduces exit 139 before `login()`.
- A Unix `socketpair()` succeeds in the same sandbox, but both TCP and UDP `AF_INET` binds to `127.0.0.1:0` fail with `PermissionError: [Errno 1] Operation not permitted`.
- Shioaji's `Shioaji` class is implemented by the native ARM64 `_core.abi3.so`. Embedded strings identify the `rsolace`/Solace client and its inter-thread CMD pipe; the exact native diagnostic is `Could not bind to read inter-thread fd`.
- macOS crash report `Python-2026-08-26-084919.ips` records `EXC_BAD_ACCESS`, `SIGSEGV`, `KERN_INVALID_ADDRESS at 0x10`, with the faulting main-thread frames inside `_core.abi3.so`.
- Root cause: the Codex sandbox rejects the loopback bind required by Solace initialization. Secondary native defect: Shioaji/Solace 1.7.2 does not fail safely after the denied bind and instead dereferences invalid state, terminating Python with SIGSEGV.
- Repository `connect_from_env()` reaches `sj.Shioaji(...)` before `api.login()`. The C0 provider guard catches Python `Exception`, but cannot catch a native SIGSEGV. PostgreSQL preflight and rehearsal are ordered later and were never reached.
- This is not caused by credentials, DSN, daily inputs, login response, order/trade subscription, or retry/session naming.

## Fix scope

- Repository code cannot grant the Codex process loopback-bind permission. The safe in-repo fix is to isolate Shioaji initialization in a child process, convert abnormal native termination into typed provider-preflight evidence, and keep all readiness gates fail closed.
- A Python-only `try/except` is insufficient because SIGSEGV terminates the interpreter. Retrying the constructor in-process would repeat the crash.
- Success requires both unit coverage and a real sandbox C0 regression that persists an immutable `BLOCKED` artifact instead of exiting 139.
- First postfix diagnostic at 09:01:47 confirms subprocess containment works: the parent returned normal exit 2 and persisted `premarket_20260826_postfix_diagnostic.json` with provider `error_code=NATIVE_SIGNAL_11`.
- Diagnostic artifact SHA-256 is `907904be24dd06fadd34587856edcb1b14b14961640ccf53a44f85fa1a32156b`; readiness digest sidecar is `f785bf1b937f552b9223b20e6db487c239aae55f6329723659158166cfa1666d`.
- Rehearsal passed all five checks; PostgreSQL remained blocked with `OPERATIONALERROR`, and the post-open diagnostic correctly also reported `SESSION_WINDOW_NOT_FUTURE`. Production gate remained `NOT_PASSED`.
- A parent-side loopback bind capability probe can avoid even launching the native worker in this known-incompatible sandbox; subprocess containment should remain as defense against other native crashes.
- Second postfix diagnostic at 09:03:48 verified the complete fix: no SDK error, no exit 139, and no new macOS Python crash report. The parent persisted `provider_preflight.error_code=LOOPBACK_BIND_DENIED` and retained `subscribe_trade=false`.
- V2 diagnostic artifact SHA-256 is `d95689a1253f0c5ed68c7cd97fe8bf8d94a6b1362c81b003aeece077716d80c1`; readiness digest sidecar is `191544391f15744e102e7c5efd000c46ac89fa333727e5a500aa2f5cfe5b4856`.
- Focused premarket tests pass 18/18; combined TM premarket/C1/operation/replay/validation regression passes 55/55. Python compilation and scoped whitespace validation pass.
- Full repository regression passes `1490 passed, 57 skipped`; final scoped `git diff --check` passes.
- Before commit packaging, the fix was uncommitted; existing concurrent modifications in the same three files were preserved and no unrelated file was cleaned or reverted.
- Commit `7f69504` (`fix(shadow): contain native provider preflight crashes`) contains exactly the fix-only three-file payload. The Git index is clean afterward; prior and unrelated working-tree changes remain present and unstaged.
- A clean detached worktree at commit `7f69504` passed `tests/test_trade_management_premarket.py` with `13 passed`. The temporary worktree was removed after verification.

## Next-session readiness after C1 commit

- Commit `9abc89f` now contains the complete reviewed C1 runtime; its clean snapshot passed 49 focused tests and the full `1443 passed, 57 skipped` suite.
- The reviewed calendar identifies 2026-08-27 as the next trading day under the same `twse_calendar_2026_v1` digest.
- All four required reviewed files are absent from `research/trade_management_shadow/session_inputs/2026-08-27/`; they must not be generated or inferred by the automation.
- A current sandbox TCP loopback bind probe still fails with `PermissionError`, so the fixed C0 will safely persist `LOOPBACK_BIND_DENIED` unless the automation runs in an environment with the required local capability.
- `.env` contains both explicit DSNs and they are distinct, but both resolve to loopback endpoints. Read-only connection attempts to each returned `OperationalError` in the current unattended sandbox.
- UDP loopback bind is also denied. Moving only PostgreSQL to a reachable host would not resolve the Shioaji/Solace requirement; the C0 execution environment itself must permit TCP and UDP loopback bind.
- The existing automation is already `ACTIVE`, runs weekdays at 08:35 with `execution_environment=local`, targets this project, and retains the reviewed data-only prompt. It was inspected through the Codex automation UI and left unchanged.
- Next-session readiness is therefore blocked by two external prerequisites: a human-reviewed 2026-08-27 input bundle and an approved unattended execution environment that can access both DSNs and satisfy Shioaji loopback IPC.
- Official OpenAI documentation search did not expose an automation-specific setting that grants local loopback bind permission. The documented container network policy applies to API containers, not this Codex desktop cron execution, so it is not evidence that the current automation can be reconfigured through its prompt or `automation.toml`.
- Local Codex CLI `0.148.0-alpha.15` confirms the effective environment is `filesystem sandbox=restricted` and `network sandbox=restricted`; `codex doctor --json` also reproduces external reachability failures. The automation prompt cannot override those host capabilities.
- CLI help exposes only broad sandbox modes (`read-only`, `workspace-write`, `danger-full-access`) and explicitly labels bypassing approvals/sandbox as extremely dangerous. That broad bypass is not an acceptable unattended fix for a production evidence automation.
- `codex sandbox` supports named permission profiles and AF_UNIX socket allowances, but its visible interface has no targeted AF_INET loopback-bind flag. No safe automation-specific profile is currently configured in `~/.codex/config.toml`.
