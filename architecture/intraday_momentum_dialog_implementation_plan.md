# 盤中動能明細 Dialog 實作計畫

## 1. 目標

讓「盤中動能」表格的每一檔股票都能點擊，開啟可鍵盤操作的明細 Dialog。Dialog 同時呈現：

1. 候選清單已有的標的與候選規則摘要。
2. 後端 Tick／BidAsk Momentum projection 產生的盤中數值。
3. 全部規則的成立、未成立、缺資料或過期證據。
4. 評估時間、資料健康與策略版本。

這是唯讀的決策支援功能。分數不是漲停機率、買進建議或委託指令，第一版 Dialog 不放模擬買進或任何券商操作。

## 2. 現況與差距

### 2.1 候選清單

- `dashboard/static/index.html` 的候選清單以 `candidate-button` 選取股票，並在同一工作區的 `detail-panel` 顯示明細。
- 技術上目前是右側明細面板，不是原生 `<dialog>`；本計畫會沿用它的資訊層級與選取體驗，但依本次需求為盤中動能建立真正的 modal Dialog。
- Candidate 快照已含股票名稱、來源、候選規則、分數，以及價格、開高低、昨收、成交量、VWAP、相對量等欄位。

### 2.2 盤中動能

- `renderMomentum()` 目前把 `state.momentum.items` 畫成唯讀 `<tr>`，沒有可點擊 trigger、選取 symbol 或 Dialog state。
- `/api/dashboard/momentum` 已提供所有候選的盤中狀態；`/api/dashboard/momentum/{symbol}` 已存在，但目前只回傳 aggregate item 的同一份資料，不是較完整的 detail contract。
- Realtime item 已有候選分數／規則、availability、stage、signal score，以及每條規則的 observed value、threshold、pass/fail、source time 和 missing reason。
- Realtime item 尚未輸出 `MomentumProjection.feature_snapshot` 的盤中市場數值。Replay serializer 雖已輸出部分市場欄位，但 Realtime serializer 沒有。

## 3. 範圍

### 3.1 第一版包含

- 整列可用滑鼠點擊，symbol 位置同時保留正式 `<button>` 供鍵盤操作。
- 開啟、關閉、Escape、backdrop、焦點回復與小螢幕版面。
- Candidate 摘要與 scanner 快照。
- Tick／BidAsk 衍生的盤中 feature 值。
- 全部規則證據與資料狀態。
- Dialog 開啟期間隨既有 Momentum polling 原地更新。
- evaluated、warm-up、capacity evicted、missing、stale、removed 和 API error 狀態。

### 3.2 第一版不包含

- 不改 Candidate 工作區既有右側 detail panel。
- 不在 Dialog 內放模擬買進或其他委託入口。
- 不新增 broker order、CA、trade callback 或自動交易路徑。
- 不在瀏覽器重算 VWAP、Momentum score、stage、threshold 或任何交易規則。
- 不把歷史 Kbar 圖複製進 Dialog；完整歷史走勢仍留在候選清單工作區，Dialog 可提供「前往候選完整評估」的唯讀導覽。
- 不假造目前 projection 沒有的 best bid、best ask 或漲停價。若要顯示精確報價，需另行擴充 runtime 的唯讀 quote/reference projection。

## 4. Dialog 資訊架構

### 4.1 標題區

- 股票代碼、名稱。
- 目前 stage，例如「觀察」、「突破」、「加速中」。
- availability badge，例如「已評估」、「等待 Tick／BidAsk 暖機」、「超過即時訂閱上限」。
- 訊號 `as_of`。
- 明確的「關閉盤中動能明細」按鈕。

### 4.2 候選摘要

由 `state.snapshot.candidates` 依 symbol join，不另外呼叫 Provider：

- Candidate 分數／滿分。
- Candidate 來源與成立規則。
- scanner 快照：目前價格、較昨收漲跌、開盤／昨收、日高／日低、成交量、VWAP、相對量。
- 若當下主畫面快照找不到該 symbol，顯示「候選快照已更新，以下保留盤中 projection」，不得拿其他股票或零值補上。

