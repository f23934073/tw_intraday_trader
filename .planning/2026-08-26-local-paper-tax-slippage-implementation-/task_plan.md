# Task Plan: Local Paper 證交稅與滑價實作計畫

## Goal
產出一份可直接交給獨立 Codex 任務執行的 source-grounded implementation plan，讓 Local Paper 以可稽核、可重播且不重複扣款的方式納入台灣股票賣出證交稅與不利滑價，同時避免和正在進行的 Kill Switch 任務互相覆蓋。

## Current Phase
Complete

## Phases

### Phase 1: 現況與法規盤點
- [x] 確認本輪只寫計畫、不實作交易程式。
- [x] 追查 Local Paper 撮合、費用、現金／損益、Journal 與 recovery 契約。
- [x] 追查回測既有的 `sell_tax_rate`／`slippage_bps` 語意與可重用邊界。
- [x] 以官方來源確認目前台灣股票證交稅與當沖優惠規則。
- **Status:** complete

### Phase 2: 契約與風險設計
- [x] 定義稅率資格、保守 fallback、逐筆 rounding、滑價與價差的邊界。
- [x] 定義 cash／PnL／Journal／replay／settings 版本化與相容策略。
- [x] 明確切開可與 Kill Switch 平行的工作及必須串行整合的重疊檔案。
- **Status:** complete

### Phase 3: 實作計畫撰寫
- [x] 寫出分階段、依賴順序、精確檔案範圍、測試、migration 與 rollback。
- [x] 補上 Definition of Done、時間估算與可直接貼到新任務的啟動提示詞。
- **Status:** complete

### Phase 4: 計畫驗證
- [x] 核對計畫與目前程式碼及官方規則一致。
- [x] 驗證無產品程式碼變更，且主工作區既有修改未被覆蓋。
- **Status:** complete

### Phase 5: 交付
- [x] 準備 Markdown 計畫與簡單易懂的執行摘要。
- [x] 還原本次建立前的 active-plan 指標。
- **Status:** complete

## Decisions Made
| Decision | Rationale |
|----------|-----------|
| 先做 source 與法規盤點再凍結數值 | 稅率、當沖資格與滑價 rounding 會直接影響現金和 PnL，不能只靠舊文件或猜測。 |
| 本輪僅變更 planning／architecture Markdown | 使用者要求先產生 impl plan，尚未授權實作。 |
| 將 Kill Switch 重疊檔案列為後段整合 | `runtime/composition.py`、API 與 Dashboard 可能同時被另一獨立任務修改。 |
| P0 新增商品分類 authority | 普通股 3‰ tax 與 tick table 不能套到 ETF、權證或未知商品。 |
| 新 v2 session 固定 frozen fee policy，僅 slippage 可調 | 法定/reference costs 與未校準 execution assumption 必須分開。 |

## Errors Encountered
| Error | Resolution |
|-------|------------|
| 誤呼叫不存在的 `scripts/session-catchup.sh` | 改用 skill 實際提供的 `scripts/session-catchup.py`，成功恢復上下文。 |
