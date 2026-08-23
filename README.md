# 台股即時選股與交易決策系統 MVP

台股盤中即時決策系統，核心流程：

> 找誰 → 值不值得買 → 買了之後何時離場

---

## 快速開始

### 1. 安裝依賴

```bash
# 建立虛擬環境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安裝基本依賴
python3 -m pip install -e ".[dev]"

# 若要使用 Shioaji 真實連線（選填）
python3 -m pip install -e ".[broker,dev]"
```

### 2. 設定環境變數（選填，使用 Shioaji 才需要）

```bash
cp .env.example .env
# 編輯 .env，填入 SHIOAJI_API_KEY 與 SHIOAJI_SECRET
```

### 3. 執行

```bash
python3 app.py
```

預設使用 **MockProvider**，不需網路連線，立即可看到輸出。
若 `.env` 或 shell 已設定 `PROVIDER=shioaji`，它會明確覆寫此預設，必須先安裝 broker extra 並設定 Shioaji 金鑰。

---

## Web 儀表板

本機啟動儀表板與紙上模擬：

```bash
python3 -m dashboard
```

瀏覽器開啟 `http://127.0.0.1:8000`。首頁預設是「市場總覽」：先看候選數、資料健康、待處理委託與已成交持倉，再選取候選股查看完整評估。左側功能欄可收合成圖示列；手機版會變成可滑出的導覽。候選清單仍是單次掃描快照，只有按下「重新掃描」才會再次執行全市場掃描。選取候選股後，預設顯示 1 日來源 Kbar，也可切換 5 日、20 日或 3 月；3 月日 K 額外顯示 MA5／MA20／MA60、成交量與區間高低點。歷史資料只會在選取該股票時向後端查詢；長週期會由後端分段取得，避免超過資料來源的單次 Kbar 查詢限制。

右上角會每 60 秒讀取目前登入連線的 Shioaji 流量狀態；只有流量已達上限時，才會顯示紅色的「Shioaji 流量已超過」警示。這項檢查不會額外呼叫 Snapshot 或 Kbar 行情 API，MockProvider 也不會顯示警示。

### 台指期夜盤盤前情境

市場總覽會另外顯示「台指期夜盤」panel。後端依 versioned TAIFEX calendar 找出下一個一般交易日與實際夜盤窗口；例如星期一使用前一個交易日 15:00 到隔日 05:00，不會把星期日當成夜盤。2026 calendar artifact 的資料狀態截至 2026-08-19，包含年度休市日與 2026-07-10 臨時休市；超出覆蓋年度時會回傳 `UNAVAILABLE`，不使用 weekday 猜測。

`query_not_before` 是實際 `session_end + 5 分鐘`，只表示可以開始查詢。`READY` 還必須通過版本化 completeness predicate、session 起訖、OHLCV、時間排序及 live contract identity 檢核。MockProvider 使用固定且明確標記的完整 fixture，因此可顯示 `READY`；Shioaji Kbar 的 finalization 尚未由真實 Kbar／Tick capture 證明，所以目前即使查到數值仍會保持 `PENDING`，不會因為時間已到或 query 有資料就假裝完整。

Context 只把 Shioaji `FuturesInfo.reference` 顯示為「Shioaji 參考價」。TAIFEX settlement 只能來自另一份 Reconciliation Artifact；兩份 immutable artifact 以 `context_digest` 在 projection 階段連結，reconciliation 不會回寫 context health。V0 只顯示 `session_move_pct`、`session_range_pct`、`provider_reference_change_pct` 等 signed metrics，沒有 `FLAT`、方向或 regime 分類。

Raw source、Context 與 Reconciliation 預設以 content-addressed JSON 分開保存在 `data/premarket/`；程式重啟後會重新驗證 canonical digest 與路徑 identity，檔案遭竄改時 fail closed。下列命令可單次產生 current/as-of Context、Kbar/Tick qualification 與 TAIFEX 官方日報 reconciliation。歷史 backfill 不使用這個 current/as-of Context 命令，也不會用現在的 `TXFR1.target_code` 補過去 identity。

```bash
PROVIDER=shioaji .venv/bin/python scripts/capture_taifex_night_context.py
PROVIDER=shioaji .venv/bin/python scripts/capture_taifex_night_qualification.py
.venv/bin/python scripts/capture_taifex_night_reconciliation.py \
  --context-digest <existing-context-sha256>
```

Qualification 是 completed-session 的單次 after-market query，不放進 dashboard polling。即使 Tick／Kbar OHLCV 一致，狀態仍是 `CAPTURED_UNQUALIFIED`，直到 source completion evidence 經 review 後另行版本化。TAIFEX 夜盤日報的 settlement 欄若為 `-` 就保存為 `null`，不拿 Shioaji reference 代替；官方成交量包含價差與鉅額交易契約，在與 Shioaji volume basis 證明一致前只保存、不做等值比較，因此 OHLC 相符時 reconciliation 仍是 `PARTIAL`。

這個 panel 是 observation-only：不會改 Candidate、Buy Score、RiskGate、本機模擬成交或任何委託。`taifex_overnight_context_v0` 在策略目錄中是 `EXPERIMENTAL` SIGNAL；既有 `premarket_gap_watchlist_v1` 仍是 `DRAFT`。可用下列 feature flags 關閉 capture 或 UI；日盤確認與策略影響在 V0 固定不啟用，設定為 `true` 會 fail closed：

