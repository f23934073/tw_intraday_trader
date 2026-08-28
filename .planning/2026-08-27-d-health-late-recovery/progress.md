# Progress Log

## Session: 2026-08-27

### Current Status

- **Phase:** 1 — Artifact and source diagnosis
- **Started:** 2026-08-27

### Actions Taken

- Read the current Shioaji adapter, passive capture, callback-quarantine, and exact replay paths.
- Verified the 2026-08-26 session reached replay parity and the 2026-08-27 session did not.
- Created an isolated task plan without taking ownership of the worktree's existing `.planning/.active_plan`.
- Identified the three rejected replay inputs: their source timestamps were milliseconds after the MID collection window but well inside the official trading session.
- Corrected future bootstrap metadata so `session_phase` remains OPEN/MID/CLOSE while the exact-replay calendar is the official 09:00–13:30 session.
- Sealed the repair in the dedicated OPEN runtime as local commit `c4a59ea`; its manifest, runner, interpreter, source-tree identity, and clean worktree verification passed.
- Replaced the unloaded 2026-08-28 08:55 LaunchAgent with the sealed runtime; it reports `runs = 0` and will not start before its calendar trigger.
- Updated the existing CLOSE automation from its expired one-shot cadence to weekday 12:50. MID remains weekday 10:21; both retain the evidence-only safety prompt.

### Test Results

| Test | Expected | Actual | Status |
|---|---|---|---|
| 2026-08-26 MID exact replay | Ten deterministic digest matches | PASS | passed |
| 2026-08-27 MID exact replay | Valid journal input | Rejected: event outside captured session calendar | blocked |
| Bootstrap calendar contract | Official session distinct from collection phase | Regression test passed in both worktrees | passed |
| Main D-HEALTH focused suite | 25 tests | 25 passed | passed |
| Sealed-runtime D-HEALTH + runner suite | 42 tests | 42 passed | passed |
| Sealed runtime identity | Hash-bound clean runtime | PASS | passed |
| Main full suite | No D-HEALTH regression | 1749 passed, 88 skipped, 1 unrelated FinMind drift failure | scoped pass |
| Sealed-runtime full suite | Broad regression | 7 unrelated FastAPI collection errors; focused suite remains green | environment-limited |

### Errors

| Error | Resolution |
|---|---|
| Replay failure cause not yet tied to a record | Inspect the retained JSONL and replay validator next. |
| Sealed runtime full-suite collection lacks FastAPI | Do not install packages or broaden runtime; the scheduled collector does not import FastAPI. |
| Main full suite fails `test_phase82_bundle_reproduces_selection_and_status_only_job` | It detects mutable FinMind target-job drift; preserve for its owning task. |
