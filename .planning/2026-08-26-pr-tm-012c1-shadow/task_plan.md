# Task Plan: PR-TM-012C1 Shadow evidence 2026-08-26

## Goal

Execute only the reviewed PR-TM-012C1 data-only/decision-only entrypoints for a complete trading-day evidence session, fail closed at every gate, and preserve immutable artifacts.

## Phases

1. [complete] Verify reviewed TWSE calendar and pre-open timing.
2. [complete] Inspect only required command bindings and existing reviewed daily inputs/DSNs.
3. [complete] Run one immutable C0 preflight attempt before 09:00; native SDK terminated before artifact persistence.
4. [complete] Do not start C1 because C0 is not READY and all four reviewed daily inputs are absent.
5. [complete] Inspect artifact targets, report NOT_PASSED, and update automation memory.
6. [complete] Diagnose repeated Python exit 139 without modifying code or execution settings.
7. [complete] Implement loopback capability detection plus native provider-preflight crash containment with explicit failure evidence.
8. [complete] Add focused regressions for denied bind, native exit, and successful worker payloads.
9. [complete] Run focused/static/full verification and real sandbox C0 regressions using new immutable outputs.
10. [complete] Record final disposition and update automation memory.
11. [complete] Stage only the verified crash-containment hunks, review the index, create one local commit, and verify its clean snapshot without push.
12. [complete] Audit next reviewed trading-day readiness without creating inputs or starting a partial session.
13. [complete] Inspect the existing automation configuration and leave it fail-closed for unresolved external prerequisites.
14. [complete] Audit official/local Codex sandbox controls and reject broad unattended sandbox bypass as unsafe.

## Hard boundaries

- No runtime code or daily input changes.
- No synthetic/partial/fake evidence or fallback runner.
- No order/fill/Position mutation, CA, trade callback, or execution capability.
- No interactive escalation; inaccessible DSN remains BLOCKED.

## Errors encountered

- C0 exited 139 at 08:49:17 during Shioaji provider preflight: `Could not bind to read inter-thread fd, error = Operation not permitted (1)`. Per automation policy, no retry or escalation was attempted.
- `pgrep` and `sort` are unavailable in this execution PATH during a final read-only check. Artifact existence checks completed before those utilities were reached; no command was retried.
- A first source-inspection command used an unmatched zsh glob; source inspection continued with explicit paths.
- `inspect.getfile(shioaji.Shioaji)` raised `TypeError` because `Shioaji` is a built-in class from the compiled extension. Package inspection continued through `_core.abi3.so` and its local metadata.
- A diff-summary loop used `path` as a zsh variable, which replaced zsh's command-search path and made `git`, `rg`, and `sed` unavailable inside that command. No state changed; subsequent inspection uses a non-special variable name.
- The first sandboxed partial-stage attempt could not create `.git/index.lock`; the user-requested commit required the managed Git-index permission path.
- An attempted interactive hunk edit failed because the PTY had no `EDITOR`. The hunk was discarded, then a test-only cached patch was applied and reviewed.
- The first partial-stage sequence briefly produced an incomplete cached provider dispatcher and two accidental prior hunks. Cached review caught this before commit; index-only reverse staging removed them, then the three missing fix hunks were added. Working-tree files were never reverted or overwritten.
- The first DSN-presence probe had shell/Python quote escaping that produced `SyntaxError`; retry with a smaller expression and no escaped f-string.
- The combined loopback probe stopped on the first uncaught TCP `PermissionError`; inspect TCP and UDP separately with explicit exception handling.
- Both read-only PostgreSQL probes returned redacted `OperationalError` through the current sandbox. No retry or escalation was attempted because the automation contract requires unattended fail-closed behavior.