```bash
TAIFEX_PREMARKET_CAPTURE_ENABLED=true
TAIFEX_PREMARKET_DASHBOARD_ENABLED=true
TAIFEX_DAY_OPEN_CONFIRMATION_ENABLED=false
TAIFEX_CONTEXT_AFFECTS_DECISIONS=false
```

「盤中動能」是獨立的即時 Shadow 研究工作區。後端每 30 秒掃描一次目前候選池，並對候選以 Shioaji Tick＋BidAsk 持續重算 `hypothesis_v0` 的盤中 Evidence Score。清單會列出每檔候選的盤中分數、策略是否觸發、所有已成立規則及其觀測值、候選規則、最後訊號時間與資料狀態；點選任一列可開啟唯讀明細 Dialog，查看候選快照、盤中 feature、完整規則證據、資料時間與版本。

瀏覽器第一次以 `GET /api/dashboard/momentum` 取得全部觀察股與 `stream_id + revision`，後續由 `/ws/dashboard/momentum` 接續推送完整 row delta。後端預設每 500ms 比對一次已完成的 projection，只有內容變更才增加 revision 並推送；沒有成交時仍每 10 秒送 heartbeat。WebSocket 健康時不會再每 2 秒 GET Momentum API；斷線期間才啟用 2 秒 HTTP fallback，並以 cursor replay 或完整 resync 避免漏資料。Dialog 沿用同一份 browser state，不會在點擊時再次查詢 Provider。

「等待 Tick／BidAsk 暖機」表示該檔尚未形成可評估 projection，不是前端更新卡住。Shioaji 行情本身是事件推送；Tick 有 `average_price` 時 VWAP 可立即取得，BidAsk 到齊後也能建立五檔指標，但成交量加速需要目前 2 分鐘 window 加上至少 4 個完整的 2 分鐘 baseline window，因此完整 Evidence Score 約需 10 分鐘連續 Tick coverage。候選池更新時間和 Tick／BidAsk 訊號時間會分開顯示，不能把掃描快照誤認為即時分數。

Momentum WebSocket 預設啟用，第一版只支援目前的單一 Uvicorn process。可用下列環境變數調整或回退；多 worker／多 replica 需先加入外部 stream broker，不能直接沿用 process-local revision：

```bash
MOMENTUM_DASHBOARD_WS_ENABLED=true
MOMENTUM_DASHBOARD_WS_COALESCE_SECONDS=0.5
MOMENTUM_DASHBOARD_WS_HEARTBEAT_SECONDS=10
MOMENTUM_DASHBOARD_WS_REPLAY_CAPACITY=256
MOMENTUM_DASHBOARD_WS_SEND_TIMEOUT_SECONDS=2
MOMENTUM_DASHBOARD_WS_MAX_CLIENTS=32
```

每檔候選使用一對 Tick／BidAsk 訂閱，最多同時評估 100 檔。超過容量、尚未收到完整行情或訂閱尚未確認的候選仍會出現在清單中，但會標示無法評估原因，絕不顯示為 0 分。若即時 Shioaji 資料未配置或連線失敗，畫面會直接顯示「即時資料不可用」，不會退回固定 Replay 資料。Evidence Score 是規則證據，不是漲停機率，也不是買進或下單指令。

左側的「模擬下單」可建立本機紙上限價委託；「委託」可查看已送出、成交、取消或拒絕的紀錄；「持倉」只顯示由已成交模擬委託建立的股票與其平均成交價、最新成交、買一／賣一、市值和損益。這些功能會開啟整頁工作區；瀏覽器在初次快照後連線 `/ws/simulation/projection`，後端每 250ms 檢查一次內存投影，價格、買一／賣一或損益改變時就透過 WebSocket 推送。WebSocket 斷線期間才每 2 秒讀取 HTTP 投影作為備援；這兩種畫面傳輸都不會輪詢 Shioaji snapshot 或帳務 API。

這個功能是 **LOCAL_PAPER_SIMULATION**：預設虛擬現金為 1,000 萬元，只支援多頭現股限價單，委託量使用正整數股數；1～999 股可作為零股本機模擬，1,000 股以上也不會強制取整張，不計手續費或稅金。使用 `PROVIDER=shioaji` 時，後端只對持倉與尚未成交委託動態訂閱既有的整股 Tick＋BidAsk；買進以賣一、賣出以買一作為本機參考撮合價，Tick 用來更新持倉市值與未實現損益。這不是證交所零股五檔撮合，也不代表 Shioaji Simulation 或券商成交。每檔使用兩個行情訂閱，程式最多允許同時監控 100 檔。若使用 MockProvider，則保留 snapshot 立即撮合，方便離線開發與測試。

委託會經過 `PENDING`、`PARTIALLY_FILLED`、`FILLED`、`CANCELLED`、`EXPIRED` 或 `RECOVERY_REQUIRED` 等明確狀態。最優一檔量可限制每次本機成交量；未成交餘量會保留，逾時取消或到期後只能建立有次數上限的 successor order。timeout、expiry 與恢復異常會顯示在模擬工作區。Shioaji 登入明確使用 `subscribe_trade=False`，沒有啟用憑證、註冊委託 callback 或呼叫下單 API；因此它仍不是 Shioaji Simulation 帳戶，也不會送出任何真實券商委託。

LOCAL_PAPER Journal 預設使用明確的 `memory` adapter。若要保存 command、risk decision、fill、rejection、cancel 與 projection checkpoint，可安裝 `postgres` extra 並設定：