### 4.3 盤中行情與動能

由後端 `MomentumProjection.feature_snapshot` 序列化，建議欄位：

| UI 標籤 | feature | 格式 |
|---|---|---|
| 即時價格 | `price` | 價格 |
| VWAP | `vwap` | 價格 |
| 盤中前高 | `previous_intraday_high` | 價格 |
| 距離漲停 | `distance_to_limit` | 百分比 |
| 2 分鐘報酬 | `return_2m` | 百分比 |
| 2 分鐘成交量 | `volume_2m` | 股數 |
| 量能加速 | `volume_acceleration_2m` | 倍數 |
| 本日外盤比 | `external_ratio_session` | 百分比 |
| 五檔委買／委賣比 | `bid_ask_ratio_5` | 比率 |
| 五檔委託簿不平衡 | `book_imbalance_5` | 比率或百分比，依後端契約固定 |

每個欄位都必須保留 `status`、`source_as_of` 與 `reason`。MISSING、STALE、UNVERIFIED 顯示「—」及原因，不得顯示 0。

### 4.4 規則證據

不要只顯示目前 table 中的 passed rules。Dialog 要列出 `signal.details` 的全部規則：

- 規則中文名稱。
- 成立／未成立／缺資料／資料過期／未驗證。
- 得分／滿分。
- 觀察值。
- 門檻。
- 資料時間。
- missing reason 或 block reason。

狀態顏色不能是唯一辨識方式，必須同時顯示文字與圖示／badge。

### 4.5 資料來源與版本

- `Shioaji Tick/BidAsk` source name。
- connection state、overall data health。
- Candidate refresh time、symbol evaluation time。
- Candidate refresh error（有錯才顯示）。
- signal config version、feature version、coverage。
- 固定揭露：「盤中分數是規則證據，不代表漲停機率，也不是買進或下單指令。」

## 5. API 與資料契約

### 5.1 Realtime item 新增 `intraday`

在不破壞既有 row 欄位的前提下，為 evaluated item 加入結構化欄位：

```json
{
  "symbol": "2613",
  "availability": "EVALUATED",
  "as_of": "2026-08-19T13:09:14+08:00",
  "intraday": {
    "price": {
      "value": "275.5",
      "status": "VALID",
      "source_as_of": "2026-08-19T13:09:14+08:00",
      "reason": null
    },
    "vwap": {
      "value": "271.8",
      "status": "VALID",
      "source_as_of": "2026-08-19T13:09:14+08:00",
      "reason": null
    }
  }
}
```

契約規則：

- Decimal 轉字串，避免瀏覽器浮點誤差；由 formatter 決定顯示小數位。
- `status` 沿用 `FeatureStatus` enum。
- 非 VALID 仍可保留原 value 作稽核，但 UI 預設不把它當有效現值；顯示 status/reason。
- 未完成 projection 的 item 回傳 `intraday: null`，並保留既有 availability label。
- 新增 `_serialize_feature_value()` 之類的單一 helper，避免各欄位各自遺漏 timestamp 或 status。
- Aggregate endpoint 與 symbol endpoint 共用 `_serialize_candidate()`，不可出現兩套欄位或計算邏輯。

### 5.2 不新增 click-time 必要請求

正常流程從已取得的 aggregate item 立即開 Dialog：

1. 使用者點擊 row。
2. 從 `state.momentum.items` 找 Momentum item。
3. 從 `state.snapshot.candidates` 找 Candidate item。
4. 立即 render 並 `showModal()`。

`GET /api/dashboard/momentum/{symbol}` 保留給直接重試或未來 deep link，不作為每次點擊的必要 round trip。

## 6. 前端狀態與互動

在 `state` 新增：

- `momentumDialogSymbol`：目前開啟的 symbol 或 `null`。
- `momentumDialogScrollTop`：需要時保留使用者捲動位置。

新增函式責任：

