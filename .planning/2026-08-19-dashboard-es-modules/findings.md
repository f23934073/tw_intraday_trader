# Findings & Decisions

## Requirements

- Split the current large dashboard `index.html` by workspace using browser-native ES modules.
- Do not introduce React or a frontend build system.
- Preserve existing API, WebSocket, paper-simulation, backtest, and server-side decision contracts.
- Preserve unrelated worktree changes.

## Initial Findings

- `dashboard/static/index.html` currently contains layout, styles, and a large inline browser script.
- The existing UI tests are mostly source-string assertions, so module boundaries need dedicated behavioral/static coverage.
- Momentum already has a cursor-safe WebSocket transport; its browser-side code must not calculate signals.
- Existing dashboard static hosting can serve sibling JavaScript modules without server routing changes.

## Inventory Notes

- The inline script begins at line 1067 and the current file has 3,398 lines.
- The script has clear responsibility clusters: shared formatting/rendering; candidate/history; simulation; momentum WebSocket/dialog; strategy catalog; and backtest orchestration.
- DOM lookup is currently global to the inline script, so the first extraction should centralize DOM references and shared state rather than make modules query arbitrary markup independently.
- `index.html` contains large shared CSS as well as workspace markup. The safe first pass is JavaScript ownership separation plus moving the whole stylesheet to a static CSS asset; CSS selector-by-selector workspace splitting can be incremental.
- Momentum already forms one mostly self-contained unit: dialog rendering, projection rendering, WebSocket resume/reconnect, alert acknowledgement, and polling fallback. Its only cross-workspace operations are navigation to a selected candidate.
- Simulation similarly owns its drawer, form, projection refresh, order submission/cancellation, positions, and status rendering; it only needs shared snapshot state and common formatting.
- Backtest has a large but cohesive API/render/polling cluster. Candidate history/chart logic is another coherent module.
- The current JavaScript syntax checker only extracts an inline script, so it must be upgraded to validate the module entrypoint and every static module before the inline script is removed.
- `dashboard/static` has no existing asset hierarchy, so the migration can add `dashboard/static/js/` without competing with an existing frontend build convention.

## Working Module Boundary

- `app.js`: browser composition, navigation, lifecycle, snapshot refresh, and shared state.
- `shared/`: DOM escaping/formatting and HTTP/error helpers.
- `workspaces/`: overview, candidates, simulation, momentum, and backtest modules.
- `styles/`: retain shared layout first; extract workspace CSS only where it keeps ownership clear.

## Issues Encountered

| Issue | Resolution |
|-------|------------|
| None | — |
