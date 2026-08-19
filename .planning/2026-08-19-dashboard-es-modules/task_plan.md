# Task Plan: Dashboard ES Modules

## Goal

Split the dashboard browser implementation by workspace into native ES modules while preserving current HTML, API contracts, server-owned calculations, WebSocket behavior, and local-paper safety boundary.

## Current Phase

Complete

## Phases

### Phase 1: Inventory and module boundary design

- [x] Map the current script's state, DOM dependencies, exports, and workspace responsibilities.
- [x] Define an incremental module graph that does not require a frontend build step.
- [x] Freeze existing browser contracts with focused tests.
- **Status:** completed

### Phase 2: Extract shared browser foundation

- [x] Extract shared DOM utilities, formatting, API/error handling, and state ownership.
- [x] Make `index.html` load a minimal module entrypoint only.
- [x] Preserve non-workspace global lifecycle behavior in the entrypoint.
- **Status:** completed

### Phase 3: Extract workspaces incrementally

- [x] Extract overview/candidate and simulation workspace render/command modules.
- [x] Extract momentum transport/workspace without moving calculations to the browser.
- [x] Extract backtest workspace behavior without changing server API contracts.
- **Status:** completed

### Phase 4: Verification and delivery

- [x] Add behavioral/static module-boundary tests appropriate to the no-build toolchain.
- [x] Run JavaScript syntax, focused UI/API suites, and full regression.
- [x] Restore the previous active planning pointer and report intentionally deferred modularization.
- **Status:** completed

## Decisions Made

| Decision | Rationale |
|----------|-----------|
| Native ES modules, no framework migration | The user explicitly wants workspace separation without immediately introducing React. |
| Keep `index.html` as layout and module entry only | It gives a measurable reduction while preserving FastAPI static hosting and existing visible behavior. |
| Preserve server-owned indicators and decisions | Momentum/WebSocket data remains serialized by the backend; modules only render and coordinate transport. |
| Avoid a full CSS redesign | CSS extraction is included only where a workspace needs it; bulk selector movement would conflict with active worktree changes. |

## Errors Encountered

| Error | Resolution |
|-------|------------|
| None | — |
