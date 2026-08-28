# Findings: PR-TM-012C1 next-session preparation

## Authorized scope

- Implement a 2026-08-27 input draft workflow; outputs must remain pending review and must not masquerade as reviewed evidence.
- Design an external-sandbox local execution path that uses only existing C0/C1 entrypoints; submit it for review without installation or activation.
- Preserve all data-only/decision-only and no-order/no-fill/no-Position/no-CA/no-trade-callback boundaries.

## Starting blockers

- The four canonical 2026-08-27 input files do not exist.
- Both explicit PostgreSQL DSNs are distinct but loopback-based and inaccessible in the current sandbox.
- TCP and UDP loopback bind are denied, so Shioaji/Solace cannot initialize in the current automation environment.
- Automation `pr-tm-012c1-shadow` is already active at 08:35 and must remain unchanged during design review.

## Source audit

- No repository JSON artifact currently supplies a LiveEntryDecision, TradeThesisDraft, Shadow policy, or RiskSnapshot candidate for 2026-08-27.
- The repository has canonical serializers/deserializers for EntryDecision and Draft, plus the C1 policy/Risk loaders, so a preparation workflow can validate caller-supplied files without inventing domain values.
- Because there is no legitimate decision source, this task must not emit four syntactically valid trading inputs from test fixtures or defaults. The truthful 2026-08-27 output is a pending-review packet with explicit missing-source blockers.
- The worktree contains extensive concurrent R5, Freshness, institutional, and backtest changes. New work remains limited to task-specific planning, one draft-preparation module/CLI/tests, one review-only architecture document, and the pending-review artifact root.

## Draft packet result

- The immutable 2026-08-27 packet is `PENDING_REVIEW`, `reviewed=false`, `formal_c1_eligible=false`, and `candidate_valid=false`; it carries exactly four missing-source blockers and no candidate payload paths.
- Packet digest is `32531ce578ea5cb1160fb43928c2184372708c22a4184b1067921c70c29ccc11`. The canonical `session_inputs/2026-08-27/` directory remains absent.

## External runner design inputs

- macOS provides `/bin/launchctl` and `/usr/bin/sandbox-exec`; Python is 3.13.5. These are availability facts only, not approval to install a runner.
- Current `.env` permissions are `0644`, which is too broad for a proposed external unattended runner that loads DSN/provider secrets. The design must require owner-only `0600` before approval; this task will not chmod or relocate it.
- A dedicated clean runtime checkout pinned to an approved commit is safer than executing the current concurrent dirty worktree. C0's source SHA-256 must remain identical through C1.

## Verification

- Importing the draft CLI does not load the C0/C1 entrypoints, concrete Shioaji/PostgreSQL adapters, `shioaji`, or `psycopg`; this is protected by an isolated-process regression test.
- Focused boundary suite: 62 passed. Full repository suite: 1549 passed, 59 skipped.
- Python compilation, draft CLI help, artifact/sidecar digest validation, canonical-input absence, and `git diff --check` all passed.
- No external service, sandbox profile, permission, secret file, automation, provider, database, order, fill, Position, or execution state was changed.
