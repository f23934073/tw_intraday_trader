# Task Plan: Kill Switch 與稅費滑價完成後的平行任務分析

## Goal
依兩個已完成獨立任務的實際交付、測試、未完成 Gate 與目前 repo 狀態，提出下一批可安全同時處理的任務、相依順序與建議優先級，不直接啟動或實作。

## Current Phase
Phase 4 — 完成

## Phases

### Phase 1: 完成狀態驗證
- [x] 讀取 Kill Switch 任務 final/status/evidence。
- [x] 讀取稅費／滑價任務 final/status/evidence。
- [x] 核對兩個 worktree 的 branch、diff、tests 與未完成 Gate。
- **Status:** completed

### Phase 2: Mainline 與依賴盤點
- [x] 確認兩個成果是否已整合至 main、是否互相包含或仍需 merge/rebase。
- [x] 盤點 Freshness、No-Overnight、PostgreSQL UAT、Shadow 等既有 blockers。
- **Status:** completed

### Phase 3: 平行波次設計
- [x] 依檔案重疊、外部時段、DSN 與安全依賴分組。
- [x] 列出可立即同時啟動、需先整合、需等交易時段的任務。
- **Status:** completed

### Phase 4: 驗證與交付
- [x] 交叉核對建議不會把 paper readiness 誤稱為 real-money readiness。
- [x] 交付簡單易懂的優先順序與時間估算。
- [x] 還原原 active-plan 指標。
- **Status:** completed

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 先驗證 task final 與 branch，不只看「已完成」狀態 | 完成可能只代表 scoped implementation，PostgreSQL UAT、合併或 formal review 仍可能未完成。 |
| 本輪不建立新 task | 使用者目前要求分析；待其選定波次後再建立。 |
| No-Overnight 先 forward-port，再做正式 campaign | 舊候選與新共同基線重疊 19 個核心檔案，舊 code identity 的 campaign 不能資格化新版本。 |
| Shadow fill.v3 compatibility 與 No-Overnight 平行 | blocker 位於 Shadow observer/builder，主要檔案與 No-Overnight core 分離。 |
| Daily loss 先 audit，不重做 | 現行已有 entry block、SELL bypass、opening-equity 與 durable policy tests。 |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| `codex_app.wait_threads` 在此環境沒有 handler | 改用 `read_thread` 刷新兩個任務的最新 turn。 |
| 目前工作區執行 `gh pr list` 遇到網路限制 | 以正在發布任務的 GitHub CLI 成功輸出確認 branch push 與 PR #2；不在本任務重複發布。 |
