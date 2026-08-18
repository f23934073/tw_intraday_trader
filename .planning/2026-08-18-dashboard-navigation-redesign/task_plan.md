# Dashboard navigation redesign

## Goal

Replace the homepage's momentum-first presentation with a neutral market overview, move primary functions into a collapsible left navigation rail, and make each function a full-page workspace with tabbed sub-functions. Preserve existing backend APIs and simulation/backtest behavior.

## Phases

- [x] Inspect current dashboard DOM, CSS, JavaScript state, and UI tests.
- [x] Implement the homepage information hierarchy and collapsible left navigation.
- [x] Convert historical backtest workspace into four accessible tabs.
- [x] Update focused UI tests and run syntax/regression checks.

## Decisions

- Homepage recommendation: use a neutral "市場總覽" with data health, candidate count, pending simulation orders, and selected-candidate detail; keep momentum evidence as a secondary analysis module instead of the hero.
- The left rail starts expanded on desktop and can collapse to an icon rail; on mobile it becomes a full-height off-canvas menu.
- Full-page workspaces are implemented inside the existing single-page app so current API contracts remain unchanged.
- Historical backtest tabs are: 準備歷史資料、設定策略組合、回測工作與結果、Baseline／Challenger 比較.

## Verification

- Existing candidate selection, order ticket, positions, strategy catalog, and backtest controls remain reachable.
- `scripts/check_dashboard_js.py`, focused dashboard UI tests, full pytest, and `git diff --check` pass.