```bash
TRADING_JOURNAL_BACKEND=postgresql
DATABASE_URL=postgresql://user:password@127.0.0.1:5432/tw_intraday_trader
```

現有環境在過渡期間也相容 `PostgreSQL_DSN`。啟動時會套用 forward-only migrations，資料表位於 `trading` logical schema，runtime 使用 bounded connection pool；資料庫無法連線、migration 或 health check 失敗時不會退回 memory 接單。runtime 使用固定的 checkpointed LOCAL_PAPER session，會從 Journal 驗證並恢復現金、持倉歸屬、委託狀態、未成交保留量、冪等識別、每日開盤權益基準及 lifecycle alerts；已核准但缺少 simulator acknowledgement 的命令會以 `RECOVERY_REQUIRED` fail closed，不會自動重送。quote cache 不會偽造恢復，重啟後仍須等待新的 Tick／BidAsk。若保留預設 `memory` adapter，資料只存在目前 process，不能宣稱跨 process 恢復。

Phase 5 的 operator UAT 不允許 memory fallback。請把一次性測試資料庫填入
`TEST_POSTGRES_DSN`，再執行：

```bash
TEST_POSTGRES_DSN=postgresql://... \
  .venv/bin/python scripts/run_phase5_paper_sell_uat.py
```

runner 會固定驗證 ownership 拒賣、stale BidAsk、SELL rejection、timeout/retry、
partial fill、13:30 reconciliation，以及以新 PostgreSQL connection 重建三次 runtime
後的持倉、掛單、reservation、冪等與 alert 一致性。

### 策略模擬意圖邊界

原本接受 caller 自行提供 `strategy_id/version` 的
`POST /api/simulation/strategy-intents` 已關閉，避免繞過 exact Strategy Set 與
`PAPER_APPROVED` lifecycle admission。策略意圖只能由已人工啟動的 Atomic Local Paper
控制器在 process 內產生；它仍會先寫入 Journal，再走相同的 Hard Risk 與
SimulationService。瀏覽器不能直接製造任意策略 BUY／SELL 意圖。

### Exact Strategy Set 自動模擬

「模擬下單」工作區提供必須人工啟動的 Atomic Local Paper 控制器。啟動前必須選擇一個
PostgreSQL 保存的 immutable `ENTRY` Strategy Set Version，並明確輸入停損百分比、停利
百分比與每日最大虧損金額；系統不提供未經校準的預設風險值。目前已接上 Local Paper
runtime binding 的原子進場策略是「站上 VWAP」、「突破盤中前高」、「區間報酬門檻」、
「成交量加速」、「開盤區間突破 ORB」、「EMA 黃金交叉」、「RSI 超賣」與
「Bollinger 下軌回歸」，可用 `ANY`、`ALL` 或
`AT_LEAST_N` 組合。滾動
策略的分鐘視窗與門檻由 immutable Strategy Version 參數決定；2 分鐘與 3 分鐘會使用不同
Feature Request／state identity，不會共用計算結果。ORB 的開盤區間分鐘數、突破 buffer 與
進場時間也由 Version 保存；從 09:00 起缺少任何一根必要的一分鐘 Kbar 時會 fail closed。
EMA 的快速／慢速週期也由 Version 保存；只有前一根快速 EMA 尚未高於慢速 EMA、目前完整
Kbar 才嚴格高於時觸發一次。暖機不足或 09:00 起的 session prefix 缺分鐘會 fail closed。
RSI 的 Wilder 週期與超賣門檻同樣由 Version 保存；目前 RSI 等於或低於門檻時觸發。
「RSI 超賣」與「Bollinger 下軌回歸」維持兩個獨立策略，不會重新包成單一規則群組。
Bollinger 的週期與標準差倍數由 Version 保存；只有上一根收盤嚴格低於當時下軌、目前完整
Kbar 收盤回到目前下軌以上時才觸發一次，暖機不足或 09:00 起缺分鐘會 fail closed。
每次啟動會重新核對 Strategy Version、參數、Template、Schema、
implementation 與 runtime binding digest；任一身分漂移都會 fail closed。
Strategy Set 內每個 Version 的 PostgreSQL lifecycle projection 還必須正好是
`PAPER_APPROVED`；activation 會在同一個 transaction 鎖定 Set、Version、projection 與
最後一筆 lifecycle event，並把 sequence、event ID、projection digest 收入 Pipeline
snapshot。`PUBLISHED`、`REVIEWED`、`BACKTESTED`、`PAUSED` 或 `RETIRED` 都不能啟動。

策略判斷直接使用既有 Momentum Shadow 的 canonical `FeatureEngine` projection，不會另建
第三套 VWAP／前高計算器。即時來源必須是 live、連線為 `RUNNING`、資料健康為 `HEALTHY`，
Tick 與可執行 BidAsk 也必須在新鮮度範圍內；策略以 Tick 現價評估，進場模擬限價使用
最新賣一。Candidate 快照分數只用於候選訂閱優先順序，不是買進條件。

