# PCD-001 progress

## 2026-08-28

- Read the complete PCD-001 plan and hygiene dependency/safety contract.
- Verified exact requested base and removed only the task-created root planning-file edits.
- Confirmed this isolated worktree uses the committed test, not the owner working tree's uncommitted hard-coded variant.
- Began phase 1 baseline evidence capture.

## Verification log

Pending.

- Existing immutable acquisition JSON/sidecar aggregate baseline SHA: `0549b6f577fed158053b6681f6490235e752cb201d01887e87b083cfc4af86bc` (acknowledgement names excluded).
- The plan's two causing commits were reproduced: `f751843` and `1d9d014`.
- Baseline source/test command did not run because bare `python` is unavailable; retry will use the repository virtualenv, not a different semantic test.
- Source SHA evidence matches the PCD-001 plan exactly.
- The first `python3 -m pytest` attempt could not collect because pytest is not installed; no test semantics were executed.
- Created ignored worktree `.venv` with CPython 3.12.6 and installed only `.[dev]`; no broker/PostgreSQL extras were installed.
- Baseline focused suite reproduced the intended sole red light: `1 failed, 3 passed`; failure is the immutable downloader pin versus current live SHA.
- Restored the tracked egg-info file changed only by editable installation; worktree task scope is clean apart from the ticket workpad.
- Generated a two-entry canonical acknowledgement with digest `582099be03e7e14c618c2835b6cf6f32999cb36b9822e737233323ad596e686b`; both entries derive causing commits from git history.
- Builder `--check` exited 0.
- Focused suite is green after implementation: `9 passed in 0.35s` (five new tests, including three fail-closed cases).
- `git diff --check` passed after focused implementation.
- Negative-probe attempt 1 was intentionally rejected as evidence: the EOF patch left the source SHA unchanged and the suite stayed green, so it does not satisfy acceptance 6.
- Acceptance-6 negative probe succeeded on attempt 2: before SHA `7abd3d3ba479907e836277294272733178b634c05ca598e8e7b4ffa3843d21c9`; patched SHA `a717bb78d6676fff5f6fec813cd72e5907509748579f448c641da520a41838e4`; focused result `1 failed, 8 passed`, with explicit stale-acknowledgement message.
- Removed the exact blank-line patch; after SHA returned to `7abd3d3ba479907e836277294272733178b634c05ca598e8e7b4ffa3843d21c9`; `git diff --exit-code -- backtest/historical_download.py` and focused `9 passed` both succeeded; builder `--check` returned current.
- First full regression: `6 failed, 1785 passed, 87 skipped in 33.28s`. Every failure is in `tests/test_finmind_selection_bundle.py` and traces to the same missing ignored `data/finmind_sponsor/...phase82_selection_...json` file; no PCD-001 test failed.
- Owner evidence aggregate before temporary fixture setup: `5439f832c84b714611bb1f2608ba86c30b522e7e32c226e5822c416b3c235b8e` across the bundle, read-only DB, and six referenced files.
- Symlink diagnostic produced `1 failed, 5 passed`: five document-only tests passed, while the end-to-end verifier correctly blocked resolved evidence outside the task project root. Symlinks will be removed and not used for acceptance.
- Byte-identical local fixture made selection focused tests pass: `6 passed in 8.18s`.
- Complete regression with the required local evidence present passed: `1791 passed, 87 skipped in 36.98s`.
- Owner evidence aggregate after tests remained `5439f832c84b714611bb1f2608ba86c30b522e7e32c226e5822c416b3c235b8e`, identical to before. The eight copies were removed; cleanup found two local SQLite `-wal`/`-shm` runtime files still to remove.
- Added a sixth test that binds the checked acknowledgement to the builder-derived structure, including git-derived causing commits.
- Final focused result: `10 passed in 0.15s`; builder `--check`, compileall, and `git diff --check` passed.
- Final complete regression for the exact implementation bytes: `1792 passed, 87 skipped in 38.59s`.
- The second byte-identical evidence fixture and its local SQLite `-wal`/`-shm` were removed. Owner evidence aggregate remained `5439f832c84b714611bb1f2608ba86c30b522e7e32c226e5822c416b3c235b8e` before and after both regression runs.
- Existing acquisition JSON/sidecar aggregate remained `0549b6f577fed158053b6681f6490235e752cb201d01887e87b083cfc4af86bc`; only the two new acknowledgement files appear in acquisition status.

## Red-light closure record

- Root cause: the immutable r2 scan configuration correctly pins the 2026-08-21 source identities, while the two live source files legally evolved afterward; comparing the immutable pins directly to mutable live bytes made the old test permanently red.
- Selected remedy: scheme D separates the canonical artifact-integrity seal from an exact, reviewed source-drift acknowledgement. Missing, stale, unsealed, mismatched-status, duplicate, or unexpected acknowledgement state fails closed.
- The previously recorded `1721 passed, 86 skipped, 1 failed` price-coverage failure is closed; the current complete suite has zero failures.
- Reuse constraint: any rerun, resume, or extension of r2 must first freeze a new r3-or-later scan configuration; r2 pins must never be presented as current source identity.
- Safety: all execution was offline/dev-test only. No provider, Shioaji, PostgreSQL, market-data generation, coverage scan, or trading path was used.
