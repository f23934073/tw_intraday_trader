# Execution Layer v1 Implementation Plan（Review Draft）

- 狀態：本機紙上模擬第一切片已完成；其餘 Execution Layer 仍待 review／實作
- 日期：2026-08-18
- 目標範圍：Historical Backtest、Replay、Live-data Shadow、Shioaji Simulation、網頁手動模擬下單與模擬持倉資訊
- 明確排除：Small Live Trading、Production Trading、任何真錢委託

> 實作狀態（2026-08-18）：已完成 `LOCAL_PAPER_SIMULATION`、網頁限價下單／委託／持倉，以及只針對持倉與掛單的 Shioaji Tick＋BidAsk 行情切片。它只以 `subscribe_trade=False` 登入取得行情，不啟用 CA、不呼叫 Shioaji 下單 API，重啟即清空；本計畫內的 authenticated Shioaji Simulation 下單、Replay、Risk 與 Journal gate 仍未實作。

## 1. 結論

原提案的核心方向可以保留：策略不得直接依賴 Shioaji，Broker 必須隔離 Replay 與 Shioaji Simulation，委託也必須用 callback／reconciliation 驅動狀態，而不是把 `place_order()` 成功當作成交。

但目前不建議直接從 `broker/base.py` 開始。現有系統仍是一次性 snapshot scan；時間、資料順序、決策去重、風控、持久化、重啟同步都還沒有契約。若先接 Broker，會得到「可以呼叫模擬下單 API」，但無法證明 Replay、Simulation 與 Journal 的結果一致，也無法安全處理 callback 重送、斷線或重啟。

建議的新順序是：

```text
Contract / Safety Freeze
        ↓
Deterministic Market Events + Replay Clock
        ↓
TradeIntent + Risk + Journal
        ↓
Shared Backtest / Replay Kernel + ReplayBroker
        ↓
Live-data Shadow（不呼叫下單 API）
        ↓
Web Manual Shioaji Simulation
        ↓
Automated Shioaji Simulation
```

這個順序仍沿用 `MarketDataStore`、`CandidateEngine`、`BuyScoreEngine`、`PositionManager` 與 Exit Rules，但會明確區分「可沿用的決策邏輯」和「尚不能當作交易帳本的狀態」。

## 2. 原提案需要調整的地方

| 優先級 | 原提案 | 建議調整 | 原因 |
|---|---|---|---|
| P0 | Phase 4 Small Live、Phase 5 Production 已排入路線 | 從本 plan 移除，未來只能透過新的 scope/RFC 與明確授權重開 | 目前專案與既有邊界都不是實盤系統；不應預先建立 `ShioajiLiveBroker` 或 `live` mode |
| P0 | 策略直接產生含 `qty`、`price`、`order_type` 的 `OrderRequest` | 策略先產生 `TradeIntent`；Risk／Order Factory 再做資金、股數、整股／零股、tick size 與委託型別正規化 | 避免策略層混入券商數量單位與資金風控；泛用 `qty=1000` 具有誤送風險 |
| P0 | Broker interface 是第一個實作項目 | 先定義事件時間、Replay clock、資料健康與 decision identity | 現有 `StockData.timestamp` 有 naive／Asia-Taipei 混用，Store 也是 last-call-wins；先接 Broker 無法保證可重現性 |
| P0 | RiskManager 到 Live Safety 才加入 | Risk 與 Data Health 必須在 Replay、Shadow、Simulation 共用 | 風控若只在 Live 才出現，就從未被相同交易流程充分驗證 |
| P0 | Trading Journal 在自動 Simulation 後才建立 | Journal 在第一筆自動 decision 之前完成 | 沒有 durable journal，就無法處理 callback 重送、restart recovery、order reconciliation 與事後稽核 |
| P0 | `place_order()` 後用線性狀態表示 accepted／filled | Broker 回傳只表示 command result；所有 order/deal callback 與查詢結果要先正規化成 idempotent `OrderEvent` | 官方文件顯示 `place_order` 可能先回 `PendingSubmit`，不能推論已接受或成交 |
| P0 | 範例用 score 82／84 作為 signal | 先凍結真正 strategy contract；目前兩個 scoring rules 的總上限只有 40，`MIN_DISPLAY_SCORE` 也只是 UI filter | 若直接照範例設 threshold，策略永遠不會下單；顯示門檻不能兼任交易門檻 |
| P1 | Historical Backtest 與 Replay Trading 分成兩套流程 | 共用同一個 event-driven kernel，只切換 ReplayClock 速度 | 避免回測與逐筆 Replay 因兩份程式產生語意漂移 |
| P1 | Replay 直接進 Shioaji Simulation | 中間加入 Live-data Shadow | 先驗證即時串流、stale／disconnect、去重、訂閱管理與 Journal，而不觸發任何下單 API |
| P1 | PositionManager 視為成交後的帳務來源 | 保留現有 Position／Exit Rules 作為 decision view；另建 fill-derived PortfolioProjection，並與 Shioaji positions 對帳 | 現有 PositionManager 是手動輸入、以 symbol 覆蓋，缺少 order/fill/account/reconciliation 語意 |
| P1 | 全市場 Scanner 後直接進即時流程 | 採兩層 universe：低頻 discovery + 有上限的 candidate／position subscriptions | 官方訂閱上限目前為 200；snapshot/ticks/kbars 也不可當成盤中輪詢式即時 feed |
| P1 | 範例將 RVOL、Opening Range breakout 當成既有訊號 | 把它們視為 future strategy hypotheses；目前 `run_scan()` 實際使用 GapUp、absolute HighVolume、GapScore、AboveVWAP | 目前 provider 的 `volume_ratio` 也不是嚴格的「過去 N 日同期平均 RVOL」，不能混用語意 |
| P1 | 用「20～30 天」作為主要通過條件 | 保留觀察期，但同時要求資料完整性、決策去重、風控、recovery、reconciliation 與預註冊績效 gate | 跑滿天數不代表系統或策略可信 |
| P1 | 網頁人工下單與未來程式下單可能各做一套 | 兩者都進同一個 `OrderApplicationService`，共用 Risk、idempotency、Journal、OrderFactory、OrderManager 與 Broker | 避免人工下單繞過風控，也避免未來自動下單重寫執行語意 |
| P2 | Dashboard 原本永久維持 read-only | Phase 0～4 繼續唯讀；通過 G4 後才新增 simulation-only order ticket、委託狀態與持倉 projection | 現有 Dashboard 不應成為 provider cadence owner，但可以在明確 Simulation gate 後成為受控 command surface |