第一版固定一張、最多一個持倉、每次啟動最多一筆進場。TWSE 交易日 09:00～13:20
可進場；持倉達到人工輸入的停損或停利時，會以五秒內的最新買一送出全數本機模擬
賣單，13:25 起也會嘗試強制出場。缺少 reviewed calendar、Mock／Snapshot 模式、行情
不健康、資料過期、多持倉、既有掛單或達每日虧損上限時都會 fail closed，原因會顯示
在工作區狀態。每日最大虧損不是 controller-only 提示：每次啟動會用
`min(system ceiling, operator limit)` 建立該 exact Set owner 專用的 Effective Hard Risk
Policy；完整 policy、digest、權益虧損 snapshot 與 decision 會寫入 Journal，checkpoint
也會保存並在重新啟動時核對。相同股票的不同 owner 掛單會在保留額度前拒絕，撮合時
仍會在 lock 內再次核對，禁止把手動與自動策略持倉合併。

Momentum runtime 與 Dashboard 目前沒有跨交易日 hot rollover。單機 MVP 請在每個交易日
開始前重啟 Dashboard；若 process 跨日持續執行，新日期行情會 fail closed。第一次使用
Parameterized Local Paper 前，仍應在盤中以真實行情完成一次 smoke test。

啟動方式：

```bash
PROVIDER=shioaji .venv/bin/python -m dashboard
```

先到「策略管理」依序建立／驗證／發布策略版本，再用已發布的 `ENTRY` versions 建立策略
組合。因 Local Paper binding 會進入 Template identity，舊 Template 建立的版本不會被
靜默沿用；若選單沒有可用版本，必須重新發布目前 Template 的版本。接著開啟「模擬下單」，
選擇精確的進場策略組合、填入三個風險參數後按「啟動自動模擬」。也可透過
`GET /api/simulation/automated-strategy` 讀取狀態、
`POST /api/simulation/automated-strategy/start` 啟動，以及
`POST /api/simulation/automated-strategy/stop` 停止。start payload 必須包含
`entry_strategy_set_version_id`、`stop_loss_pct`、`take_profit_pct`、`max_daily_loss`、
`actor_id` 與 `activation_idempotency_key`；瀏覽器會在 response-loss retry 保留同一個
activation key。所有 mutation 都受 loopback、完整 Origin 與 CSRF 防護。另有「緊急停止」可立即禁止新的自動
意圖；解除後仍維持 `STOPPED`，必須再次人工啟動。一般停止只阻止新的自動意圖，不會
擅自清除既有持倉；Dashboard 重啟後控制器固定為停止。若 Journal 使用 PostgreSQL，
本機模擬委託、持倉、保留量與交易日風控基準會恢復，但仍須由操作人重新啟動控制器；
策略 runtime checkpoint 也會用 exact Strategy Set owner 與 pipeline digest 恢復 signal dedup
狀態。預設 memory adapter 則不提供跨 process 恢復。

MVP audit 限制：start activation 已保存 actor、完整 config 與 durable idempotency result；
stop、kill-switch engage/reset 目前仍是 process-local control，尚未各自保存 actor 與 durable
idempotency operation。這項限制必須在多使用者、外網、自動 promotion 或任何正式交易前
補齊；目前不能把 Local Paper control audit 宣稱為完整多使用者稽核。

自動控制器只把意圖送入既有
`Journal → ProposedOrderCommand → RiskGate → ApprovedOrderCommand → SimulationService`
路徑；proposal、Risk snapshot、effective policy、decision 與 approved command 都保存
穩定 digest，Simulation adapter 會拒絕未核准的 proposal。沒有
CA、券商委託 callback、`place_order` 或 `subscribe_trade=True`。目前撮合支援最優一檔量
限制下的部分成交，但仍不計手續費、證交稅、滑價與真實排隊順位，所以適合策略流程與
多日 paper evidence，不代表可直接升級為真實交易。

---

## 歷史回測（資料研究，不會下單）

在儀表板左側點選「歷史回測」，即可開啟整頁研究工作區；工作流程拆成四個 tab：

1. 準備歷史資料：建立或選擇封存的歷史資料集；按「建立資料集」會在背景透過後端 Provider 下載 Kbar，不會卡住網頁。
2. 設定策略組合：分別選擇買入與賣出策略，每一側可只選 1 個獨立執行，也可複選多個並設定 `ANY`、`ALL` 或「至少 N 個」條件。
3. 回測工作與結果：建立回測後，可查看進度、取消、失敗重試、OOS 勝率／信賴區間、損益、回撤、Profit Factor、交易明細與策略歸因。
4. 比較與資格判定：先比較兩個已完成 Run；正式 qualification 只填固定 train／validation／Primary OOS 日期與 walk-forward folds，attempt history、multiple-testing family 與門檻由伺服器 ledger／policy 產生，再把不可變 evidence 寫入 PostgreSQL。

點選交易可查看該筆進出場的主要策略、所有同時觸發策略、門檻與當時觀測值；也可以匯出 CSV。

回測使用獨立的 `backtest/` composition：只讀已封存的資料集，買入訊號最早在下一根 Kbar 才成交，並納入手續費、賣出證交稅與滑價。它不會啟動本機紙上模擬、Shioaji 下單、帳務、CA 或 trade subscription。

`backtest-engine-v2` 另外提供五個預設不勾選的 1 分 K `EXPERIMENTAL` 策略：開盤區間突破、EMA(5/20) 黃金交叉、RSI／布林通道均值回歸、固定 ATR 停損，以及 12 根一分鐘 Kbar 的時間退出。這些策略只接受資料 manifest 同時證明 `OHLCV`、`KBAR_INTRADAY`、`KBAR_1M`、`SESSION_BOUNDARIES`；API 建立 Run 與 worker 執行前都會再次驗證。舊 manifest 不會被原地升級，若缺少能力欄位，需要重新封存資料集。

