# Task Plan: 三大法人資料與策略研究報告

## Goal
產出一份以目前 `tw_intraday_trader` 架構為基礎、可直接進入實作評審的三大法人資料取得與策略設計完整技術報告；本次不修改產品程式。

## Current Phase
Complete

## Phases

### Phase 1: Requirements & Discovery
- [x] 確認使用者要完整研究報告，而非立即實作策略。
- [x] 保留目前工作區未提交的 freshness calibration 變更。
- [x] 盤點專案現有資料、策略、回測與 catalog 邊界。
- [x] 查核官方 TWSE/TPEX 資料來源、欄位、更新時點與限制。
- **Status:** complete

### Phase 2: Planning & Structure
- [x] 定義法人正規化資料契約、交易日／as-of／可用時間語意。
- [x] 設計不使用未來資料的策略假說與回測矩陣。
- [x] 定義報告 narrative、圖表 contract 與來源證據。
- **Status:** complete

### Phase 3: Report Construction
- [x] 產出完整 technical report artifact（MCP app report）。
- [x] 在報告中加入資料源比較、策略優先順序、架構與測試計畫。
- **Status:** complete

### Phase 4: Testing & Verification
- [x] 驗證資料來源與官方文件證據。
- [x] 驗證 artifact schema、圖表、表格、來源 metadata 與閱讀順序。
- [x] 確認沒有修改產品程式或混入既有未提交變更。
- **Status:** complete

### Phase 5: Delivery
- [x] Render 完整 MCP report 並交付重點結論。
- [x] 提供可選的後續 Sites 分享，不自行發布。
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 以 technical audience 撰寫 | 核心價值在資料可用時點、正規化、look-ahead 防護、策略定義與驗證方法。 |
| 本次只研究與報告，不實作 | 使用者尚未要求修改策略程式；先讓資料與假說可評審。 |
| MCP app report 為唯一 delivery mode | 目前為 Codex Desktop、非 Work Mode，且 artifact validator/renderer 可用。 |
| 以官方 TWSE/TPEX 為權威資料源 | 三大法人數據是交易策略輸入，需避免第三方欄位漂移與不可稽核。 |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| 初始化腳本無法用中文產生 slug，建立 `untitled-5758e1ab` | 保留穩定 plan id，直接在內容中使用中文任務名稱。 |
| Web opener 拒絕帶 query 的官方 JSON endpoint | 以官方頁面/Swagger 保留證據，另用唯讀 HTTP client 驗證實際 response。 |