## 3. 現有元件怎麼沿用

### 直接沿用

- `CandidateEngine`：保留純選股邏輯，不接 Broker。
- `BuyScoreEngine`：保留 score breakdown，作為 `TradeIntent` 的證據之一。
- Candidate／Scoring rules：Replay、Shadow、Simulation 使用同一份實作。
- Exit Rules：仍產生 exit reason，但要透過 DecisionEngine 轉成可去重的 exit intent。
- Dashboard Candidate／Kbar snapshot：繼續沿用；Phase 5 才另外新增 simulation-only command/query endpoints，不把交易欄位塞回原 snapshot contract。

### 沿用但補強契約

- `MarketDataStore`：繼續當每個 symbol 的最新狀態 projection；不把它當歷史資料庫或 replay event log。
- `StockData`：先維持現有決策輸入，外層新增 timezone-aware market event metadata、received time、source、session 與 sequence。
- `PositionManager`：保留為 Exit Rules／Dashboard 可讀的 position view；資料改由 `PortfolioProjection` 轉入，不直接把 broker callback 寫進現有 dict。
- `run_scan()`：保留 CLI／Dashboard 的一次性 snapshot path；新的長生命週期交易 session 不塞進這個函式。

### 新增的最小邊界

```text
MarketEvent / ReplayClock / DataHealth
TradeIntent / RiskDecision / OrderRequest
Broker / ReplayBroker / ShioajiSimulationBroker
OrderEvent / OrderManager
PortfolioProjection / Reconciler
TradingJournal
OrderApplicationService / SimulationQueryService
TradingSession runners
```

不導入 Kafka、Redis、微服務、CQRS、通用 DI container 或完整 event-sourcing framework。

## 4. 目標架構

```text
 Historical 1m Dataset                     Shioaji Streaming
           │                              Tick / BidAsk
           ↓                                   │
   ReplayEventSource                   ShioajiQuoteFeed
           │                                   │
           └──────────→ bounded event queue ←──┘
                               │
                               ↓
                    MarketDataStore projection
                               │
                    DataHealth + ReplayClock
                               │
                               ↓
                       CandidateEngine
                               ↓
                       BuyScoreEngine
                               ↓
                   TradingDecisionEngine
                               ↓
                         TradeIntent
                               ↓
                    StrategyOrderCommand ───────────┐
                                                   │
 Browser Simulation Order Ticket                   │
               ↓                                   │
       ManualOrderCommand ─────────────────────────┤
                                                   ↓
                                      OrderApplicationService
                                                   ↓
                                      RiskEngine / OrderFactory
                      │ allowed        │ rejected
                      ↓                └────→ Journal
                    OrderRequest
                          │
                 Broker protocol
                ┌─────────┴──────────┐
                ↓                    ↓
          ReplayBroker     ShioajiSimulationBroker
                │                    │
                └─────────┬──────────┘
                          ↓
                 normalized OrderEvent
                          ↓
               OrderManager + Journal
                          ↓
                 PortfolioProjection
                     ┌────┴──────────────┐
                     ↓                   ↓
           Position view / Exit Rules   SimulationQueryService
                                             ↓
                              Browser Orders / Holdings views
```

Historical Backtest 與 Replay Trading 只差時鐘：Backtest 盡可能快地推進 event time；Replay 以 1x 或指定倍率播放。策略、Risk、ReplayBroker、OrderManager 與 Journal 必須相同。

## 5. 核心資料契約

### 5.1 MarketEvent

至少包含：

- `session_id`
- `source`
- `symbol`
- `event_type`（第一版從 completed `BAR_1M` 開始；之後加入 `TICK`／`BID_ASK`）
- `event_at`（交易所／資料事件時間，timezone-aware Asia/Taipei）
- `received_at`（系統接收時間）
- `source_sequence` 或可辨識的來源 key
- `payload`

規則：

- 同一 source stream 的舊資料不得覆蓋新 projection。
- Tick 與 BidAsk 是不同 stream，不假設兩者 exchange timestamp 可形成單一全序。
- 發現 gap、queue overflow、時間倒退或 stale 時，DataHealth 必須 fail closed，阻擋新 entry intent。
- 第一版 Replay 只吃完成的 1 分 K；訊號在 bar close 產生，不能在同一根 bar 內成交。