日 K SMA20／SMA60 也已是兩個預設不勾選的 `EXPERIMENTAL` 策略：`sma_20_60_golden_cross_entry_v1` 在完整日 K 收盤確認 SMA20 上穿 SMA60 後，建立下一個有效日 K 開盤買入；`sma_20_60_death_cross_exit_v1` 對應下穿，於下一個有效日 K 開盤退出。兩者都要求 `OHLCV` 與 `KBAR_DAILY`，並將 `DAILY_NEXT_BAR` 存入決策、委託與成交結果；資料結束前沒有下一個有效日 K 時，委託會明確標示 `UNFILLED_END_OF_DATA`，不會以當日收盤價偷填。儀表板不會預設勾選它們；若使用者同時選擇 `end_of_day_exit_v1`，會顯示「每日日 K 收盤平倉」的非阻擋提醒，但不會替使用者改掉策略選擇。

`KBAR_DAILY` 不會由「某天只有一根 Kbar」或圖表資料推論。Provider Kbar 在封存前會先正規化為 `Asia/Taipei` 的 `session_date`；G0 目前選定 `DERIVED_FINALIZED_SESSION_V1`：base dataset 的每個 `(symbol, session_date)` 還必須都有獨立的 source-completion evidence digest，才可 materialize 成 immutable daily child。child 保留完成收盤的 `timestamp` 作為訊號時間，並另外保留第一根來源 Kbar 的 `session_open_at` 作為下一日開盤成交的稽核時間。它一律記錄 `RAW`、`corporate_action_adjusted: false`、`REGULAR_SESSION`／`COMMON_LOT` volume contract 與 parent digest；可重現策略工程，但不可宣稱正式 alpha。現有 G0 fixture 只證明 2330 的單一歷史 session，不能拿來授權整個下載資料集。

可在準備好完整 evidence bundle 後執行離線派生（不會連 Provider 或券商）：

```bash
python scripts/derive_backtest_daily_dataset.py \
  --base-dataset-id dataset-已驗證的分鐘資料 \
  --dataset-id dataset-derived-daily-v1 \
  --completion-proofs /secure-data/daily-session-proofs.json
```

`daily-session-proofs.json` 必須使用 `daily-session-completion-proofs-v1`，包含 `session_contract`、`volume_contract` 以及 base 每一個 `(symbol, session_date)` 的唯一 `symbol`、`session_date`、`digest`。缺少、重複、額外或與 parent 不相符的 proof 都會 fail closed；相同 dataset ID 若契約不同也會拒絕覆寫。

資料 cadence 依每個 `(symbol, session_date)` 的 timestamp 間距推導，不再用整個市場單日總筆數猜測。一分鐘資料仍可有缺 bar，但需要完整 09:00～09:14 的 ORB 當日才會產生有效 opening range；indicator 全程使用 `Decimal`，每個 session 重新 warm-up。舊的 `backtest-engine-v1` Run 仍可用原版本重試，新 Run 預設使用 v2。

正式 runtime 預設使用 PostgreSQL 單一 database 的 `backtest` logical schema；可直接設定 `BACKTEST_DATABASE_URL=postgresql://...`，或設定 `BACKTEST_DATABASE_BACKEND=postgresql` 來沿用 `DATABASE_URL`／`POSTGRESQL_DSN`／舊版 `PostgreSQL_DSN`。未提供 DSN 時會 fail closed，不會自動建立新的 SQLite 權威；SQLite adapter 僅供顯式 local dev 與測試：

```bash
python3 -m pip install -e ".[postgres,dev]"
BACKTEST_DATABASE_URL='postgresql://user:password@host:5432/tw_backtest' python3 -m dashboard
```

既有 SQLite 搬遷採唯讀、可重跑流程；工具會保留原檔，將 stale `RUNNING` job 在目的端轉為可續跑的 `PAUSED`，並在十張表的筆數與內容 digest 全部一致後才回報成功：

```bash
.venv/bin/python scripts/migrate_backtest_sqlite_to_postgres.py \
  --sqlite data/backtest/backtest.sqlite3
```

驗證通過後才設定 `BACKTEST_DATABASE_BACKEND=postgresql`。若已另有 PostgreSQL backup／restore 能力，可以移除舊 SQLite；不可讓 SQLite 與 PostgreSQL 同時 claim 新工作。

FinMind snapshot 封存完成後，可用 saved plan 重新驗證完整 artifact，再以
PostgreSQL-only transaction 註冊 immutable Dataset 並切換預設回測 binding：

```bash
BACKTEST_DATABASE_URL='postgresql://user:password@host:5432/tw_backtest' \
  .venv/bin/python scripts/materialize_finmind_backtest_dataset.py \
  --execute \
  --plan-file data/backtest/finmind_plans/<operation>/snapshot-plan.json \
  --activate-default \
  --expected-binding-revision 0 \
  --activation-idempotency-key <stable-key> \
  --actor local-researcher \
  --change-note 'activate verified FinMind snapshot'
```

首次 binding 的 expected revision 是 `0`；之後必須使用目前 revision。相同
idempotency key 與相同 request 會回放原結果，相同 target 搭配新 key 是不增加
revision 的 no-op，stale revision 或不同 request 重用同 key 都會 fail closed。
這條 activation 不支援 SQLite fallback，也不會啟動 Web Run、Local Paper 或券商下單。

