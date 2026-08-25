# Strategy Management UI Redesign

## Goal

重新設計「策略管理」工作區，讓策略選擇、參數草稿、版本、策略組合與稽核功能不再藏在長頁底部，同時保留既有 API、資料模型與安全邊界。

## Scope

- 只修改 Dashboard 前端 HTML／CSS／JavaScript、前端回歸測試與本計畫文件。
- 不修改策略演算法、PostgreSQL schema、lifecycle、模擬交易、broker 或 real-money 能力。
- 保留現有暗色設計語言與繁體中文介面。
- 不納入 `.planning/.active_plan`、FinMind、live-trading 或 odd-lot 變更。

## Phases

### Phase 1 — UX evidence and information architecture

- [x] Inspect the supplied screenshot and current Strategy Management DOM/CSS/JS.
- [x] Query `ui-ux-pro-max` for long-form tool navigation, sticky actions, accessibility, and plain HTML guidance.
- [x] Freeze a minimal redesign that exposes every major workflow above the fold.

### Phase 2 — Implementation

- [x] Add predictable workflow navigation and compact master-detail layout.
- [x] Keep active task controls visible without hiding content behind sticky elements.
- [x] Preserve existing element IDs, API calls, form semantics, escaping, and keyboard behavior.
- [x] Add responsive behavior for narrower screens.

### Phase 3 — Verification

- [x] Run Dashboard JavaScript graph/syntax validation.
- [x] Run focused Dashboard/Atomic Web tests and full no-DSN regression as appropriate.
- [x] Render and inspect the updated page at desktop and narrow viewport widths.
- [x] Run accessibility and `git diff --check` review.

## Gate

UI redesign: **COMPLETED / READY FOR USER REVIEW**. No commit or push is authorized by this task unless requested separately.

## Errors Encountered

| Error | Attempt | Resolution |
|---|---:|---|
| `python` command unavailable for skill search | 1 | Re-ran the skill script with `python3`. |
| Initial findings patch context mismatch | 1 | Inspected the actual file and reapplied against stable headings. |