### 5.2 TradeIntent

策略輸出不是 broker order，至少包含：

- `intent_id`／`idempotency_key`
- `session_id`
- `strategy_id`、`strategy_version`
- `symbol`
- `action`（`ENTER_LONG`／`EXIT_LONG`）
- `signal_at`
- `market_event_id`／輸入 snapshot identity
- `reference_price`
- Candidate matched rules、score breakdown、exit reason

第一版不在 intent 放 Shioaji enum、account、整股／零股或 broker quantity。

### 5.3 OrderCommand、RiskDecision 與 OrderRequest

瀏覽器人工下單與策略自動下單的上游證據不同，但兩者必須在 Broker 前匯流：

- `ManualOrderCommand`：來自網頁，包含 `origin=WEB_MANUAL`、symbol、side、common-lot quantity、limit price、使用者確認時間與 request id。
- `StrategyOrderCommand`：由 `TradeIntent`、position-sizing policy 與 strategy metadata 產生，包含 `origin=STRATEGY_AUTOMATED`。
- 兩者都交給 `OrderApplicationService`；route handler 或 strategy runner 不得直接呼叫 Broker。
- Journal 必須保存 command origin、request/intent id、actor（可匿名化的 local user identity）與完整 risk result。

RiskEngine 取得 OrderCommand、可用的 TradeIntent evidence、DataHealth、PortfolioProjection、pending orders 與 session PnL，輸出：

- `APPROVED`／`REJECTED`
- 明確 reason codes
- 核准的 internal share quantity
- price／notional／position limits

OrderFactory 再產生 broker-ready `OrderRequest`：

- `client_order_id`
- `intent_id`
- `side`
- 明確的 internal quantity unit
- `order_lot`
- `limit_price`（使用 Decimal／tick-normalized value，不使用未正規化 float）
- `price_type`
- `time_in_force`
- `created_at`／`expires_at`

第一版自動 Simulation 僅支援：現股、long-only、common lot、ROD、limit order。Simulation 不支援的興櫃／零股要在 adapter 前明確拒絕。

### 5.4 Broker 與 OrderEvent

Broker protocol 建議只暴露：

- `submit(request) -> SubmissionAck`
- `cancel(order_id) -> CommandAck`
- `replace(order_id, changes) -> CommandAck`（可在後一小節才開）
- `reconcile() -> BrokerSnapshot`
- normalized order-event sink／stream

`SubmissionAck` 只代表 command 已送出或被本地拒絕，不代表 accepted／filled。

Order lifecycle 至少涵蓋：

```text
CREATED
  ↓
PENDING_SUBMIT
  ↓
SUBMITTED / ACCEPTED
  ↓
PARTIALLY_FILLED
  ├──→ FILLED
  └──→ CANCELLED

任何可用狀態亦可能 → REJECTED / EXPIRED / RECONCILIATION_REQUIRED
```

每個 callback、`update_status`、`list_trades` 結果都先轉為 normalized `OrderEvent`。Journal 以 broker event identity／內容 fingerprint 去重，再更新 OrderManager projection。

### 5.5 PortfolioProjection

- Source of truth 是已 journal 的 fills，加上 broker reconciliation 結果，不是 `bought=True`。
- 追蹤 quantity、average cost、realized/unrealized PnL、pending quantity 與 last reconciled time。
- 啟動、重連、定期同步時比較本地 projection 與 Shioaji `list_positions`／trades。
- 不一致時標記 `RECONCILIATION_REQUIRED`，停止新開倉，但仍允許同步與必要的風險處理。
- 產生相容的現有 `Position` view，讓 Exit Rules 與 Dashboard 不需直接理解 broker 模型。

### 5.6 Web Simulation API 與 UI 契約

#### 後端 API

建議使用明確的 simulation namespace：

```text
GET  /api/simulation/session
GET  /api/simulation/orders
POST /api/simulation/orders
POST /api/simulation/orders/{order_id}/cancel
GET  /api/simulation/positions
```

規則：

- 所有 GET 只讀本地 `OrderManager`／`PortfolioProjection`／session projection，不因瀏覽器刷新直接呼叫 Shioaji account/status API。
- `POST /api/simulation/orders` 只建立 command，成功時回 `202 Accepted`、`command_id`／`client_order_id` 與目前狀態；不得回「已成交」。
- request 必須帶 idempotency key；double-click、retry 或 browser reconnect 不得造成第二筆委託。
- route 只能在 backend 回報 `SHIOAJI_SIMULATION + healthy + reconciled + ordering_enabled` 時接受；其他 mode 一律 fail closed。
- 第一版網頁只開 common-lot、cash、long-only、ROD limit order；買進與賣出都需通過相同 RiskEngine。
- cancel 只能作用於可取消狀態；replace 可留在 Phase 5 後段或先用 cancel + new command，不能由瀏覽器直接改 broker object。

#### 網頁資訊架構

