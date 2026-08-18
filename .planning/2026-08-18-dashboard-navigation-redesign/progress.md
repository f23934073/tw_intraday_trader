# Progress

## 2026-08-18

- Restored prior planning context and inspected the dirty worktree.
- Read the relevant coding/planning skill instructions.
- Located current dashboard navigation, homepage momentum section, drawer workspaces, and backtest markup/state.
- Replaced the momentum-first homepage with a market overview summary and moved momentum into its own workspace.
- Added a collapsible left navigation rail with full-width workspace panels for research and local simulation features.
- Added four accessible historical-backtest tabs and preserved existing element IDs/API flows.
- Updated UI contract tests and README documentation.
- Verification: JavaScript syntax and focused tests passed; browser verified overview, momentum, backtest tab switching, full-width setup layout, and sidebar collapse.
- Final regression after the mobile navigation close fix: `297 passed, 1 skipped`; JavaScript syntax and `git diff --check` passed.
- Follow-up overlap diagnosis: the full-page drawer was aligned at `left: 248px`, while the main grid starts after the 18px gap at `266px`; the desktop sidebar toggle also had z-index 31 and rendered over the drawer heading.
- Fixed drawer alignment to the main column (`left: 266px`, top/bottom aligned with the shell), and limited the high z-index sidebar toggle to the mobile-open state. Browser screenshot now shows a clean gap and unobstructed 持倉 heading.
