# Progress: Strategy Set lifecycle actions

## 2026-08-23

- Started a repository-grounded lifecycle audit.
- Declared immutable revision and reference-safe removal as acceptance boundaries.
- Inspected the migration, repository, backtest snapshot, and Local Paper activation paths.
- Selected lifecycle-safe semantics: revise to a new exact version; archive the family instead of hard-deleting snapshots.
- Confirmed revision creation can reuse the existing immutable save path with the same family id and `base.version_number + 1`.
- Confirmed the UI should require a delete confirmation and show explicit archive success feedback.
- Added migration 011 with a separate Strategy Set archive tombstone table.
- Added repository/application archive operations, active-list filtering, Local Paper rejection, revision/create API reuse, and new-backtest archive rejection.
- Backend revision creates the next immutable version in the same strategy-set family; archive remains idempotent and evidence-preserving.
- Began the Tab 3 card/editor interaction implementation.
- Added latest-version-only Modify/Delete card actions, revision editor state, cancel/reset, delete confirmation, and inline feedback.
- Added revision/archive API tests, archived-backtest rejection coverage, migration assertions, and PostgreSQL archive lifecycle coverage.
- Browser-checked the Tab 3 copy, editable minimum trigger input, automatic `AT_LEAST_N` switch, and initial cancel-button state against the local app.
- Focused regression passed with 62 tests; full regression found one stale expected migration list and is being rerun after updating it for migration 011.
- Full regression passed: 1254 tests passed and 23 PostgreSQL/environment-dependent tests skipped.
- JavaScript syntax, Python compilation, and `git diff --check` all passed.