1. Header 永久顯示 `Shioaji 模擬盤（非真錢）` badge、連線／DataHealth 與最後 reconciliation 時間。
2. Candidate 詳情區增加「模擬下單」按鈕；只有 session healthy 且 ordering enabled 時可用。
3. Order ticket 預填 symbol 與最新 reference price，輸入買／賣、common-lot 張數、limit price；同時顯示換算股數、估算成交金額、資料時間與 Risk preview。
4. 送出前顯示 final confirmation；確認後立即 disable submit，直到取得 command response。
5. 新增「委託」view／drawer，分開顯示 pending、submitted、partially filled、filled、rejected、cancelled，包含 order/fill quantity、average fill price、reason 與時間。
6. 沿用目前右上角「持倉」drawer，但資料改讀 Simulation `PortfolioProjection`。每檔至少顯示：
   - symbol、name、Simulation 標籤
   - 持有股數／張數、pending buy/sell quantity
   - average fill price、current price、market value
   - unrealized PnL 金額／百分比、realized PnL
   - stop/take-profit、Exit status
   - DataHealth、position source、last reconciled time、reconciliation status
7. 委託 accepted 但尚未 fill 時只出現在「委託」，不可提早出現在「持倉」。持倉只能由 normalized fill 更新。
8. MVP 可每 1 秒 poll 本地 projections，或後續改 SSE；無論哪一種都不能把 browser refresh 變成 provider/account polling。

#### Web 安全邊界

- 預設只 bind `127.0.0.1`；若未來允許非 loopback，必須先加入 authentication、authorization、TLS 與明確部署 review。
- 使用 same-origin／CSRF 防護、JSON POST、idempotency key、input allowlist 與 server-side validation；GET 永遠沒有 side effect。
- 頁面不得持有 API key、secret、CA password 或完整帳號資訊。
- Simulation badge、route namespace 與 backend mode check 三層都不可被前端 query parameter 覆寫。

## 6. 分階段實作計畫

### Phase 0 — Contract and Safety Freeze

目標：先把「可以做什麼」與「絕對不會做什麼」寫成程式可驗證的契約。

工作項目：

1. 定義 typed runtime modes：`BACKTEST`、`REPLAY`、`SHADOW`、`SHIOAJI_SIMULATION`；不建立 production-order／`LIVE` mode。Quote-only 資料來源與 order capability 分開設定。
2. 定義 long-only、cash、common-lot、limit-order v1 scope。
3. 定義 Taiwan session timezone、event-time、received-time、internal share unit 與 money precision。
4. 凍結第一個可測 strategy contract：實際 rules、score maximum、entry threshold、evaluation cadence；不把提案中的 82/84 分與 RVOL/breakout 範例當成已實作能力。
5. 決定第一個 pilot universe 與 immutable historical dataset manifest；第一版不直接擴成全市場 Tick。
6. 釐清 RVOL data semantics；`volume_ratio` 若只是今日累積量／昨日總量，不得標示成過去 N 日同期 RVOL。
7. 把 strategy/cost/slippage/SDK/config 版本寫入每次 session metadata。
8. 保留 `run_scan()` 與既有 Dashboard snapshot/history contract；Phase 0～4 不註冊 simulation order commands，Phase 5 才以獨立 namespace 加入。

預計程式區域：

- 修改：`config/settings.py`、`pyproject.toml`、README／architecture docs
- 新增：`runtime/config.py`、`trading/models.py`

Acceptance：

- 非法 mode 或 production-order capability 啟動即失敗；既有 quote-only snapshot path 不被誤判成下單模式。
- repository 內不存在 `ShioajiLiveBroker`、live factory branch 或 production-order entrypoint。
- default test path 不需 Shioaji credentials／CA／network。
- 現有 64 tests 全數通過。

Review gate G0：使用者確認 scope、pilot universe、資料粒度與 journal storage 選擇後，才進下一階段。

### Phase 1 — Deterministic Market Data and Replay Clock

目標：同一份歷史輸入可重複產生完全相同的 store／decision trigger 順序。

工作項目：

1. 新增 timezone-aware `MarketEvent`、`ReplayClock`、`SystemClock` 與 `DataHealth`。
2. 第一版 canonical replay input 使用完成的 1 分 K，要求唯一且排序穩定的 `(symbol, timestamp)`。
3. Replay loader 啟動前驗證 schema、OHLC、volume、timezone、duplicate、ordering 與 manifest hash；驗證失敗即停止。
4. `MarketDataStore.update()` 回報 accepted／duplicate／out-of-order，不再默默讓舊 event 覆蓋新 projection。
5. Candidate/Scoring evaluation 固定在 completed bar boundary，不因電腦速度改變。
6. 對舊 snapshot path 保留相容 adapter，避免一次改壞 Dashboard。

預計程式區域：

- 修改：`market_data/models.py`、`market_data/store.py`
- 新增：`market_data/events.py`、`market_data/clock.py`、`market_data/replay.py`、`market_data/health.py`
- 新增測試：out-of-order、duplicate、timezone、session boundary、deterministic replay fixtures

Acceptance：

- 同一 dataset 連跑至少 10 次，event／candidate／score digest 完全一致。
- 舊資料、duplicate、naive timestamp、manifest mismatch 都有可測的 fail-closed 結果。
- Replay 不讀 wall clock，不呼叫網路，也不在同一根訊號 K 棒成交。
- 現有 Dashboard 與 Provider tests 仍通過。

Review gate G1：資料與時鐘契約穩定後，才能開始交易 decision／fill 模型。

### Phase 2 — TradingDecision, Risk, Idempotency, Journal

