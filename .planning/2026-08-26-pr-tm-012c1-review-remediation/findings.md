# Findings: PR-TM-012C1 adversarial review remediation

## Frozen findings

- P0: one date-level draft output is consumed by the first missing-source attempt.
- P0: C1 treats canonical path placement as reviewed provenance and does not verify an approval artifact.
- P0: the external execution allowlist omits Git and the existing C0 worker/rehearsal child modes.
- P0: no atomic cross-supervisor/session lock prevents duplicate C0/C1 collectors.
- P1: candidate files are hashed and validated through separate reads.
- P1: SIGTERM cannot currently guarantee a terminal C1 artifact.
- P1: JSON and digest sidecars are written as a non-atomic pair without an explicit incomplete-pair disposition.
- P1: baseline RiskSnapshot input lacks session/date/symbol/capture/source provenance.

## Constraints

- Do not rewrite the existing 2026-08-27 missing-source packet.
- Do not fabricate candidate inputs or reviewer approval.
- Do not install or enable launchd, sandbox profiles, supervisors, or permissions.
- Do not alter the existing automation.
- Do not invoke provider, database, order, fill, Position, CA, or trade-callback capabilities.

## Second adversarial review findings

- P0: external ownership keyed by market date plus session ID permits concurrent collectors with different session IDs.
- P0: C1 ignores the C0 artifact-pair `.write.lock` introduced by exclusive publication.
- P0: C1 ignores a retained per-date promotion lock after crash-at-rename.
- P1: POSIX `rename` can replace an existing empty canonical date directory after the pre-check.
- P1: terminal evidence re-reads the preflight artifact after session admission.
- P1: runtime identity omits prepare/review/promotion entrypoints.
- P1: the external exact allowlist omits the `git status --porcelain` child required by its own clean-checkout gate.
- P2: RiskSnapshot capture provenance has no reviewed temporal admissibility window.

## Read-only reproductions

- C1 canonical path admission accepted a retained `.YYYY-MM-DD.promotion.lock`.
- Changing `scripts/review_trade_management_shadow_inputs.py` did not change `runtime_code_identity`.
- POSIX `Path.rename()` replaced an existing empty destination directory.

## Final adversarial re-review findings

- P1: prepare records its actual `prepared_at` but does not reject a RiskSnapshot whose `captured_at` is later than that operation.
- P1: review accepts caller-supplied future `reviewed_at` so long as it follows the claimed RiskSnapshot capture; a 2099 timestamp was accepted by the approval contract.
- P1: C1 recomputes the manifest and readiness-report digests, but only compares provider/PostgreSQL/rehearsal claimed digests to the report. Their payload digests are not independently recomputed.
- These are evidence-integrity findings only; no provider, database, execution, canonical-input, approval, or external-runner action is required to remediate them.
