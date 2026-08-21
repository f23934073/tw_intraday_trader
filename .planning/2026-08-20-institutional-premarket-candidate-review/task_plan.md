# Task Plan: Institutional Premarket Candidate Code/Design Review

## Goal
產出一份以目前 `tw_intraday_trader` 實際程式碼為依據的三大法人盤前候選策略設計審查與可直接進入實作評審的 implementation plan；本次不修改產品程式。

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] 讀完使用者提供的完整設計提案。
- [x] 確認本次是 review 與 plan only，不授權產品實作。
- [x] 盤點現有 Candidate、MarketData、Backtest、Dataset、Catalog、Dashboard 與 subscription boundaries。
- [x] 查核官方資料源與時序／交易範圍契約。
- **Status:** completed

### Phase 2: Planning & Structure
- [x] 對提案逐項給出 blocking／important／suggestion findings。
- [x] 定義最小可行架構、資料契約、研究假說與依賴順序。
- **Status:** completed

### Phase 3: Plan Authoring
- [x] 撰寫 repository-grounded implementation plan Markdown。
- [x] 列出 exact file map、migration、API/UI、tests、rollout、rollback 與 Definition of Done。
- **Status:** completed

### Phase 4: Testing & Verification
- [x] 驗證 plan 與目前程式契約、官方來源和使用者提案一致。
- [x] 驗證 Markdown 結構、識別碼、code fences、whitespace 與 scope。
- [x] 確認產品程式與既有 freshness calibration 變更未被修改。
- **Status:** completed

### Phase 5: Delivery
- [x] 以 severity-first 方式交付 review findings。
- [x] 提供 plan 路徑、推薦決策與下一步 approval gate。
- **Status:** completed

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 文件放在 `architecture/` | 此專案既有 strategy/backtest 重大變更都以 architecture implementation plan 管理。 |
| 法人資料定位為盤前 Candidate Prior | 符合現有即時 Candidate → BuyScore → Position/Exit 決策支援邊界。 |
| 不實作產品程式 | 使用者只要求 review 與 implementation plan。 |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| Root planning files 正在執行 freshness calibration Phase 13 | 建立隔離 `.planning/2026-08-20-institutional-premarket-candidate-review/`，完成後恢復原 active plan pointer。 |