目標：先能產生可稽核、可去重、尚未送券商的交易意圖。

工作項目：

1. `TradingDecisionEngine` 將 Candidate、score、position/exit state 轉成 `TradeIntent`。
2. entry/exit rule、score threshold、cooldown、market-time rule 皆版本化，不使用 UI 的 `MIN_DISPLAY_SCORE` 當交易門檻。
3. 建立 deterministic intent key，避免同一 symbol／session／signal 重複產生 side effect。
4. `RiskEngine` 在所有 mode 共用，至少檢查：
   - DataHealth healthy／fresh
   - session/time window
   - 單筆 notional
   - 每日損失上限
   - 最大持倉／pending order 數
   - 同 symbol 重複 entry
   - 可交易狀態、price limit、spread（欄位可用時）
5. Journal 在 broker 前完成，記錄 session、market input identity、decision、risk result 與 reason code。
6. 定義 `OrderApplicationService` command boundary 與 `CommandOrigin`；先用 fake/no-op broker 驗證任何 producer 都不能繞過 Risk、idempotency 與 Journal。
7. 第一版建議單機 SQLite WAL；若 Phase 4 前決定多進程／遠端服務，先 review 是否改 PostgreSQL，避免雙主資料源。

預計程式區域：

- 新增：`trading/decision.py`、`trading/risk.py`、`trading/journal.py`、`trading/application.py`
- 修改：`app.py` 僅抽出可重用 engine factory；不放長生命週期 runtime
- 新增測試：decision provenance、duplicate suppression、risk reason、journal restart

Acceptance：

- 同一 signal 重送不會產生第二個 intent。
- 每個 allowed/rejected decision 都能從 Journal 回溯到輸入資料、rule version 與 reason。
- DataHealth stale/disconnected 時 entry 必定被拒絕；exit decision 仍可被記錄。
- process restart 後 idempotency 仍成立。
- direct Broker calls 只能存在於 `OrderApplicationService` adapter boundary；route handler 與 strategy runner 的繞過測試必須失敗。

Review gate G2：Journal 與 risk invariants 通過後，才新增 Broker side effect。

### Phase 3 — Shared Backtest/Replay Kernel and ReplayBroker

目標：用同一份 runtime 驗證策略、風控、order state 與績效，不建立兩套語意。

工作項目：

1. 建立最小 Broker protocol、`ReplayBroker`、`OrderManager` 與 `PortfolioProjection`。
2. Backtest 與 paced Replay 使用同一 `TradingSession`；只切換 ReplayClock speed 與輸出頻率。
3. 第一版 fill model：
   - bar close 產生的 order 最早下一根 bar 才 eligible
   - market intent 使用下一個可成交 event 的明確價格規則
   - limit order 必須定義 gap-through 與 OHLC 路徑不明時的保守規則
   - 先支援 all-or-none；若未模擬 partial fill，要在 report 明確標記 model limitation
4. CostModel 將 fee、tax、slippage 分開，按 instrument／side 版本化，不把費率散落在 broker code。
5. 產生 gross/net PnL、trade count、win/loss、profit factor、expectancy、max drawdown、exposure、turnover 與 fill metrics。
6. IS／validation／OOS 分開輸出；原提案的 `trade > 300`、`PF > 1.2` 只當範例，正式 gate 必須在執行前預註冊。

預計程式區域：

- 新增：`broker/base.py`、`broker/replay.py`
- 新增：`trading/order_manager.py`、`trading/portfolio.py`、`runtime/session.py`、`runtime/backtest.py`、`runtime/replay.py`
- 修改：`position/manager.py` 增加由 PortfolioProjection 產生相容 view 的 adapter，不改 Exit Rules 的 broker 隔離原則

Acceptance：

- Backtest 與 1x Replay 對同一 dataset 產生相同 intents、orders、fills、positions 與 net PnL digest。
- 任一 fill 都能追到唯一 OrderRequest、RiskDecision、OrderCommand；strategy order 另需追到 TradeIntent 與 market event，manual web order 則追到 request/confirmation evidence。
- duplicate/out-of-order order event 不會重複加倉。
- fee、tax、slippage 可分項重算，無 same-bar look-ahead。
- strategy gate 未通過時，不能進 Live-data Shadow 的自動 signal tracking。

Review gate G3：先 review 第一份可重現 Backtest/Replay report，再決定是否進即時資料。

### Phase 4 — Live-data Shadow

目標：在真實即時行情上跑完整 decision/risk/journal/virtual execution，但完全不呼叫 Shioaji 下單 API。

工作項目：

1. 抽出 capability-scoped `ShioajiSession` ownership；每個 runtime 只持有一個 SDK client，明確區分 `QUOTE_ONLY` 與 `SIMULATION_ORDER`，避免重複 login 或互相存取 private `_api`。
2. 使用 streaming subscribe 接 Tick／BidAsk；callback 只做輕量 normalize + bounded enqueue，單一 consumer 更新 Store／Journal。
3. Tick 與 BidAsk 各自保持來源順序；不建立假的 cross-stream exchange-time 全序。
4. queue overflow、sequence gap、disconnect、stale 都設為 DataHealth fatal/degraded，阻擋新 entry。
5. 正常 shutdown 必須停止 producer、drain queue、flush Journal，再關閉 session。
6. 訂閱管理採兩層 universe：
   - discovery 只在明確且合規的 cadence 執行
   - candidate、pending order、position 優先訂閱
   - 硬限制不超過官方 200 subscriptions，並保留 safety headroom
