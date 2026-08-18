# Findings

- The current homepage has a momentum hero in the main content and exposes primary functions as top-right buttons.
- The current HTML already contains separate drawers for positions, orders, strategy catalog, and backtest, plus backtest sections for data, strategy setup, runs/results, and comparison.
- Existing backtest JavaScript uses element IDs and does not require separate backend routes per section, so tab switching can be a presentation-layer change.
- The current static dashboard is a single HTML file with inline CSS and JavaScript; surgical edits should stay in that file unless tests require otherwise.
- The worktree has unrelated uncommitted market-data, simulation, and planning changes. Do not revert or reformat them.
- The running local dashboard confirmed the new left rail and overview render with live snapshot data; the momentum projection is reachable separately.
- A first browser screenshot exposed the active backtest tab using only the first grid column; adding `grid-column: 1 / -1` made the tab content span the workspace.
- Collapsed sidebar buttons needed explicit `aria-label` values because their text labels are visually hidden in icon-rail mode.
- The screenshot overlap was confirmed by runtime geometry: sidebar right edge was `248px` and the drawer started at `248px`, ignoring the grid gap; the sidebar toggle also appeared above the drawer because its desktop z-index was `31`.
- The corrected runtime geometry is sidebar right `248px`, drawer left `266px`, with an 18px gap; the toggle is only above the sidebar while the mobile menu is open.
