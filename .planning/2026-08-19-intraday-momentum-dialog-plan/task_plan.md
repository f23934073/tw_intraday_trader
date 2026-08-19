# Task Plan: Intraday momentum detail dialog

## Goal

Implement the approved plan so users can click an intraday momentum row and inspect Candidate context plus current Tick/BidAsk-derived values and rule evidence in an accessible, live-updating dialog.

## Current Phase

Complete

## Phases

### Phase 1: Restore context and freeze scope

- [x] Inspect the supplied screenshot and record the requested interaction.
- [x] Confirm the dirty worktree and preserve unrelated changes.
- [x] Read repository-local instructions and locate the active dashboard implementation.
- **Status:** complete

### Phase 2: Trace the existing candidate dialog

- [x] Locate its row-click affordance, state model, rendering, accessibility, and close behavior.
- [x] Trace the backing API/service data contract and refresh behavior.
- [x] Record which behavior and fields should be reused.
- **Status:** complete

### Phase 3: Trace intraday momentum data

- [x] Map the intraday momentum table from runtime/provider through API to browser rendering.
- [x] Identify available versus missing Tick, BidAsk, freshness, score, decision, and rule-evidence fields.
- [x] Check ordering, stale/warm-up/error states and safe data-only boundaries.
- **Status:** complete

### Phase 4: Design the change

- [x] Define the click target and dialog information architecture in Traditional Chinese.
- [x] Define frontend state and backend/API contract changes with loading, empty, stale, and error behavior.
- [x] Specify responsive layout, accessibility, refresh consistency, and performance constraints.
- **Status:** complete

### Phase 5: Verification plan and handoff

- [x] Define exact files, dependency order, focused tests, browser scenarios, and acceptance criteria.
- [x] Cross-check the plan against current repository behavior and the supplied screenshot.
- [x] Confirm that no product code was implemented.
- **Status:** complete

### Phase 6: Baseline and backend contract

- [x] Capture focused test and JavaScript baselines from the current dirty worktree.
- [x] Add provenance-aware `intraday` serialization for evaluated and unavailable Momentum items.
- [x] Extend service/API contracts without changing subscriptions, scoring, or broker behavior.
- **Status:** complete

### Phase 7: Dialog implementation

- [x] Add accessible row triggers and native Dialog shell.
- [x] Render Candidate summary, intraday features, full rule evidence, source/version data, and safe unavailable/error states.
- [x] Keep an open Dialog synchronized with aggregate polling while preserving focus and scroll.
- **Status:** complete

### Phase 8: Verification and delivery

- [x] Add focused service/API/UI regression coverage and update README.
- [x] Run focused/full/static checks and review the scoped diff.
- [x] Browser-test pointer, native-button focus, close/focus restoration, live refresh, Candidate navigation, and narrow layout.
- **Status:** complete

## Decisions

| Decision | Rationale |
|---|---|
| Plan only; no product-code changes | The user explicitly asked for planning. |
| Use an isolated planning directory | Existing root and task-specific planning records contain unrelated in-progress work. |
| Reuse the established candidate dialog interaction where practical | The user explicitly wants the intraday momentum interaction to behave like the candidate list. |
| Preserve data-only and no-order semantics | A detail dialog is an observability feature, not a trade instruction or broker action. |
| Implement against the current working copy | Relevant Momentum and Dashboard files already contain substantial uncommitted user changes. |
| Keep the change additive and server-owned | The browser formats the existing projection and never recomputes score, stage, or evidence. |

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| First architecture-plan patch omitted the added-line prefix before `git diff --check` | 1 | No file was created; recorded the failure and reapplied a corrected patch successfully. |
| New stale-provenance test referenced `runtime` before assigning it | 1 | Restored the original close assertion and assigned the fake runtime explicitly in the new test. |
| UI contract expected `momentumDialogBody` but implementation uses `momentumDetailBody` | 1 | Corrected the test to the actual stable DOM variable name. |
| Sandboxed local server could not bind `127.0.0.1:8765` | 1 | Re-ran the scoped Uvicorn command with approved local bind permission; server started successfully. |
| Browser Escape key did not emit the native Dialog `cancel` event | 1 | Added the Momentum Dialog as the first branch of the existing global Escape handler, retaining the native cancel listener as fallback. |
| Momentum polling replaced the restored row trigger and focus fell back to `body` | 1 | Preserve the focused row symbol across table replacement and refocus its new trigger without scrolling. |
| Browser locator could not evaluate the hidden closed Dialog | 1 | Used read-only page evaluation to confirm `open=false`; no product retry or mutation was needed. |
| System `python3` did not have `pytest` installed during the final rerun | 1 | Re-ran the suite with the repository's `.venv/bin/python`; all tests passed. |
| Browser control could not synthesize trusted Enter activation on the background tab | 1 | Verified a native labeled `<button>`, focus restoration, and click bubbling in-browser; retained deterministic UI contract coverage for the keyboard-accessible trigger. |
