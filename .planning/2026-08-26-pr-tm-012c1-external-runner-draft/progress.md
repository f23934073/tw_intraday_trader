# Progress: PR-TM-012C1 External Runner Draft

## 2026-08-26

- Started the explicitly authorized repo-only external runner implementation phase.
- Restored prior planning context and confirmed the worktree contains extensive unrelated changes.
- Selected a new isolated plan directory without changing the shared active-plan pointer.
- Announced and read the planning, architecture, coding-discipline, and code-review skill instructions.
- Read the full external execution design, operational C0/C1 contracts, entrypoint parsers, runtime identity, reviewed calendar, immutable artifact writer, review-promotion validators, and existing launchd conventions.
- Froze the command/process boundary and the fail-closed deployment-spec approach; no provider/DB/C0/C1 command was run.
- Completed Phase 1. Current phase: Phase 2 control-plane implementation.
- Implemented the first supervisor core, OS adapter, shared exact subprocess allowlist, thin CLI, disabled deployment templates, and 18 focused fixtures.
- First focused run: 17 passed, 1 boundary-test failure. The fixture incorrectly prohibited legal existing C0 data-plane imports; production code did not fail. Narrowed only that test assertion while preserving the subprocess boundary check.
- Second focused run exposed a test-edit placement error: ownership assertions landed in the child-log test. Moved them back; no runtime behavior changed.
- Focused suite recovered to 21 external fixtures plus 63 existing C0/input/C1 tests, all passing.
- Adversarial review Round 1 decision: REQUEST CHANGES with five P1 findings covering canonical digest recomputation, runtime drift, terminal binding, installation-evidence binding, and status naming. Remediation is in progress.
- Round 1 P1 regressions passed; full repository suite passed with `1636 passed, 61 skipped`.
- Round 2 decision: REQUEST CHANGES because `subprocess.run(timeout=...)` has an implicit SIGKILL/orphan risk. Reworking the single process adapter to explicit SIGTERM-only process supervision before the next review.
- The first compile of the Popen refactor caught four call-site syntax errors (`argv` followed a keyword argument). Named `argv=` explicitly; no command executed.
- Round 3 removed process capability from runtime identity by splitting exact read-only Git commands into a dedicated adapter.
- Round 4 required the immutable execution approval spec and sidecar to be current-user `0600`; added regressions and updated the installation checklist.
- Round 5 removed unbounded post-timeout waits from C0 internal child and Git helpers. They now use process-group SIGTERM, one bounded grace period, no SIGKILL, and an explicit termination-pending outcome. C1 documentation now matches the no-timeout/no-signal implementation.
- Final focused external supervisor suite: `34 passed`.
- Final full repository regression: `1643 passed, 61 skipped`.
- Final syntax, CLI help, JSON, plist, forbidden-process scan, subprocess/import boundary, read-only Git adapter, and scoped `git diff --check` validations passed.
- Final autonomous adversarial review decision: `APPROVE` for the repository-only uninstalled draft. Formal installation/execution remains blocked and Production Shadow Gate remains `NOT_PASSED`.