7. Shadow 使用 virtual broker/fill model；程式路徑不得 import 或呼叫 `place_order`。

預計程式區域：

- 新增：`market_data/shioaji_session.py`、`market_data/shioaji_stream.py`、`market_data/subscriptions.py`
- 新增：`broker/shadow.py`、`runtime/shadow.py`
- 修改：Dashboard 可只讀 runtime projection；Simulation order controls 在本 phase 仍停用，不透過 refresh 控制 streaming cadence

Acceptance：

- 靜態／runtime 測試可證明 Shadow path 沒有 `place_order`、cancel、replace 或 CA activation。
- callback queue 無 silent drop；overflow 會停止新 entry 並留下明確 incident record。
- 重連後先完成 data/order state synchronization，才恢復新 entry。
- 20～30 個交易日內，所有資料 gap 都被偵測與分類，非預期重複 intent／side effect 為 0，shutdown journal loss 為 0。
- API usage monitor 未觸發官方限制；snapshot/ticks/kbars 沒有被用作盤中輪詢 feed。

Review gate G4：Shadow evidence review 通過後，才能啟用 Simulation order API。

### Phase 5 — Web Manual Shioaji Simulation and Portfolio

目標：從網頁人工送出 Shioaji Simulation 委託，查看委託與已成交持倉；仍不連接策略自動下單。

工作項目：

1. `ShioajiSimulationBroker` 只能接受已驗證的 `simulation=True` session；任何 production mode 立即拒絕啟動。
2. 將 Shioaji contract/order/status/deal objects 轉成內部 models，SDK type 不外洩。
3. 把 `PendingSubmit`、order callback、deal callback、`update_status`／`list_trades` 統一為 idempotent OrderEvent。
4. 啟動、斷線恢復、callback gap 後執行 reconciliation；本地與 broker 不一致時 fail closed。
5. 完成 `OrderApplicationService` 的 web-manual path 與 `SimulationQueryService`，支援 submit、cancel、orders、positions 與 session health；status refresh/reconciliation 由 runtime cadence 控制，不由每個 HTTP GET 觸發。
6. 新增 `/api/simulation/*` FastAPI routes；outside Simulation、unhealthy、unreconciled 或 ordering disabled 時拒絕 mutation。
7. 在現有 Dashboard 增加：Simulation badge、模擬下單 ticket、委託 view，以及由 PortfolioProjection 驅動的持倉 drawer。
8. 驗證 common-lot quantity 轉換、tick normalization、account selection、custom/client correlation、CSRF/idempotency 與 secrets redaction。
9. 在 adapter 前拒絕 Simulation 不支援的 odd lot／emerging stock；第一版 UI 不提供對應選項。
10. 先以 fake broker 與 dry-run preview 驗證 UI/API，再由人工明確啟用 credentialed Simulation smoke。

預計程式區域：

- 新增：`broker/shioaji_simulation.py`、`trading/reconciliation.py`、`trading/queries.py`、`runtime/simulation_manual.py`
- 修改：`dashboard/server.py`、`dashboard/service.py`、`dashboard/static/index.html`
- 新增 web contract、fake broker 與 tagged credentialed integration tests；default CI 不需要 credentials

Acceptance：

- 網頁只能在 `SHIOAJI_SIMULATION`、healthy、reconciled、ordering-enabled 狀態送單；其他 mode 的 mutation request 全部 fail closed。
- 人工從網頁完成 limit buy、PendingSubmit/Submitted 顯示、deal、持倉建立、limit sell/cancel，以及 positions/PnL reconciliation。
- `202 Accepted` 不顯示成成交；未 fill order 只在委託區，第一個 normalized fill 後才更新持倉。
- double-click、HTTP retry、browser reload 使用同一 idempotency key 時只產生一筆 broker command。
- 持倉 drawer 顯示 quantity、average fill、current price、market value、realized/unrealized PnL、pending quantity、exit state 與 reconciliation/data-health 資訊。
- browser polling/streaming 只讀 local projections；重複刷新不得增加 Shioaji status/position query 次數。
- callback 重送、先後順序不同、restart 後 query backfill 都不會重複成交或遺失狀態。
- broker mismatch 時禁止新 order，Journal 保留差異與處理結果。
- log／Journal 不含 API secret、CA password、完整 account/person identity。
- 每筆 manual order 的 audit chain 包含 `origin=WEB_MANUAL`、request id、confirmation、RiskDecision、OrderRequest 與 OrderEvents。
- 未通過人工 gate 前，Strategy 到 SimulationBroker 的 wiring 不存在。

Review gate G5：提供 manual Simulation evidence 與 reconciliation report，review 後才開自動 Simulation。

### Phase 6 — Automated Shioaji Simulation and Evidence Campaign

目標：讓程式產生的 TradeIntent 透過與網頁人工委託相同的 `OrderApplicationService` 接到官方模擬委託，驗證 operation semantics，而不是宣稱已具備實盤可信度。

工作項目：