原子策略平台的 Template、Draft、immutable Version、Publish event/state/outbox、Publish operation、mutation audit 與 exact-version Strategy Set 固定使用 PostgreSQL；這些 mutation 不支援 SQLite，也不會在 PostgreSQL unavailable 時 fallback。Dashboard handler 與背景 backtest worker 透過 bounded PostgreSQL connection pool 在每次 operation checkout，各 transaction 不共用單一 connection／rollback 狀態。

Dashboard 啟動後，可用以下歷史回測流程：

1. 開啟左側「策略管理」，選擇伺服器提供的策略 Template；表單欄位、預設值、範圍與單位都由 code-owned Schema 產生。
2. 儲存 Draft、執行驗證，再 Publish 成不可修改的 Version；參數變更必須複製成新 Draft／Version，不會覆寫舊回測所引用的版本。
3. 選取一個或多個相同 stage 的精確 Version，建立 `ANY`、`ALL` 或 `AT_LEAST_N` Strategy Set。
4. 到「歷史回測」選擇 READY 資料集與該 Strategy Set，再送出原子策略回測。Run 會保存完整 Set、Version、Feature Specification、implementation digest 與 as-of semantics；複製或重試也不接受 raw strategy ID 覆寫。建立要接受正式資格判定的 Challenger 時，必須在同一表單選擇一個已完成 Atomic Baseline；伺服器會由 Dataset／config／成本／adapter、精確 Baseline Strategy Version 與研究 protocol 推導穩定的 research-baseline identity，並在建立 Run 的同一個 PostgreSQL transaction 登錄單調 attempt sequence。相同研究基準即使重新執行成不同 Run ID，也會回到同一個 family 與同一份嘗試額度。
5. 到「比較與資格判定」選取該 Baseline／Challenger，只需填寫研究假設、固定切割與 walk-forward folds。所有 fold OOS 都必須在 Primary OOS 開始前結束，不能重複使用最終 OOS 證據。完整 attempted Run history、family head、Bonferroni alpha／planned attempts 與門檻都由伺服器 ledger/policy 產生，瀏覽器不能覆寫。系統會核對 Run config/result、Run row 與 config 內的 Dataset identity、DatasetManifest、成本／資金／exit contract 與 Feature adapter identity，再建立不可變 qualification；通過只代表可送人工 promotion Review，不會自動啟用策略。Qualification 會保存可驗證 digest 的 immutable family snapshot，detail API 另外提供目前 family linkage，讓 Reviewer 分辨當時 evidence 與後續 hypothesis／qualification 關聯。

目前這條 Phase 3 流程只接歷史回測，ENTRY Set 仍搭配既有伺服器端收盤退出政策；不會啟動本機紙上模擬、模擬交易、Shioaji／券商委託或 real-money execution。固定政策至少要求 Primary OOS 30 筆、10 個獨立交易日、最大回撤 20%，以及至少 2 個位於 Primary OOS 之前的 Walk-forward folds；family alpha 固定 5%、最多 20 次嘗試。新 mutation API 僅接受 loopback client、同源請求、process CSRF token 與 idempotency key，成功與衝突結果都保留 PostgreSQL audit evidence。Qualification persistence 固定使用 PostgreSQL；SQLite 開發模式可繼續使用舊版回測，但畫面會明確顯示不能建立正式資格證據。

PostgreSQL migration、row lock 與 concurrent Publish 測試必須使用明確的專用測試資料庫。測試 fixture 會刪除該資料庫中的 `backtest` schema，並在執行前要求 database 名稱含獨立的 `test` token（例如 `_test`）；不符合時會直接拒絕 cleanup。只有受控的 disposable database 才可明確設定 `ALLOW_POSTGRES_TEST_SCHEMA_RESET=1` 覆寫名稱檢查，請勿填入開發或正式環境 DSN：

```bash
python3 -m pip install -e ".[dev,postgres]"
TEST_POSTGRES_DSN='postgresql://user:password@127.0.0.1:5432/tw_intraday_trader_test' \
  .venv/bin/python -m pytest -q \
  tests/test_strategy_migrations.py \
  tests/test_strategy_publish_idempotency.py \
  tests/test_backtest_qualification_postgres.py
```

沒有 `TEST_POSTGRES_DSN` 時，上述 PostgreSQL integration tests 會顯示明確 skip；一般 domain／atomic strategy／backtest regression tests 仍會執行，不會改用 SQLite 冒充 PostgreSQL contract evidence。

### 可續傳的歷史資料下載 script

全市場三年 Kbar 不適合只靠瀏覽器背景工作：時間長，而且 Shioaji 另有每日行情流量與查詢頻率限制。可改用獨立 CLI；每完成一檔股票，就會把 canonical JSONL 以 gzip 壓縮後寫入目前回測資料庫的 `backtest_history_partitions`。按 `Ctrl+C`、連線失敗或關閉終端機後，已完成股票不會遺失。

先用少量股票確認帳號、日期與資料量：

```bash
PROVIDER=shioaji .venv/bin/python scripts/download_backtest_history.py \
  --years 3 \
  --symbols 2330 2317
```

確認後下載目前 Provider 可列出的全部股票：

```bash
PROVIDER=shioaji .venv/bin/python scripts/download_backtest_history.py --years 3
```

script 啟動時會先輸出 `dataset-download-*` 工作 ID。若中斷，使用相同 Provider 接續：