- `openMomentumDialog(symbol)`：驗證 symbol、render、showModal、移入焦點。
- `closeMomentumDialog()`：關閉、清 state，依 symbol 重新找到最新 row trigger 並回復焦點。
- `renderMomentumDialog()`：只格式化 server payload，不做市場運算。
- `syncMomentumDialog(momentum)`：polling digest 更新時原地更新內容，保留焦點與 scroll。
- `findCandidateBySymbol(symbol)`：從主 snapshot 取得 Candidate context。

Row 行為：

- `<tr data-momentum-symbol="...">` 可點擊並有 hover/focus-within 樣式。
- 第一欄股票代碼使用 `<button class="momentum-row-trigger">`，提供 Tab、Enter、Space 與 accessible name。
- row click 採 event delegation，避免每次 polling 全表重畫後綁大量 listener。
- 點選文字或其他未來互動控制時不得造成雙重觸發。

Polling 行為：

- 開啟 Dialog 不建立第二個 polling timer。
- 使用既有 `/api/dashboard/momentum` payload 與 digest。
- 更新 Dialog 內容時保留目前 focus、scroll 及開啟狀態。
- symbol 從新 Candidate 清單消失時，Dialog 不突然關閉；改顯示「此標的已離開目前候選清單」與最後 as-of，讓使用者自行關閉。
- API 暫時失敗時保留最後成功內容並顯示「更新失敗／資料可能過期」，不可清空 Dialog。

## 7. Accessibility 與 RWD

- 使用原生 `<dialog>`、`showModal()`、`aria-labelledby` 和明確 close button。
- Escape 使用瀏覽器原生 cancel 行為；backdrop click 可關閉，但 Dialog 內容 click 不關閉。
- 關閉後焦點回到同一 symbol 的最新 trigger；若 row 已移除，回到 Momentum heading。
- 不把整個高頻更新 Dialog 設成 `aria-live`，避免每筆 Tick 都被朗讀；只有錯誤／狀態切換使用小範圍 `role="status"`。
- Desktop：寬度約 `min(960px, calc(100vw - 32px))`、高度不超過 `90dvh`，body 區域獨立捲動。
- Mobile：接近全螢幕、固定可見標題與關閉按鈕，metrics 改單欄，rule table 改卡片或可讀的兩欄布局；不能依賴 900px table 橫向捲動。
- `prefers-reduced-motion` 下不使用強制平滑捲動或大幅 transition。

## 8. 實作順序

### Phase 0：凍結 UI／資料契約

1. 確認上述 Dialog 欄位與第一版非目標。
2. 為 `intraday` schema 建立 evaluated、warm-up、stale 三種 golden payload。
3. 確認百分比與 ratio 的單位，避免 UI 對同一欄位重複乘 100。

### Phase 1：後端 projection

1. 在 `dashboard/momentum.py` 增加 `FeatureValue` serializer。
2. 由 realtime `projection.feature_snapshot` 建立 `intraday`。
3. unavailable item 固定回 `intraday: null`。
4. 維持 aggregate 和 symbol route 共用同一 serializer。
5. 不修改 runtime signal 計算、訂閱策略或 order path。

### Phase 2：Dialog shell 與 row trigger

1. 在 `dashboard/static/index.html` 加入靜態 `<dialog>` shell、header、body、close control。
2. 將 Momentum rows 加上 symbol trigger 與 hover/focus styling。
3. 加入 open/close、focus restore、Escape/backdrop 行為。
4. 先完成 Candidate 摘要與 loading/unavailable/removed skeleton。

### Phase 3：盤中與規則明細

1. Render `intraday` metrics 與每欄 provenance。
2. Render 全部 `signal.details` 和 `block_reasons`。
3. 加入版本／資料健康／時間與 disclaimer。
4. 加入「前往候選完整評估」導覽，不帶入模擬下單。

### Phase 4：Live sync、RWD 與錯誤狀態

1. 將既有 polling 更新接到 `syncMomentumDialog()`。
2. 保留 open state、scroll、focus 與最後成功 payload。
3. 完成 390px、768px、desktop layouts。
4. 驗證 warm-up、capacity、stale、removed 和 request failure。