1. Strategy runner 只能建立 `origin=STRATEGY_AUTOMATED` 的 StrategyOrderCommand，再交給既有 `OrderApplicationService`；不得直接 import/call Broker。
2. 以 feature-disabled default 接上 automated Simulation，逐步從單一 symbol／單一 open order 開始。
3. 強制 one-open-entry-per-symbol、order expiry、rate limiter、daily kill switch、disconnect/stale block。
4. Dashboard 在委託/持倉中標示 `人工`／`自動` origin；可提供單向「暫停自動新委託」kill switch，但不得從網頁直接啟用 auto mode。
5. 記錄並報告：
   - signal → risk → submit latency
   - submit → accepted latency
   - accepted → fill latency
   - reference/order/fill price 差
   - rejection、cancel、replace、reconciliation 次數
6. 將 Simulation observed execution 分布回饋給 Replay fill/slippage model，但要保留 model version，不覆寫舊報告。
7. 跑至少 20～30 個交易日；天數只是 observation horizon，正式通過仍需下列 gate。

Acceptance：

- production/live mode 啟用次數為 0。
- duplicate broker side effect 為 0；unresolved orphan order/fill 為 0。
- 每筆 order/fill 的 audit chain 完整率為 100%。
- queue drop 為 0；所有 disconnect/stale/gap 都有 block 與 recovery evidence。
- local PortfolioProjection 與 broker snapshot 在每次 reconciliation 後一致，否則 session 不恢復 entry。
- web manual 與 strategy automated command 都經過相同 Risk/Journal/OrderFactory/OrderManager；測試可證明不存在第二條 broker path。
- Dashboard 能同時顯示人工與自動委託、合併後的實際 Simulation 持倉，且不把 accepted order 當 position。
- 預註冊策略 gate 在 OOS/forward evidence 上通過；未通過則停在 Simulation，不修改 threshold 追結果。

Review gate G6：交付 Simulation report。此 plan 到此結束，不自動銜接 Small Live 或 Production。

## 7. 測試策略

| 層級 | 必測內容 |
|---|---|
| Unit | time/unit/price normalization、intent key、risk rules、order transitions、cost model |
| Property / state model | duplicate/reordered callbacks、partial fill + cancel、terminal state、quantity conservation |
| Golden Replay | 固定 dataset 多次執行 digest 相同；Backtest 與 paced Replay parity |
| Persistence | transaction rollback、restart、duplicate event insert、schema migration |
| Fake Broker integration | submit/reject/fill/cancel/replace、timeout、disconnect、late callback |
| Web command contract | mode gate、CSRF、idempotency、double-click/retry、validation、202/PendingSubmit semantics、cancel eligibility |
| Web projection/UI | Simulation badge、order status、filled-only holdings、PnL fields、reconciliation/data-health states、narrow layout/accessibility |
| Shared producer path | `WEB_MANUAL` 與 `STRATEGY_AUTOMATED` 都只能經過同一 OrderApplicationService；direct Broker bypass 必須失敗 |
| Shioaji contract fixtures | SDK object mapping、PendingSubmit、order/deal callback、position unit mapping |
| Recovery / chaos | callback gap、queue overflow、process restart、network disconnect、reconciliation mismatch |
| Regression | 現有 Candidate/Scoring/Position/Dashboard/Provider 64 tests 持續通過 |
| Credentialed Simulation | 另設 marker、人工啟動、不得進 default CI |

測試不以「可以 import」或「API 沒丟 exception」當完成；必須驗證狀態、idempotency、帳務守恆與 restart semantics。

## 8. Rollout 與 rollback

- 所有新 runner 與 Simulation mutations 預設關閉；未啟用 Phase 5 runtime 時，現有 `python app.py` 與 Dashboard 保持原行為。
- 每個 phase 都是 additive slice；先 dual-run 比對結果，不直接替換既有 snapshot scan。
- Journal schema 使用 forward migration；事件與報告 append-only，不原地改寫歷史 evidence。
- 任一 gate 失敗時，關閉該 runner 即可回到前一個已驗證模式，不刪資料、不改策略參數追結果。
- Shioaji streaming 與 Simulation 使用明確 entrypoint；Dashboard route 只呼叫 `OrderApplicationService`／`SimulationQueryService`，不持有或直接呼叫 broker。
- 關閉 Simulation runtime 即撤銷 order mutation capability；既有 snapshot/history GET 與 planning evidence 不需 rollback。
- 不建立 production credentials、production mode config 或 LiveBroker，因此此 plan 沒有真錢 rollback 情境。

## 9. 預計檔案變更地圖