```bash
PROVIDER=shioaji .venv/bin/python scripts/download_backtest_history.py \
  --resume dataset-download-請替換成實際ID
```

Downloader 會把 Shioaji Kbar 查詢限制在每 10 秒最多 40 次，低於官方 50 次上限；每次查詢前也會讀取 `api.usage()`，至少保留 16 MiB 安全流量。每個 Kbar request 的 timeout 為 60 秒，逾時時最多重試 3 次（2 秒、5 秒退避）；仍失敗時，工作會保存目前股票代碼並標為 `PAUSED`，下次只重試該檔。若接近每日上限，或收到無法判定為真實無資料的空 Kbar，也會以 exit code `75` 安全暫停，不會把 0 根資料誤存成完成。逾時可稍後直接接續；Shioaji 流量不足則等交易日上午 `08:00` 重置後再執行同一個 `--resume` 指令。

舊版 Downloader 已經寫入「資料來源未回傳 Kbar」的工作也可以直接使用新版 `--resume`。新版會保留第一個 0 根異常以前的成功資料，並重抓該異常與後續尾段；不需要刪除資料庫，也不要建立新的 job。不同商品可能因 Provider 可提供的歷史範圍而同時只回傳約一年資料，因此不會只憑共同起始日把非零分區判定為損壞。

SQLite 預設寫入 `data/backtest/backtest.sqlite3`；若有設定 PostgreSQL backend 或 `BACKTEST_DATABASE_URL=postgresql://...`，partition 與工作進度會寫入 PostgreSQL 的 `backtest` schema。全部完成後，script 會以 streaming 方式封存 `bars.jsonl`／`manifest.json`、驗證 SHA-256，並在 `backtest_datasets` 登記為 `READY`；回到網頁按「重新整理」即可選取。

不要同時執行網頁的「建立資料集」與 CLI 全市場下載，否則不同 process 無法共用同一個頻率限制器，也會重複消耗 Provider 額度。舊版已經在執行中的網頁工作沒有資料庫 partition，無法把其中途進度轉成新的 `--resume` 工作；請先在網頁取消，再啟動或接續 CLI。

### 收盤後自動增量同步

Dashboard process 啟動時會啟用收盤排程。預設每個工作日 `14:30`（`Asia/Taipei`）檢查一次最新的 `READY` Provider 資料集，只重抓每檔股票最後一根 Kbar 所在日期到今天，並把 watermark 以前的重疊資料排除。舊資料集不會被改寫；有新 Kbar 時會建立 `parent + delta` 的新 immutable dataset，沒有新資料時只記錄本日已檢查並沿用原資料集。

第一次仍需先用上述 CLI 完成三年基礎資料集。若完整下載仍在執行，排程會顯示「等待既有下載工作」並持續重試，不會再啟動另一份全市場下載。休市日不會建立空資料集；程式停機數日後再次於收盤時間運行，會從各檔既有 watermark 接續到當天。

排程狀態會顯示在網頁「歷史回測 → 準備歷史資料」，也可以讀取 `GET /api/backtests/datasets/incremental-sync`。若修改設定，需要重新啟動 Dashboard：

```bash
BACKTEST_INCREMENTAL_SYNC_ENABLED=true
BACKTEST_INCREMENTAL_SYNC_CLOSE_TIME=14:30
BACKTEST_INCREMENTAL_SYNC_POLL_SECONDS=60
BACKTEST_INCREMENTAL_SYNC_OVERLAP_DAYS=1
BACKTEST_ACTIVE_JOB_STALE_MINUTES=30
```

這是應用程式內排程，因此電腦與 Dashboard process 必須運行。目前正式 runtime 使用 PostgreSQL；SQLite 僅供顯式 dev/test。若平台部署多個 Web process，應只讓一個 process 啟用排程，其他 process 設定 `BACKTEST_INCREMENTAL_SYNC_ENABLED=false`。

其他可用設定：`BACKTEST_ENABLED`（預設 `true`）、`BACKTEST_DATA_DIR`（預設 `data/backtest`）、`BACKTEST_DATABASE_BACKEND`、`BACKTEST_DATABASE_URL` 與 `BACKTEST_WORKERS`。完整驗證可先執行：

```bash
python3 -m pytest -q tests/test_backtest_core.py tests/test_backtest_api.py
```

### 統一策略目錄

左側的「策略目錄」會讀取 `/api/strategies`，集中顯示所有策略家族，不限於回測可執行的買入／賣出策略。每個版本包含：

- `role`：`CANDIDATE`、`SCORE`、`SIGNAL`、`ENTRY`、`EXIT`
- `session_phase`：`PRE_MARKET`、`OPENING`、`INTRADAY`、`END_OF_DAY`、`POSITION_LIFECYCLE`
- `status`、資料能力、execution binding、標籤與可任意巢狀的 JSON `parameters`

`/api/backtests/strategies` 只會回傳已在伺服器註冊、且目錄版本與 execution binding 完全一致的 `ENTRY`／`EXIT` 策略。目錄中的候選、評分、訊號、草稿或尚未接上歷史執行器的研究策略不會出現在回測選單，也不會因資料庫 metadata 而被當成程式執行。

目前的盤前跳空觀察名單定義會標示為 `DRAFT`，因為現有資料流程尚未提供盤前試撮資料；開盤跳空、高成交量、VWAP、動能與回測策略則會各自標示實際時段與研究狀態。這樣可以先統一目錄，再逐步接上候選池與盤中決策，不會把「候選」誤當成「買入」。