### Phase 5：驗證與文件

1. 更新 focused service/API/UI tests。
2. 跑 Dashboard JavaScript syntax check、focused tests、full regression、`git diff --check`。
3. 以實際瀏覽器驗證滑鼠、Tab/Enter/Space、Escape、backdrop、focus restore、polling 更新及 mobile layout。
4. 在 `README.md` 的 Dashboard 說明補上「盤中動能列可開啟唯讀證據明細」，並保留不代表下單的邊界。

## 9. 預計異動檔案

| 檔案 | 變更 |
|---|---|
| `dashboard/momentum.py` | 序列化 realtime intraday feature 與 provenance。 |
| `dashboard/static/index.html` | Row trigger、Dialog markup/CSS/state/render/live sync/accessibility。 |
| `tests/test_realtime_momentum_dashboard_service.py` | evaluated/unavailable/stale intraday contract。 |
| `tests/test_momentum_dashboard_api.py` | aggregate/symbol schema 一致與 404 行為。 |
| `tests/test_momentum_dashboard_ui.py` | Dialog、trigger、server-owned fields、no browser rule calculation。 |
| `tests/test_candidate_workspace_ui.py` | Candidate workspace 與選取行為沒有被 Dialog 破壞。 |
| `README.md` | 使用方式與唯讀／非下單說明。 |

`dashboard/server.py` 預期不需新增 route；若 schema typing 或錯誤映射需要才做最小調整。

## 10. 測試與驗收

### 10.1 自動測試

建議指令：

```bash
.venv/bin/python -m pytest \
  tests/test_realtime_momentum_dashboard_service.py \
  tests/test_momentum_dashboard_api.py \
  tests/test_momentum_dashboard_ui.py \
  tests/test_candidate_workspace_ui.py -q
python3 scripts/check_dashboard_js.py
.venv/bin/python -m pytest tests/ -q
git diff --check
```

### 10.2 必須通過的情境

1. 任一 evaluated row 以滑鼠、Tab＋Enter、Tab＋Space 都能開啟正確 symbol。
2. Dialog 一開啟就有 Candidate 摘要，不因 Momentum detail loading 顯示錯股票。
3. 盤中數值、規則結果與來源時間全部來自 server payload。
4. passed、failed、missing、stale、unverified 都有不同文字狀態；缺值不顯示 0。
5. warm-up 或 capacity-evicted row 仍能開啟 Dialog，顯示 Candidate 資訊與不可評估原因。
6. polling 更新不會關閉 Dialog、不會跳回頂端、不會偷走焦點。
7. symbol 被 Candidate refresh 移除時，顯示最後資料與 removed notice。
8. Escape、close button、backdrop 都能關閉；焦點回到原 symbol，或在 row 消失時回到 Momentum heading。
9. 390px viewport 不出現 Dialog body 水平溢位；關閉按鈕一直可見。
10. Dialog 沒有 broker／order side effect，也沒有模擬買進 control。

## 11. Rollout 與 rollback

- 這是 additive、read-only UI/API 變更，不需資料庫 migration。
- 先部署後端 `intraday` additive contract，再部署使用它的前端；舊前端會忽略新欄位。
- 若前端有問題，可移除 row trigger/Dialog rendering，現有 Momentum table 與 polling 仍可運作。
- 若後端 feature serialization 有問題，可停止輸出 `intraday`；UI 必須退回「盤中明細暫不可用」而不是影響 aggregate table。

## 12. Definition of Done

- 每個盤中動能 row 都可開啟同一視覺語言的唯讀明細 Dialog。
- Dialog 同時正確顯示 Candidate 摘要、盤中 feature、完整規則證據與資料 provenance。
- unavailable/stale/error 狀態 fail closed，不用 0 或過期值冒充有效值。
- 即時刷新不破壞 Dialog 的焦點與閱讀位置。
- Desktop、tablet、mobile 互動與 accessibility 驗證通過。
- focused/full/static checks 通過，README 與實際行為一致。
- 沒有新增或觸發任何 Shioaji／券商下單行為。