```text
config/
  settings.py                   # 保留 rule config；逐步移出 runtime mode

market_data/
  models.py                     # 保留 StockData/KBar 相容性
  store.py                      # monotonic projection + update result
  events.py                     # new: MarketEvent
  clock.py                      # new: ReplayClock/SystemClock
  replay.py                     # new: validated historical event source
  health.py                     # new: CONNECTED/HEALTHY/STALE/...
  shioaji_session.py            # new: single SDK ownership
  shioaji_stream.py             # new: Tick/BidAsk callback adapter
  subscriptions.py              # new: bounded subscription policy

trading/
  models.py                     # new: TradeIntent/OrderCommand/RiskDecision/OrderEvent
  decision.py                   # new: TradingDecisionEngine
  risk.py                       # new: mode-independent RiskEngine
  application.py                # new: one command path for web/manual/strategy
  queries.py                    # new: local session/order/portfolio projections
  order_manager.py              # new: normalized order projection
  portfolio.py                  # new: fill-derived portfolio projection
  reconciliation.py             # new: local/broker comparison
  journal.py                    # new: durable audit persistence

broker/
  base.py                       # new: Broker protocol
  replay.py                     # new: deterministic fill model
  shadow.py                     # new: no-order live-data virtual broker
  shioaji_simulation.py         # new: simulation-only SDK adapter

runtime/
  config.py                     # new: typed fail-closed modes
  session.py                    # new: shared event-driven kernel
  backtest.py                   # new: fast replay runner
  replay.py                     # new: paced replay runner
  shadow.py                     # new: live-data/no-order runner
  simulation_manual.py          # new: manual broker smoke runner
  simulation.py                 # new: gated automated simulation runner

position/
  manager.py                    # compatible view adapter only

dashboard/
  server.py                     # simulation-only command/query routes
  service.py                    # existing scan + simulation query composition
  static/index.html             # Simulation badge, order ticket, orders, holdings

tests/
  unit / replay / broker / recovery / integration fixtures
```

`pyproject.toml` 的 package discovery 必須同步納入新 package，並為 Shioaji Simulation 建立已驗證的 SDK version/constraint；session metadata 要記錄實際版本。

## 10. 實作前需要在 review 階段定案的項目

1. Pilot universe：先用明確、有限的股票清單，不直接承諾全市場即時訂閱。
2. Historical source 與 custody：資料格式、交易日曆、adjustment policy、dataset manifest/hash。
3. Entry policy：真正的交易 threshold、cooldown、同檔重入規則；不能沿用 UI display threshold。
4. Feature semantics：決定第一版使用 absolute volume 還是嚴格同期 RVOL；若選 RVOL，先建立歷史同期分母與 provenance，不能直接沿用 Shioaji `volume_ratio` 名稱。
5. Position sizing：以 internal shares、固定 notional 或 risk-based sizing；broker lot conversion 只留在 adapter。
6. Cost/slippage policy：股票／ETF、buy／sell 的版本化設定與來源證據。
7. Journal storage：預設單機 SQLite；若預計多進程／遠端部署，Phase 2 前改定 PostgreSQL，不能雙主。
8. Shioaji SDK support：以目前環境的 1.7.2 建立 integration evidence，再決定精確 pin／相容範圍。
9. Credentialed Simulation 操作人與時段：CA／account secrets 的取得、保存、人工 gate 與證據留存方式。
10. Web exposure：本 plan 預設 localhost/single-user；若要從其他主機存取，先定 authentication、authorization、TLS 與部署邊界。
11. Manual order UX：預設輸入 common-lot 張數並同步顯示股數／估算金額；若要改成直接輸入股數，需先定清楚 rounding 與 lot conversion。

## 11. 官方限制與實作時再確認事項

截至 2026-08-18，官方文件顯示：

- Simulation 提供 market data、order/update/cancel/status/list trades、positions 與 PnL，但不支援興櫃與零股模擬委託：[Simulation Mode](https://sinotrade.github.io/tutor/simulation/)
- order/deal 透過 callback 回報，且送單後可能先處於 PendingSubmit：[Stock Order](https://sinotrade.github.io/tutor/order/Stock/)／[Order & Deal Event](https://sinotrade.github.io/tutor/order_deal_event/)
- 行情查詢、委託、訂閱與連線均有限制；官方明確要求盤中即時行情使用 subscribe/SSE，不要輪詢 snapshots/ticks/kbars：[使用限制](https://sinotrade.github.io/zh/tutor/limit/)

這些數字與 SDK 行為可能變動，進入 Phase 4／5 前要重新核對官方文件與實際安裝版本，不把本 plan 的日期快照當成永久契約。

## 12. 最終 Definition of Done

Execution Layer v1 完成時，必須同時滿足：

1. 同一份 strategy code 在 Backtest、Replay、Shadow、Shioaji Simulation 不需修改。
2. Backtest 與 paced Replay 對同一 dataset 產生相同 decision/order/fill/PnL digest。
3. 每個 order/fill 都可回溯到 OrderCommand、RiskDecision 與 broker event；自動 order 另可追到 market event、score breakdown、TradeIntent，人工 order 可追到 web request 與 confirmation evidence。
4. stale/disconnect/gap/reconciliation mismatch 會 fail closed，不產生新 entry。
5. restart、callback 重送、順序變動不會重複成交或破壞 position quantity。
6. Dashboard 在非 Simulation mode 維持 read-only；Simulation mode 可人工送單、取消與查看委託/持倉，但所有 mutation 都經過同一安全 pipeline，且 browser refresh 不觸發 provider/account polling。
7. 網頁人工與程式自動委託共用 Risk、idempotency、Journal、OrderFactory、OrderManager、PortfolioProjection 與 ShioajiSimulationBroker，不存在第二條 broker path。
8. 委託與持倉語意分離：accepted/pending order 不算持倉，只有 normalized fill 能改變持有股數與 PnL。
9. 只存在 Replay、Shadow、Shioaji Simulation；沒有 live broker、live mode 或真錢路徑。

這比原提案的「同一 BUY signal 可切 ReplayBroker／ShioajiSimulationBroker」多了三個必要條件：結果必須可重現，每個 side effect 必須可稽核／可恢復／可對帳，而且網頁人工與程式自動委託必須走同一條安全路徑。