策略版本是 immutable：同一個 `strategy_id + version` 若內容不同，API 會拒絕覆蓋，必須建立新版本。新增或調整資料庫策略可使用 `POST /api/strategies`；新邏輯先存為 `DRAFT`，只有已部署且白名單內的 execution binding 才能標為 `ACTIVE`／`EXPERIMENTAL`。資料庫只保存定義與參數，不會直接執行任意程式碼。

### 近三年全市場的資料限制

透過目前 Provider 直接下載時，只能列出「今天仍存在」的 contracts；系統會把這種資料集標為 `CURRENT_SNAPSHOT`／探索性，並禁止它得到 `RESEARCH_PASS`，避免把 survivorship bias 當成正式勝率證據。要驗證「近三年所有當時可交易的台股」，必須先匯入含 date-effective 上市／下市、商品類型、交易日與調整／參考價資訊的資料集，並將其登錄為 `DATE_EFFECTIVE`。系統已保留這種 immutable import contract；沒有這些歷史 universe 資料時，網頁仍可執行回測，但結果只能用於探索，不能宣稱涵蓋完整市場。

完整資料由受控的 server-side JSONL 匯入，不從瀏覽器上傳。每行必須是 `HistoricalBar.to_dict()` 的 JSON；資料經過 OHLC、時區、重複列與 SHA-256 驗證後，才會出現在網頁的資料集選單：

```bash
python scripts/import_backtest_dataset.py \
  --bars /secure-data/twse_tpex_2023_2026_1m.jsonl \
  --source twse-tpex-date-effective-v1 \
  --universe-scope DATE_EFFECTIVE \
  --research-eligible
```

---

## 切換至 Shioaji 真實資料

編輯 `.env` 或 `config/settings.py`：

```env
PROVIDER=shioaji
SHIOAJI_API_KEY=your_key
SHIOAJI_SECRET=your_secret
```

---

## 手動觀察清單

編輯 `config/settings.py`：

```python
MANUAL_WATCHLIST = {
    "2376",
    "3231",
}
```

手動加入的股票**永遠進入 Candidate Pool**，不會被自動掃描移除。

---

## 持倉管理

掃描結果目前仍在 `app.py` 直接設定一筆示範持倉，用於既有出場規則展示：

```python
position_manager.add(Position(symbol="2317", entry_price=205.0, quantity=1000))
```

Web 的「模擬持倉」與這筆示範資料分開，完全由 `simulation/` 中已成交的本機紙上委託推導。後續策略自動下單應呼叫同一個 `SimulationService.submit_order()` 指令入口，而非由瀏覽器或策略程式直接操作券商 SDK。

---

## 執行測試

```bash
python3 -m pytest tests/ -v
```

---

## 專案結構

```text
tw_intraday_trader/
├── app.py                  # Orchestration layer（主程式）
├── market_data/
│   ├── models.py           # StockData
│   └── provider.py         # Snapshot、Kbar、台指期盤前與 Shioaji Tick/BidAsk adapter
├── premarket/
│   ├── calendar.py         # TAIFEX trading-date、session 與 historical identity resolver
│   ├── models.py           # Context／Reconciliation immutable contracts
│   ├── artifacts.py        # Canonical SHA-256 與 durable content-addressed repository
│   ├── qualification.py    # Shioaji Kbar／Tick fail-closed qualification
│   ├── service.py          # Observation-only aggregation、READY 與 Dashboard projection
│   ├── reconciliation.py   # 獨立 reconciliation artifact service
│   └── taifex_reconciliation.py # TAIFEX 官方盤後日報 acquisition／parser
├── candidate/
│   ├── models.py           # Candidate
│   ├── rules.py            # GapUpRule, HighVolumeRule
│   └── engine.py           # CandidateEngine
├── scoring/
│   ├── models.py           # ScoreDetail, BuyScoreResult
│   ├── rules.py            # AboveVWAPRule, GapScoreRule
│   └── engine.py           # BuyScoreEngine
├── position/
│   ├── models.py           # Position
│   ├── manager.py          # PositionManager
│   └── exit_rules.py       # StopLossRule, TakeProfitRule
├── config/
│   ├── settings.py         # 既有 threshold 與設定
│   ├── premarket.py        # 盤前 feature flags 與 completeness contract
│   └── taifex_calendar_2026.json
├── simulation/
│   └── service.py          # 本機紙上模擬委託與持倉投影
├── strategy_catalog/
│   ├── domain.py           # 統一策略定義、角色、時段、狀態與版本摘要
│   └── service.py          # 內建策略 bootstrap、查詢與版本化保存
└── tests/                  # 單元測試
```

---

## 架構原則

1. 其他模組禁止直接依賴 Shioaji SDK，透過 `MarketDataProvider` 隔離
2. Candidate ≠ 買入訊號，只代表「值得監控」
3. Manual Watchlist 的股票不可被自動掃描移除
4. Position 永遠持續監控（即使不在 Candidate Pool）
5. 評分必須提供 breakdown，不只回傳一個數字
6. 系統級安全與資料設定集中在 `config/`；策略 threshold 隨版本保存在 `strategy_catalog` 定義中
7. 網頁紙上模擬與未來策略程式共用後端下單指令；Shioaji 只提供行情，目前不包含 Shioaji 或真實帳戶下單
