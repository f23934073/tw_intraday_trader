# Task Plan: PR-TM-012C1 Shadow evidence 2026-08-27

## Goal

Execute only the reviewed PR-TM-012C1 data-only/decision-only entrypoints for a complete trading-day evidence session, fail closed at every gate, and preserve immutable artifacts.

## Phases

1. [complete] Verify reviewed TWSE calendar, current time, reviewed daily inputs, DSN names, and immutable output availability.
2. [complete] Run exactly one new immutable C0 preflight before 09:00; it persisted BLOCKED evidence with exit 2.
3. [complete] Do not start C1 because C0 is not READY_FOR_SESSION and canonical reviewed inputs are absent.
4. [complete] Preserve the terminal C0 artifact, verify digests, confirm no C1 artifact, and keep Production Shadow Gate NOT_PASSED.
5. [complete] Update automation memory with the run result and current time.

## Hard boundaries

- No runtime, policy, daily-input, database, or evidence edits outside reviewed entrypoints.
- No synthetic, partial, fake, or fallback evidence.
- No order/fill/matching/Position mutation, broker order API, CA, trade callback, or execution capability.
- No interactive escalation; inaccessible sandbox or DSN remains BLOCKED.
- Do not retry a failed formal command unless a later user request explicitly authorizes a new immutable attempt.

## Errors encountered

- The read-only input inventory returned exit 2 because canonical `session_inputs/2026-08-27/` does not exist; the legacy draft packet exists but is not C1-eligible.
- The read-only output inventory returned exit 1 because the intended new C0/C1 artifacts do not yet exist; this confirms immutable target availability.
- Formal C0 exited 2 with `LOOPBACK_BIND_DENIED` and PostgreSQL `OPERATIONALERROR`; these are retained blockers and were not retried or escalated.
- The post-run C1-path inventory returned exit 1 because no C1 artifact exists, as required after C0 blocked.
