# 近三年全市場策略回測與 Web 操作 Implementation Plan

## 1. 目標與完成定義

這個計畫要把目前的「歷史行情瀏覽／訊號 Replay」擴充成真正的歷史回測功能，讓使用者可以在既有 Web 平台完成以下流程：

1. 準備並驗證近三年台股歷史資料。
2. 分別複選已凍結版本的買入與賣出策略，並設定 `ANY`、`ALL` 或 `AT_LEAST_N` 組合規則。
3. 從網頁建立、取消、查看與重新開啟回測工作。
4. 用一致的事件時間、成交、成本與資金規則模擬交易。
5. 查看淨勝率、信賴區間、報酬、回撤、Profit Factor、交易明細與資料覆蓋率。
6. 針對每一筆交易回看進出場 K 線、當時策略證據與成本。
7. 以資料集、策略、參數及程式版本的 digest 重現同一份結果。
8. 將 baseline 與每次調整後的 challenger run 永久保存，從網頁比較同條件下的策略變更是否改善。

「完成」不是網頁顯示一個勝率數字，而是：

- 最新完整交易日往前推三個日曆年的 TWSE／TPEX 目標商品都有可稽核的資料覆蓋報告。
- 同一個 dataset＋strategy-set snapshot 執行至少 10 次，交易、損益與結果 digest 完全一致。
- 買入訊號不會在同一根用來決策的 K 棒成交，且沒有任何 future data／look-ahead。
- 勝率以扣除手續費、稅與滑價後的已平倉交易計算。
- Web 可建立工作、顯示進度、取消、失敗後重試、查看結果及匯出交易明細。
- 每一筆買入／賣出都能顯示主要觸發策略及所有同時達標的策略名稱、版本、門檻與證據。
- 完成的 run 不可覆寫；重啟服務後仍可查看、複製與比較歷史回測。
- 回測程式不會啟動即時行情、憑證、券商委託或真實交易路徑。

## 2. 範圍與非目標

### 2.1 本次範圍

- 現股、多頭、整股交易。
- 近三年、以 latest complete trading session 為截止日；另取足夠 warm-up sessions，但不把 warm-up 納入績效。
- 基準 universe：每一歷史交易日當時可交易的 TWSE／TPEX 普通股。
- 第一個可完成的全市場資料粒度：1 分 Kbar＋Amount＋date-effective instrument reference。
- 第二個資料 profile：歷史 Tick L1（成交、最佳買賣價量、tick type）；只有通過資料完整性與容量 Gate 才可執行。
- 既有 Gap／VWAP／BuyScore／StopLoss／TakeProfit 策略的可執行版本。
- 既有 Momentum family 的歷史資料能力檢查與可執行 adapter；缺少必要特徵時 fail closed。
- 買入策略與賣出策略分開複選，第一版支援 `ANY`、`ALL`、`AT_LEAST_N` 聚合方式。
- 完整保存策略定義、策略集合版本、決策事件的逐策略評估、全期評估計數、聚合決策、orders、fills、closed trades 與 run lineage。
- 建立 baseline／challenger 實驗與同條件回測比較頁，量化調整前後差異。
- Signal Study 與 Portfolio Simulation 兩種報告。
- FastAPI＋現有 Vanilla JavaScript 儀表板。

### 2.2 明確非目標

- 不送 Shioaji Simulation 或真實券商委託。
- 不啟用 CA、trade subscription 或 broker order callback。
- 不做放空、融資融券、期貨、選擇權或零股。
- 不在第一版做任意 YAML 策略 DSL 或讓瀏覽器上傳可執行 Python。
- 不把缺少的五檔 BidAsk 由 1 分 K 或 Tick L1 人工補成「真實」資料。
- 不把訓練區間調出的參數，當成未見資料的 OOS 成果。
- 不以單一勝率作為策略可上線的充分條件。

## 3. 已確認的現況與主要缺口

| 項目 | 現況 | 本計畫處理方式 |
|---|---|---|
| 歷史 Kbar | Dashboard 對單一 symbol on-demand 查詢，process memory cache | 建立獨立、可續傳、不可變的全市場 dataset pipeline |
| Replay | manifest／SHA-256／事件排序與 DataHealth 已有 | 保留為 ingestion 核心，擴充 session collection 與 strategy runner |
| Momentum | 可產生 signal/state/alert，但 `REPLAY_ALERT_ONLY` 且 RiskGate unavailable | 增加 strategy adapter、historical capability profile 與 execution intent |
| Candidate／BuyScore | 純規則可重用，但目前只有 one-shot snapshot | 凍結 historical evaluation cadence、entry threshold 與去重規則 |
| Exit | StopLoss 2%、TakeProfit 3%，但只評估手動示範持倉 | 改由 simulated fills 建立持倉並定義 bar/tick exit 順序 |
| Local paper | 可限價撮合與顯示持倉，但使用 float、無成本、只在記憶體 | 保留互動模擬；歷史回測使用新的 Decimal execution/accounting core |
| Journal／Risk／Clock | 已有可重用 contracts | 共用時間、identity、audit 原則，不讓 FastAPI 進入 domain |
| Web | 單頁 Candidate＋模擬 drawer | 新增第一級「歷史回測」功能頁與非同步工作投影 |
| 策略組合 | 現有流程以單一策略／固定規則為主 | 買入、賣出分組複選，使用 deterministic aggregator 產生唯一交易決策 |
| 回測歷史 | 尚無可長期比較的實驗 lineage | PostgreSQL 保存 immutable runs、策略歸因、baseline／challenger 與 comparison records |

## 4. 必須先凍結的產品決策（Gate D0）

正式實作前把以下設定保存成 versioned `StrategySetSnapshot`。Snapshot 內含買入／賣出策略版本、聚合規則、優先序與完整參數；每次修改都產生新版本與 digest，不覆寫舊結果。

### 4.1 建議的第一版預設

| 決策 | 建議預設 | 說明 |
|---|---|---|
| Universe | 每日當時上市／上櫃普通股 | ETF、ETN、權證、特別股與興櫃先排除，避免成本與交易規則混用 |
| 歷史期間 | latest complete session 往前 3 個日曆年 | 執行時依交易日曆解析實際 start/end |
| Warm-up | 額外 60 個完整交易日 | 只供 RVOL／moving baseline，不列入績效 |
| Baseline entry | `legacy_gap_volume_vwap_entry_v1` | 保留目前 GapUp／HighVolume／VWAP／BuyScore 公式 |
| Baseline exits | `stop_loss_exit_v1`、`take_profit_exit_v1`、`end_of_day_exit_v1` | 退出規則拆成可獨立選擇、版本化與歸因的策略 |
| Entry aggregation | `ANY` | 任一買入策略達標就建立一筆聚合買入決策；可改成 `ALL` 或 `AT_LEAST_N` |
| Exit aggregation | `ANY` | 任一賣出策略達標就建立一筆聚合賣出決策；保護性 exit 另有固定優先序 |
| Entry threshold | BuyScore 40／40 | 目前兩個 binary score 都成立才進場；可調但會建立新 strategy version |
| Entry cadence | 每個 completed 1-minute bar 評估；每日每檔最多首次有效 entry 一次 | 防止同一條件在每分鐘重複下單 |
| Fill timing | 最早下一根 bar | 禁止 signal bar 內成交 |
| Position policy | 多頭整股、無槓桿、每檔最多一個 position | 與現有系統邊界一致 |
| Liquidity | 每根 bar 最多使用該 bar 成交量 5%，不足時 partial fill | 比「只要碰價就全部成交」保守；比例可調但會建立新 version |
| Exit | -2% stop、+3% take-profit、收盤前強制平倉 | intraday baseline；overnight 必須是另一個策略版本 |
| 同根 K 同時碰停損／停利 | 採最差結果（先停損） | 1 分 OHLC 無法知道路徑，採保守假設並統計 ambiguity 次數 |
| Starting cash | 10,000,000 TWD | 對齊現有 local paper，可在 run config 修改 |
| Sizing | 固定 equity 比例＋整股向下取整 | 比固定張數更能比較跨價位商品；比例需由使用者確認 |
| Same-day trading | 只允許 date-effective eligibility 通過的股票 | 資料缺少時 fail closed，不假設所有股票可當沖 |
| Win-rate target | 使用者在 Web 輸入 | 不把任意數字寫死；結果同時顯示 break-even win rate |

### 4.2 Baseline strategy set 的精確語意

`legacy_gap_volume_vwap_entry_v1` 與三個 baseline exit strategies 不直接呼叫 `run_scan()`，而是建立新的 historical adapters：

1. 每個交易日用 date-effective reference price 作為 gap 分母，避免除權息造成假 gap。
2. 每根 completed 1-minute bar 更新 open、high、low、close、累積 volume、累積 amount 與 VWAP。
3. Candidate 規則先保留目前的 `GapUpRule OR HighVolumeRule`，確保是在驗證現行策略，不偷偷換公式。
4. Candidate 成立且 BuyScore 達 threshold 時，該 entry strategy 產生 `TRIGGERED` evaluation；其他已選 entry strategies 也在同一 as-of context 獨立評估。
5. `DecisionAggregator` 依 entry aggregation policy 產生至多一筆 `ENTER_LONG` decision 與 intent；intent 只能交給下一根 bar／下一筆 historical Tick 的 fill model。
6. position 建立後，每根 bar 分別評估 stop、take-profit、end-of-day 及其他已選 exit strategies，再聚合成至多一筆 exit decision。
7. 同一 symbol 同一天 entry cooldown、最大進場次數與 re-entry policy 都屬 strategy-set snapshot。
8. 改用 RVOL 的版本另命名為 `gap_rvol_vwap_intraday_v1`，結果不得與 legacy strategy 混合。

### 4.3 Momentum 的資料能力矩陣

| Profile | 能力 | 可否宣稱與目前 live strategy 等價 |
|---|---|---|
| `KBAR_1M_V1` | OHLCV、Amount、衍生 VWAP、bar returns、bar volume acceleration | 否；只能執行明確命名的 bar-compatible strategy version |
| `TICK_L1_V1` | trade、best bid/ask、bid/ask volume、tick type | 部分；可測 L1 Momentum，但不能假裝有歷史五檔 book |
| `TICK_BIDASK_DEPTH_V1` | 完整所需 Tick＋五檔 BidAsk | 只有外部歷史深度資料 source 通過 Gate 才能標示 exact parity |

每個 strategy 宣告 `required_capabilities`。Dataset 不足時，Web 顯示「不可執行」與缺少欄位，不允許自動補值後繼續。

### 4.4 多策略組合與決策規則

每一個可選策略先登錄成 immutable `StrategyDefinition`：

- `strategy_id`：跨版本穩定識別，例如 `legacy_gap_volume_vwap_entry`。
- `display_name_zh_tw`：Web 顯示名稱，例如「跳空＋VWAP 買入策略」。
- `side`：`ENTRY`、`EXIT` 或 `BOTH`；前端依 side 放進不同複選清單。
- `version`、完整 parameters、`required_capabilities`、code/config digest。
- 策略更新只能新增版本，不能修改已被 run 引用的舊版本。

`StrategySetSnapshot` 至少保存：

- `entry_strategy_refs[]`、`entry_aggregation_policy`、`entry_min_trigger_count`。
- `exit_strategy_refs[]`、`exit_aggregation_policy`、`exit_min_trigger_count`。
- `priority_order`、risk／forced-exit priority、canonical JSON 與 SHA-256 digest。

聚合語意：

| Policy | 建立交易決策的條件 |
|---|---|
| `ANY` | 已選策略中至少一個為 `TRIGGERED`；第一版預設 |
| `ALL` | 所有已選且資料能力通過的策略皆為 `TRIGGERED` |
| `AT_LEAST_N` | `TRIGGERED` 數量大於或等於設定的 N |

- 同一 symbol／event／side 有多個策略同時達標時，只建立一筆聚合 decision 與一張 order，不得重複下單。
- primary strategy 依 snapshot 的 deterministic priority 選出，但所有 triggered／not-triggered／blocked evaluations 都保留。
- decision idempotency key 使用 `run_id + symbol + event_identity + side + strategy_set_digest`。
- 風控／強制退出優先於研究型 exit；同一 event 同時出現 entry 與 exit 時，既有持倉的保護性 exit 先處理，exit 未解決前不建立新 entry。

## 5. 整體架構

```text
Web Backtest View
       │
       │ create/query/cancel
       ▼
FastAPI Backtest Controller
       │
       ▼
BacktestApplicationService ───────────────► BacktestRepository (PostgreSQL)
       │                                      │
       │ enqueue                              ├─ experiment/run/config/progress
       ▼                                      └─ decisions/evidence/trades/metrics
Durable Backtest Job Coordinator
       │ dedicated worker process
       ▼
HistoricalBacktestEngine
       ├─ HistoricalDatasetPort ───────────► immutable Parquet partitions
       ├─ StrategyRegistry ────────────────► versioned entry/exit adapters
       ├─ StrategyPort[] ──────────────────► independent evaluations
       ├─ DecisionAggregator ──────────────► one attributed trade decision
       ├─ HistoricalBrokerPort ────────────► bar/tick fill model
       ├─ CostModelPort ───────────────────► effective-dated fee/tax/slippage
       ├─ PortfolioLedger
       ├─ MetricsEngine
       └─ Journal/checkpoint digest

Separate acquisition path:

Web "準備資料" ─► DatasetApplicationService ─► acquisition worker
                                                ├─ Shioaji history adapter
                                                ├─ TWSE/TPEX calendar/universe/reference adapter
                                                ├─ validation/reconciliation
                                                └─ manifest + Parquet store
```

### 5.1 Dependency rule

- `backtest/domain.py`、`backtest/engine.py`、`backtest/metrics.py` 不得 import FastAPI、Shioaji、DuckDB、PostgreSQL、SQLite 或 filesystem implementation。
- `historical_data` 將 provider payload 轉為 canonical rows；strategy 不認識 provider SDK。
- FastAPI route 只做 DTO validation、呼叫 application service、回傳 projection。
- Web 只送 job command 與讀取結果，不執行 strategy、provider 或成本計算。
- 歷史回測 composition 不得建立即時 `SimulationService` 或任何 broker-order adapter。

## 6. Historical data 設計

### 6.1 Dataset profiles

第一版實作 `KBAR_1M_V1`：

- `symbol`, `exchange`, `session_date`
- `bar_start`, `bar_end`, timezone-aware Asia/Taipei
- `open`, `high`, `low`, `close`：Decimal-compatible canonical representation
- `volume`, `amount`, explicit units
- `source`, `source_identity`, `ingested_at`
- `instrument_reference_id`, `calendar_version`

第二版實作 `TICK_L1_V1`：

- trade time、price、volume
- best bid/ask price and volume
- tick type／aggressor mapping status
- deterministic source sequence
- capability 不包含五檔深度

### 6.2 Partition 與 catalog

- 實體資料使用 Parquet，預設路徑由 `BACKTEST_DATA_DIR` 控制，不進 Git。
- 建議 partition：`profile/session_date/exchange/symbol_bucket/*.parquet`。
- 每個 partition 先寫 temp，再 fsync／驗證，最後 atomic rename。
- Dataset catalog 只登錄已封存 partition；失敗或半成品不可讀。
- DuckDB 只作 bounded scan／aggregation adapter，不作 authoritative storage。
- 回測期間禁止向 Shioaji 查資料；所有資料必須先通過 catalog READY Gate。

### 6.3 Manifest

Dataset manifest 至少包含：

- schema/profile version、dataset id、source/version、timezone
- effective start/end、warm-up start
- universe id/version、calendar id/version
- partition 清單、row count、min/max time、SHA-256
- source query parameters、acquired_at、SDK version
- adjustment/reference/corporate-action policy
- capability matrix
- expected／actual symbol-session coverage
- duplicate、out-of-order、invalid OHLC、missing reference、missing amount 統計
- completeness verdict 與明確 reason codes

### 6.4 Universe 與 survivorship bias

`InstrumentUniverseSource` 必須回傳每個 session date 當時存在且符合 product filter 的商品，不可只拿今天仍上市的 contracts 回推三年。

Gate：

- 有 date-effective 上市、下市、暫停交易、商品類型、交易單位、當沖資格與參考價。
- 若 delisted coverage 不完整，dataset 標為 `SURVIVORSHIP_BIASED`。
- `SURVIVORSHIP_BIASED` 可以做 exploratory run，但不能得到 `RESEARCH_PASS`。

### 6.5 Acquisition workflow

1. Web 先建立 dataset sync job，不直接等待 provider 回應。
2. 解析 latest complete session、三年 start、warm-up start 與每日 universe。
3. 產生缺少的 partition 計畫，已驗證 partition 不重抓。
4. acquisition worker 在盤後執行，使用 token bucket、exponential backoff 與 `api.usage()` guard。
5. 空回應先區分休市／停牌／無成交／traffic exceeded／source error，不盲目重試。
6. 每個 partition 做 schema、range、timezone、OHLC、volume、duplicate 與 checksum 驗證。
7. 以官方日成交統計做日線 OHLCV reconciliation；差異超過 policy 就隔離該 partition。
8. 全部必要 partition 完成後才產生 immutable dataset manifest。
9. 後續每日只追加新完整交易日，舊 manifest 永不原地改寫。

官方 Shioaji 顯示股票歷史 Tick／Kbar 可追溯至 2020-03-02，但 full-market 三年資料仍會受到每日流量與查詢限制。Preflight 必須先顯示預估 symbol-days、calls、bytes、磁碟與完成時間；若使用者帳戶流量不足，允許跨日續傳或改用已授權 bulk Parquet source。

## 7. Backtest domain contracts

### 7.1 核心模型

- `BacktestRunConfig`：dataset、strategy-set snapshot、date range、capital、sizing、execution、cost、target metrics、experiment lineage。
- `StrategyDefinition`：stable id、繁體中文名稱、side、version、parameters、required capabilities、code/config identity。
- `StrategySetSnapshot`：entry/exit strategy refs、各自 aggregation policy、minimum trigger count、priority、完整 canonical JSON、SHA-256。
- `StrategyContext`：session、instrument reference、只包含 as-of 可見資料的 feature view。
- `StrategyEvaluation`：run/event/symbol、side、strategy id/name/version、status、observed values、threshold、score、reason、input identity。
- `AggregatedTradeDecision`：entry/exit、policy、trigger counts、primary strategy、全部 triggered／not-triggered／blocked strategy refs、evidence digest。
- `TradeIntent`：decision id、entry/exit、symbol、signal_at、earliest fill、input identity。
- `HistoricalOrder`：shares、side、order type、created_at、earliest_fill_at、expiry。
- `HistoricalFill`：price、shares、time、bar/tick identity、slippage、fees、tax。
- `PositionLot`／`PortfolioLedger`：cash、cost basis、realized PnL、pending orders、equity。
- `ClosedTrade`：entry/exit decision ids、primary entry/exit strategies、全部觸發策略 refs、fills、gross/net PnL、MAE/MFE、holding time、exit reason。
- `BacktestCheckpoint`：partition cursor、portfolio digest、strategy-set digest、result counts。

所有 price、money、fee、tax、PnL 使用 `Decimal`；domain quantity 一律 shares，張數只在 UI／adapter 邊界轉換。

### 7.2 StrategyPort

```text
required_capabilities()
begin_run(run_context)
begin_session(session_context)
on_market_event(as_of_context) -> tuple[StrategyEvaluation, ...]
on_fill(fill, portfolio)
end_session(session_context) -> tuple[StrategyEvaluation, ...]
end_run(run_context)
```

- Strategy 只能讀取 event time 當下或之前的資料。
- 每個已選 strategy 都必須回傳 `TRIGGERED`、`NOT_TRIGGERED`、`INSUFFICIENT_DATA` 或 `BLOCKED`，不能只留下最後贏得 priority 的策略名稱。
- `DecisionAggregator` 依 immutable strategy-set snapshot 將 evaluations 轉成至多一筆 attributed decision，再由 application/domain service 建立 intent。
- Decision 必須保留 Candidate rule、BuyScore／Momentum evidence、entry/exit reason、aggregation result 與全部 strategy versions。
- Strategy 不可建立 broker SDK order。

### 7.3 決策歸因與交易關聯

- `TradeIntent`、`HistoricalOrder`、`HistoricalFill` 都保存 `decision_id`，任何成交都能回查當時聚合規則與策略證據。
- `ClosedTrade` 同時保存 `entry_decision_id` 與 `exit_decision_id`，並投影 `primary_entry_strategy_name`、`primary_exit_strategy_name` 供列表快速顯示。
- 多策略同時達標時，UI 顯示一個主要策略及其餘策略 chips；底層 evidence records 不做逗號字串壓平。
- 一個 strategy evaluation 可被多個研究報告引用，但不可事後改寫 status、threshold 或 observed value。
- 決策、evidence 與 order 建立必須在同一 logical transaction 內完成，避免有 order 卻找不到觸發原因。

### 7.4 兩階段計算

為了同時回答「訊號本身有沒有 edge」與「真實資金配置後會怎樣」，每次 run 產生兩組結果：

1. `SIGNAL_STUDY`：每個合法 entry episode 獨立追蹤到 exit，允許不同股票的研究交易重疊；用來估計淨勝率、payoff 與樣本量。
2. `PORTFOLIO_SIMULATION`：套用 starting cash、最大持倉、position sizing、pending order、liquidity 與 capital contention；用來算 equity curve、return 與 drawdown。

兩者共用 strategy signal、fill/cost policy；差異必須在 UI 清楚標示，禁止混用分母。

## 8. 成交、成本與風控語意

### 8.1 1-minute bar fill model

- Signal 在 bar close 產生，`earliest_fill_at` 是下一根 bar start。
- Marketable entry 預設用下一根 open 加不利方向 slippage。
- Limit BUY 只有後續 bar low 觸及 limit 才可能成交；Limit SELL 只有 high 觸及才可能成交。
- Gap through 以較保守且不違反 limit 的成交價計算。
- 同一 bar 同時觸發 stop/take 時採 worst-case，並增加 `ambiguous_bar_exit_count`。
- volume=0、停牌、漲跌停鎖死、無下一根 bar時不可成交。
- 設 `max_participation_rate`；超過可用成交量時 partial fill 或保守不成交，run execution snapshot 要固定其中一種。
- position 建立後，最早從下一個 event 開始觸發 exit，避免 entry-bar look-ahead。

### 8.2 Tick L1 fill model

- BUY 使用可見 ask，SELL 使用可見 bid。
- quote 必須不晚於 decision 且未 stale。
- 可成交量受 L1 size 與 participation policy 限制。
- 缺 ask/bid 時保持 pending 或 expiry，不可退回 last trade 當作無成本成交。

### 8.3 Effective-dated cost model

- buy commission、sell commission、broker discount、minimum fee。
- sell-side security transaction tax，依 product、日期與是否符合 day-trade 規則選擇。
- slippage model 與 liquidity impact 分開記錄。
- 所有 schedule 都有 version、effective_from/to 與 source note。
- Web 顯示本次實際成本設定；變更設定會建立新 run config digest。

### 8.4 Portfolio restrictions

- long-only、cash account、不可負現金、不可賣超。
- max concurrent positions、per-position notional、daily entry count、per-symbol cooldown。
- instrument 不可交易或資料健康 blocked 時禁止新 entry；已有 position 仍執行能取得資料的保護性 exit。
- end-of-day force close 若沒有可成交資料，標為 unresolved position，該 run 不可宣稱完全 closed。

## 9. 指標、勝率與研究判定

### 9.1 核心指標定義

- `net_win_rate = net_pnl > 0 的 closed trades / 全部 closed trades`；breakeven 不是 win，另列。
- 95% Wilson confidence interval，不只顯示 point estimate。
- gross/net PnL、total return、CAGR、max drawdown、daily volatility。
- Profit Factor、expectancy per trade、average win、average loss、payoff ratio。
- trade count、exposure、turnover、average holding time、MAE、MFE。
- fill rate、partial／expired／rejected orders、ambiguous exits。
- 每年、每季、月份、market、symbol、entry hour、exit reason、score band、entry strategy、exit strategy 的 breakdown。
- 每個策略的 `evaluated → triggered → aggregated → ordered → filled → closed win` funnel，並分開 entry／exit attribution。
- benchmark relative return；benchmark source與 adjustment 必須和 run 一起凍結。

### 9.2 `RESEARCH_PASS` 規則

Win-rate target 由使用者在建立 run 時輸入。系統只在以下全部成立時顯示通過：

1. OOS／walk-forward net win rate 的 95% lower bound 大於或等於 target。
2. OOS closed trade count 大於或等於預先設定的 minimum sample size。
3. OOS net expectancy > 0、Profit Factor > 1。
4. Max drawdown 不超過預先設定 guardrail。
5. Dataset coverage、survivorship、corporate action、cost 與 capability Gates 全部通過。

否則顯示 `INSUFFICIENT_EVIDENCE` 或 `FAILED_TARGET`，而不是把高訓練勝率包裝成有效策略。

### 9.3 時間分割

- Dashboard 同時顯示 full period、年度／季度與 chronological split。
- 預設研究 split：前 18 個月 development、接續 6 個月 validation、最後 12 個月 OOS；實際邊界以完整交易日對齊。
- 任何參數調整後都產生新 strategy version；已看過的 OOS 不再視為真正 unseen。
- 若執行 walk-forward，train/validation/test window 與 promotion rule 必須先寫入 config。

### 9.4 Experiment 與調整前後比較

`BacktestExperiment` 用來把一個 baseline run 與後續 challenger runs 分組。每次從舊 run 複製設定並調整策略時，必須保存：

- `experiment_id`、`baseline_run_id`、`parent_run_id`。
- `change_note`、`changed_fields`、建立者與建立時間。
- baseline/challenger 各自 immutable config、strategy-set、dataset、engine 與 result digests。

只有以下條件完全一致時，UI 才可標示 `COMPARABLE`：

- dataset digest、universe、date range、data profile。
- execution/fill policy、fees、tax、slippage、starting capital、sizing、position limits。
- development/validation/OOS split 與 engine version。

不一致時仍可並排查看，但顯示 `NOT_COMPARABLE` 與差異欄位，不計算「策略調整改善」結論。

### 9.5 Comparison 指標

- OOS net win-rate delta、各自 Wilson confidence interval，以及以 trading session 為 cluster 的 bootstrap delta confidence interval。
- OOS closed-trade count、net return、max drawdown、Profit Factor、expectancy delta。
- 可配對交易以 symbol＋signal time＋side 對齊，顯示共同、只在 baseline、只在 challenger 的交易。
- entry／exit strategy contribution，以及每個 strategy 的 triggered→filled→win funnel 差異。
- strategy-set config diff、策略版本與參數差異。
- 比較 verdict 使用 `LIKELY_IMPROVED`、`NO_CLEAR_EVIDENCE`、`REGRESSED`；只有 comparable、OOS delta confidence interval 達門檻且 drawdown/expectancy guardrails 通過時才可顯示 `LIKELY_IMPROVED`。
- 多個策略共同觸發時，同一筆 PnL 不得在各策略加總成多份；頁面分別呈現 primary-attributed PnL 與 participated-in trades。要判斷新增某策略的邊際影響，必須比較未加入／已加入該策略的兩個 comparable runs。
- 頁面用語採「本次調整關聯差異」，不把 observational backtest comparison 宣稱成因果改善。

## 10. Persistence 與工作生命週期

### 10.1 Storage

- 大型歷史資料：immutable Parquet。
- 平台 authoritative metadata/results：PostgreSQL，透過 `BacktestRepository` port。
- SQLite 只作單機開發與測試 adapter，不作正式歷史比較依據；同一 repository contract 必須有 PostgreSQL contract tests。
- 既有 trading Journal 不保存數億原始 bars；只保存 run-level audit、decisions、orders、fills 與 checkpoints。

建議 tables：

- `historical_datasets`, `historical_partitions`, `data_quality_issues`
- `strategy_definitions`, `strategy_versions`
- `strategy_set_versions`, `strategy_set_members`
- `backtest_experiments`, `backtest_runs`, `backtest_run_lineage`, `backtest_run_configs`, `backtest_progress`
- `strategy_evaluations`, `trade_decisions`, `decision_strategy_evidence`
- `backtest_checkpoints`, `backtest_orders`, `backtest_fills`, `backtest_trades`, `backtest_trade_attributions`
- `backtest_daily_equity`, `backtest_metrics`, `backtest_breakdowns`
- `backtest_comparisons`
- `backtest_artifacts`

所有 run/result rows 都包含 dataset digest、strategy-set digest、engine version 與 created_at。主要關聯與限制：

- completed run、strategy-set version、evaluation、decision、trade 與 metrics 都 immutable；調參只能建立新 version/run。
- `strategy_set_members` 以 `side + strategy_version_id + priority` 表達成員，不以 JSON 字串取代可查詢關聯。
- `decision_strategy_evidence` 保存 evaluation 在該 decision 的角色：`PRIMARY_TRIGGER`、`TRIGGER`、`NOT_TRIGGERED`、`BLOCKED`。
- `backtest_trade_attributions` 以 `ENTRY`／`EXIT` role 關聯 trade、decision 與 strategy version，支援策略貢獻查詢。
- `backtest_runs` 保存 `experiment_id`、`baseline_run_id`、`parent_run_id`、`change_note`、`changed_fields`。
- `backtest_comparisons` 保存比較條件、compatibility verdict、result digest 與建立時間；基礎 runs 不因重算 comparison 被修改。
- unique constraint 至少包含 decision 的 `(run_id, symbol, event_identity, side, strategy_set_digest)`、strategy set member 的 `(strategy_set_version_id, side, strategy_version_id)` 與 idempotent run command key。
- 常用 index 覆蓋 `backtest_runs(experiment_id, created_at)`、`trade_decisions(run_id, symbol, event_at)`、`backtest_trades(run_id, entry_at)`、`backtest_trade_attributions(strategy_version_id, role)`。
- completed run 的外鍵採 restrict/no-cascade delete；canonical JSON 使用 PostgreSQL `jsonb` 保存，同時保存 digest 作 identity。

### 10.2 寫入與一致性邊界

1. 建立 run 時，先在同一 transaction 保存 immutable run config、strategy-set snapshot 與 lineage，再 enqueue job。
2. Engine 對每個 market event 評估所有已選策略，但 PostgreSQL 不逐列保存數十億筆普通 `NOT_TRIGGERED`；它保存聚合計數，並完整保存所有 `TRIGGERED`、`BLOCKED` 及任何形成 decision 的 event 上每個已選策略 evaluation。若啟用 debug retention，完整 evaluation stream 寫 immutable Parquet artifact。
3. 產生交易時，decision、decision evidence 與 order 在同一 logical transaction commit。
4. fill 與 ledger checkpoint 一起保存；closed trade 完成時再原子寫入 entry/exit attribution 與 metrics input。
5. run 只有在 results、digests、quality verdict 都完成後才切到 `COMPLETED`。
6. 使用 database idempotency constraints 防止重複 decision、order、fill 與 run command。
7. 保留 append-only audit timestamps；正式環境不提供刪除 completed run 的 API，只能 archive 顯示狀態。

### 10.3 Job states

```text
QUEUED
  ↓
PREFLIGHT
  ↓
RUNNING
  ├─► CANCELLING ─► CANCELLED
  ├─► FAILED
  └─► COMPLETED

process restart 時 RUNNING ─► INTERRUPTED ─► RESUMING／FAILED
```

- HTTP request 只建立 durable job，不直接執行三年回測。
- 第一版使用單一 dedicated worker process，避免 CPU 工作阻塞 FastAPI event loop。
- 每完成一個 session partition 更新 checkpoint；取消最多等到目前 partition 結束。
- restart 從最後一個完整 checkpoint 繼續，並驗證 portfolio digest。
- 同一 idempotency key 不可建立重複 dataset/run job。
- 第一版可維持單一 worker，但 lease／claim 使用 PostgreSQL row lock 或 advisory lock；日後擴充多 worker 不更換 run repository。

## 11. Web API contract

### 11.1 Dataset

```text
GET  /api/backtests/capabilities
GET  /api/backtests/datasets
POST /api/backtests/datasets/sync
GET  /api/backtests/datasets/jobs/{job_id}
POST /api/backtests/datasets/jobs/{job_id}/cancel
```

Dataset response 顯示 profile、期間、universe、coverage、size、manifest digest、capabilities、issues 與是否可執行指定 strategy。

### 11.2 Runs

```text
GET  /api/backtests/strategies?side=ENTRY|EXIT
GET  /api/backtests/strategy-sets
POST /api/backtests/strategy-sets
GET  /api/backtests/experiments
POST /api/backtests/experiments
POST /api/backtests/runs
GET  /api/backtests/runs
GET  /api/backtests/runs/{run_id}
POST /api/backtests/runs/{run_id}/clone
POST /api/backtests/runs/{run_id}/cancel
POST /api/backtests/runs/{run_id}/retry
```

- Create run request 分別傳 `entry_strategy_version_ids[]`、`entry_aggregation_policy`、`entry_min_trigger_count`、`exit_strategy_version_ids[]`、`exit_aggregation_policy`、`exit_min_trigger_count`。
- API 驗證 entry/exit 至少各有一個策略、`AT_LEAST_N` 範圍合法、dataset capabilities 滿足所有已選策略。
- Clone run 接受 overrides 與必填 `change_note`，保存 `parent_run_id`；舊 run/config 不修改。
- Run list 顯示 experiment、baseline/challenger、strategy-set 摘要與版本，支援依策略、日期、狀態篩選。

### 11.3 Results

```text
GET /api/backtests/runs/{run_id}/summary
GET /api/backtests/runs/{run_id}/equity?scope=portfolio&split=oos
GET /api/backtests/runs/{run_id}/drawdown
GET /api/backtests/runs/{run_id}/breakdowns?dimension=year
GET /api/backtests/runs/{run_id}/trades?page=1&page_size=100
GET /api/backtests/runs/{run_id}/trades/{trade_id}
GET /api/backtests/runs/{run_id}/trades/{trade_id}/chart
GET /api/backtests/runs/{run_id}/strategy-attribution?side=ENTRY|EXIT
GET /api/backtests/runs/{run_id}/export.csv
POST /api/backtests/comparisons
GET /api/backtests/comparisons/{comparison_id}
GET /api/backtests/comparisons/{comparison_id}/trade-diff
```

- 列表全部 pagination；圖表 series 由後端 bounded/downsample。
- create/cancel/retry 需要 idempotency key。
- 錯誤使用穩定 reason code，不把 provider credential 或 filesystem path 回傳瀏覽器。

## 12. Web UI 設計

### 12.1 導航與資訊架構

在現有頁面上方新增第一級功能切換：

```text
選股雷達 | 歷史回測 | 模擬委託 | 持倉
```

「歷史回測」是一個獨立 workspace，不放在 Candidate detail drawer。切回選股雷達時保留目前選中的 candidate；回測工作在背景持續執行。

### 12.2 建立回測

畫面分三區：

1. 資料狀態：三年資料期間、profile、coverage、size、最後同步、錯誤與「準備／補齊資料」。
2. 策略設定：買入策略複選、買入組合方式、賣出策略複選、賣出組合方式、各策略 version/parameters、capital、sizing、cost、slippage、target win rate、minimum trades、max drawdown。
3. Preflight：required capabilities、預估 bars/ticks、磁碟／時間、look-ahead policy、完整 config digest。

只有 dataset READY、strategy capabilities satisfied、必要欄位完整時才啟用「開始回測」。

策略設定互動：

- 「買入策略（可複選）」與「賣出策略（可複選）」是兩個獨立區塊，不把 exit 當成 entry strategy 的隱藏參數。
- 每個策略 chip 顯示繁體中文名稱、version、required data profile；不相容策略 disabled 並說明缺少能力。
- 組合方式提供「任一策略達標（ANY）」、「所有策略達標（ALL）」、「至少 N 個策略達標（AT_LEAST_N）」。
- 即時顯示白話摘要，例如：「任一已選買入策略達標即建立一筆買入決策；任一保護性賣出策略達標即平倉」。
- 儲存的不是前端 labels，而是 immutable strategy version ids 與 strategy-set digest。

### 12.3 執行狀態

- 固定顯示 status、phase、完成 sessions／symbols、百分比、開始時間、預估剩餘時間、目前 partition。
- 每 2 秒輪詢 local job projection；不輪詢 Shioaji。
- 可取消；離開頁面或重開瀏覽器後可從 runs 列表恢復查看。
- 失敗時顯示 reason code、最後 checkpoint 與可否 retry。
- Runs 列表顯示 experiment、baseline／challenger、買入策略摘要、賣出策略摘要與版本；可直接「複製並調整」。

### 12.4 結果頁

由上到下：

1. Verdict：`RESEARCH_PASS / FAILED_TARGET / INSUFFICIENT_EVIDENCE` 與原因。
2. Hero metrics：OOS net win rate＋95% CI、closed trades、net return、max drawdown、Profit Factor、expectancy。
3. Equity curve：portfolio vs benchmark；下方同步 drawdown。
4. Breakdown：年度／季度、月份 heatmap、score band、entry time、exit reason、market、entry strategy、exit strategy。
5. Trade distribution：net PnL、MAE／MFE、holding time。
6. Trade table：symbol、entry/exit、買入策略、賣出策略、gross/net PnL、cost、exit reason；主要策略直接顯示，其餘以 chips／`+N` 展開。
7. Trade detail：歷史 K 線、entry／exit markers、hover OHLCV、所有已選／觸發／blocked 策略、各自門檻與 observed values、聚合方式、fills。
8. Methodology／Data Quality：dataset、strategy、cost、slippage、coverage、excluded sessions、digests。

所有卡片、圖表與 trade table 必須使用同一份 summary/result records；前端不重新計算勝率或 PnL。

交易原因顯示範例：

```text
買入：跳空＋VWAP 買入策略 v1
同時達標：成交量加速買入策略 v2
賣出：停損策略 v1
```

### 12.5 調整前後比較頁

1. 選擇 baseline 與 challenger，預設限制在同一 experiment。
2. 先顯示 comparability verdict 與 config diff；不相容時停用「改善／退步」結論。
3. KPI delta cards：OOS win rate＋CI、trade count、net return、max drawdown、Profit Factor、expectancy。
4. 疊加 equity／drawdown；圖例明確標示 baseline 與 challenger。
5. Trade diff：共同交易、新增交易、消失交易，以及相同訊號但 exit 策略改變的交易。
6. Strategy contribution：每個買入／賣出策略的 evaluated、triggered、filled、wins、net PnL 與 delta。
7. 顯示 `change_note`、changed fields、strategy versions、dataset/config/engine digests，讓使用者知道究竟改了什麼。

## 13. 效能與全市場三年執行策略

全市場 1 分 K 是數億列等級，不能一次載入 RAM。實作採 bounded streaming：

1. DuckDB／Parquet 依 session partition predicate pushdown。
2. 先按 symbol-session 平行產生 feature／intent timeline；輸出固定 schema 與 digest。
3. 再以 `(event_at, symbol, intent_id)` 穩定排序，單一 portfolio ledger 執行資金競爭與 fills。
4. `SIGNAL_STUDY` 可按 symbol-session 平行；`PORTFOLIO_SIMULATION` 的 cash/position mutation 保持單一 deterministic sequence。
5. worker 每次只保留目前 session、持倉需要的後續 bars 與 bounded output buffer。
6. equity 只保存每日 authoritative point；Web chart 另外產生 bounded series。
7. run summary/trades/decision evidence 批次寫 PostgreSQL，不逐 bar 寫資料庫；高容量 debug stream 寫 Parquet artifact。

Rollout benchmark：

- 5 symbols × 20 sessions：correctness fixture。
- 全市場 × 1 session：memory／ordering benchmark。
- 全市場 × 20 sessions：throughput benchmark。
- 全市場 × 1 year：resume／storage soak。
- 全市場 × 3 years：final acceptance run。

Preflight 根據實際 catalog 計算資料列與磁碟，不在 UI 寫死完成分鐘數。

## 14. Implementation phases 與 Gates

### Phase 0 — Contract freeze 與 baseline

工作：

1. 確認 D0 entry/exit strategy sets、aggregation policies、priority、universe、cost、target、position sizing 與 EOD decisions。
2. 保存現有 dashboard／simulation／replay golden fixtures。
3. 建立 `BacktestRunConfig`、`StrategyDefinition`、`StrategySetSnapshot`、`StrategyEvaluation`、`AggregatedTradeDecision`、data capability 與 result metric schemas。
4. 設定 `HISTORICAL_BACKTEST` mode，沒有任何 live/broker value。
5. 記錄完整 current test baseline。

Gate G0：所有語意無未決單位／時間問題，且 feature flag off 時現有行為不變。

### Phase 1 — Historical dataset foundation

工作：

1. 建立 historical ports、manifest、Parquet catalog 與 validation。
2. Shioaji Kbar acquisition adapter 保留 Amount、timezone、source identity；加入 usage-aware throttle。
3. 建立 calendar、date-effective universe/reference/corporate action adapters。
4. 實作 CLI `sync_historical_data.py`，Web 尚不接入。
5. 建立 5 symbols × 20 sessions 的真實／fixture qualification report。

Gate G1：相同 source bytes 產生相同 partition hash；缺資料、錯時區、duplicate、reference mismatch 都 fail closed。

### Phase 2 — Deterministic strategy kernel

工作：

1. 建立 backtest domain、StrategyPort、StrategyRegistry、RunContext 與 session lifecycle。
2. 將 `legacy_gap_volume_vwap_entry_v1`、`stop_loss_exit_v1`、`take_profit_exit_v1`、`end_of_day_exit_v1` 實作成獨立 versioned adapters；RVOL 版本使用另一個 strategy id。
3. 實作 strategy definition／strategy-set canonical JSON＋digest。
4. 實作 deterministic `DecisionAggregator`，支援 entry/exit 各自的 `ANY`、`ALL`、`AT_LEAST_N`、priority 與單一 decision/order 去重。
5. 加入 no-look-ahead sentinel、next-event execution queue 與 end-of-session contract。
6. 以 synthetic fixture 驗證多策略同時觸發、未達聚合門檻、blocked capability、Gap／VWAP／stop／take／EOD。

Gate G2：同 fixture 10 次 evaluations/decisions/intents/fills/trades digest 一致；多策略同時達標只產生一張 order；修改未來 bar 不會改變較早 decision。

### Phase 3 — Historical broker、cost 與 portfolio ledger

工作：

1. 實作 bar/tick fill model、partial fill、limit、price-limit、suspension 與 expiry。
2. 實作 Decimal cash/position ledger、effective-dated fee/tax/slippage。
3. 實作 Signal Study 與 Portfolio Simulation。
4. 讓 intent、order、fill、closed trade 全程攜帶 entry/exit decision attribution，並產出 authoritative daily equity 與 checkpoints。
5. 將 unresolved／ambiguous outcomes列入 quality metrics。

Gate G3：cash＋positions＋costs 守恆；沒有負現金／賣超；手算 ledger fixtures 完全一致。

### Phase 4 — Metrics 與 research evaluation

工作：

1. 實作 win rate、Wilson CI、return、drawdown、Profit Factor、expectancy 與 breakdowns。
2. 加入 development／validation／OOS 與 walk-forward contract。
3. 實作 target verdict 與 insufficient-evidence reasons。
4. 加入 benchmark comparison、entry/exit strategy attribution funnels 與 source provenance。
5. 實作 baseline/challenger comparability contract、paired trade diff 與 KPI delta calculation。

Gate G4：每個 KPI 可由 trade/equity fixtures 重算；summary、chart、table 數值完全 reconcile。

### Phase 5 — Durable jobs 與 API

工作：

1. 實作 PostgreSQL repository、forward-only migrations、lease/claim、idempotency 與 checkpoints；SQLite 僅保留 dev/test adapter。
2. 實作 dataset sync／backtest coordinator 與 dedicated worker process。
3. 實作 strategy definitions/sets、experiments、create/list/clone/status/cancel/retry/result/export APIs。
4. restart 將 RUNNING 轉 INTERRUPTED，驗證 digest 後 resume。
5. 實作 immutable lineage、decision evidence、trade attribution 與 comparison persistence。
6. Backtest APIs 注入 `RuntimeComposition`，不得直接 new SDK/provider。

Gate G5：HTTP 不阻塞長任務；double-click 不重複建 job；服務 restart 後 runs/attributions/comparisons 仍可查；repository contract 與 restart/cancel/retry integration tests 通過。

### Phase 6 — Web backtest workspace

工作：

1. 新增 top-level「歷史回測」導航與 workspace state。
2. 實作 dataset readiness、entry/exit strategy multi-select、aggregation controls、config digest preview 與 preflight。
3. 實作 jobs/runs/experiments 列表、strategy-set 摘要、progress、clone、cancel/retry。
4. 實作 results KPI、equity/drawdown、breakdowns、包含買入／賣出策略的 trade table/detail/K chart。
5. 實作 baseline/challenger comparison、config diff、KPI delta、trade diff 與 strategy contribution。
6. 加入 loading／empty／error／insufficient evidence／not comparable 與窄螢幕狀態。

Gate G6：真實 API fixture 下多選、聚合預覽、策略歸因與比較互動可用；刷新瀏覽器可恢復 run；鍵盤操作、focus、tooltip 與 responsive QA 通過。

### Phase 7 — Scale rollout 與三年 dataset

工作：

1. 依 benchmark 順序由 1 session 擴到 20 sessions、1 year、3 years。
2. 完成 TWSE/TPEX historical universe 與 delisted coverage report。
3. 依官方 limits 在盤後跨日續傳，不碰 traffic ceiling。
4. 執行全市場三年 baseline strategy-set acceptance run。
5. 對完整 run 做 hash、coverage、reconciliation、performance 與 restart evidence report。

Gate G7：三年期間全部必要 partitions READY；沒有 silent skip；run 可完成並可由 checkpoint 恢復。

### Phase 8 — Momentum historical profile

工作：

1. 實作 Shioaji historical Tick L1 acquisition／normalization，保留 capability 限制。
2. 將既有 FeatureEngine／MomentumSignalEngine／MomentumStateMachine 接上 shared backtest kernel。
3. 缺五檔、aggressor mapping 未驗證或 coverage 不完整時 fail closed。
4. 完成 L1-compatible Momentum run；若取得完整 depth source，再新增 exact-parity profile。
5. 比較 Kbar-compatible、Tick L1 與 live-capture overlap sessions 的 signal/fill sensitivity。

Gate G8：UI 不會將 bar/L1 run 標示為 live exact；任何 promoted Momentum 結果都有 capability 與 OOS evidence。

## 15. 預計檔案變更

```text
config/
  backtest.py                         # typed paths, worker, strategy/cost defaults

historical_data/
  models.py                           # dataset/profile/reference contracts
  ports.py                            # source/catalog/universe/calendar ports
  manifest.py                         # canonical manifest + checksum
  parquet_store.py                    # immutable partitions
  duckdb_reader.py                    # bounded analytical reads
  shioaji_history.py                  # Kbar/Tick L1 adapter
  universe.py                         # date-effective universe
  validation.py                       # coverage/reconciliation
  acquisition.py                      # resumable sync use case

backtest/
  domain.py                           # run/evaluation/decision/order/fill/trade objects
  ports.py                            # strategy/dataset/broker/cost/repository ports
  strategy_registry.py                # immutable strategy definitions/versions
  strategy_set.py                     # entry/exit sets and canonical snapshots
  decision_aggregator.py              # ANY/ALL/AT_LEAST_N and priority
  strategies/gap_vwap.py              # current rules historical adapter
  strategies/exits.py                 # stop/take/EOD versioned exit adapters
  strategies/momentum.py              # existing Momentum adapter
  engine.py                           # deterministic session/run kernel
  execution.py                        # bar/tick historical broker
  costs.py                            # effective-dated commission/tax/slippage
  portfolio.py                        # Decimal ledger
  metrics.py                          # KPI/CI/drawdown/strategy attribution
  comparison.py                       # comparability, KPI/trade/config diff
  repository.py                       # repository port/shared mappings
  postgres_repository.py              # platform authoritative adapter
  sqlite_repository.py                # local dev/test adapter only
  migrations/001_backtest_core.sql
  migrations/002_strategy_attribution.sql
  migrations/003_backtest_experiments.sql
  jobs.py                             # coordinator/worker/cancel/resume
  application.py                      # use cases and DTO-independent projections

dashboard/
  backtest_service.py                 # presentation mapping only
  server.py                           # /api/backtests namespace
  static/index.html                   # navigation, setup, jobs, results

runtime/composition.py                # wire backtest services without broker path
scripts/sync_historical_data.py       # same use case as Web
scripts/run_historical_backtest.py    # CLI parity/debug path
pyproject.toml                        # optional backtest dependencies
.gitignore                            # local Parquet/SQLite/debug artifacts
README.md                             # setup, storage, limits, verification
```

新增測試 families：

```text
tests/test_historical_manifest.py
tests/test_historical_acquisition.py
tests/test_historical_coverage.py
tests/test_strategy_snapshot.py
tests/test_strategy_set.py
tests/test_multi_strategy_aggregation.py
tests/test_trade_decision_attribution.py
tests/test_backtest_no_lookahead.py
tests/test_backtest_fill_model.py
tests/test_backtest_costs.py
tests/test_backtest_portfolio.py
tests/test_backtest_metrics.py
tests/test_backtest_determinism.py
tests/test_backtest_jobs.py
tests/test_backtest_postgres_repository.py
tests/test_backtest_experiment_comparison.py
tests/test_backtest_api.py
tests/test_backtest_dashboard.py
tests/test_backtest_restart.py
tests/test_momentum_backtest_capabilities.py
```

## 16. 測試與驗證矩陣

| 層級 | 必測內容 |
|---|---|
| Unit | Decimal rounding、fees/tax effective date、entry/exit timing、ANY/ALL/AT_LEAST_N、priority、ambiguous bar、Wilson CI、drawdown |
| Property/invariant | cash conservation、no oversell、no future reads、one decision/order per event/side、monotonic event/checkpoint、idempotency |
| Golden | fixed dataset/config 對應 evaluations/decisions/intents/fills/trades/attributions/metrics/digest |
| Adapter | Shioaji mapping、timezone、Amount/volume unit、empty/error/traffic responses |
| Data quality | missing session、delisted symbol、corporate action、duplicate、out-of-order、bad OHLC |
| Integration | Parquet→engine→PostgreSQL→API→frontend DTO reconcile；SQLite adapter contract parity |
| Recovery | kill worker、restart、resume、cancel、retry、corrupt checkpoint |
| Performance | bounded memory、full-session ordering、20-session throughput、1-year soak |
| Browser | entry/exit multi-select、aggregation preview、create/clone run、progress、reload recovery、trade strategy labels、baseline comparison、responsive/accessibility |
| Safety | zero Shioaji order calls、zero CA、zero trade subscription、browser never receives credentials |

CI 使用小型 immutable fixtures，不下載三年資料、不登入 Shioaji。真實 provider qualification 與 full three-year run 是明確的 manual evidence Gate。

## 17. Migration、rollback 與 feature flags

- 新增 `BACKTEST_ENABLED=false` 預設 flag；未啟用時不建立 worker，現有 dashboard 完全不變。
- Dataset sync 與 run 分開 flags；可只瀏覽既有結果而不允許建立新工作。
- PostgreSQL migrations forward-only；migration 前備份 metadata schema，completed run rows 不做 in-place semantic rewrite。
- SQLite schema 只支援 local dev/test，不能當正式平台歷史比較資料庫。
- 新 schema version 產生新 dataset，不重寫舊 partition。
- UI/API 可整段關閉 backtest namespace；Candidate、歷史 K 圖與 local paper routes 不受影響。
- 若 worker 不穩定，rollback 到 CLI-only 同一 application use case；PostgreSQL 已完成 runs/results/lineage 不丟失。

## 18. Definition of Done

1. Web 可準備資料、建立／取消／重試回測、查看 durable progress 與結果。
2. Web 可分別複選買入／賣出策略並設定 `ANY`、`ALL`、`AT_LEAST_N`；相同 event/side 無論幾個策略達標都只有一筆 decision/order。
3. latest complete session 往前三年的 target universe 有 immutable manifest、coverage 與 quality report。
4. baseline strategy set 在全市場三年資料完成 Signal Study 與 Portfolio Simulation。
5. 每一筆 closed trade 都能追溯到 dataset rows、entry/exit decisions、主要與全部觸發策略名稱/版本、fills、costs 與 exit reason。
6. 勝率為 net closed-trade win rate，顯示 95% CI、樣本量與 OOS 結果。
7. Profit Factor、expectancy、return、drawdown、strategy contribution 與 table/chart 全部 reconcile。
8. completed runs、strategy-set versions 與 comparisons 保存於 PostgreSQL，服務重啟後可查且不可覆寫。
9. Web 可從 baseline clone challenger，保存 change note，通過 comparability guard 後比較 KPI、trade diff 與 entry/exit strategy contribution。
10. no-look-ahead、determinism、accounting invariants、restart/cancel 與 safety tests全部通過。
11. Momentum 只能在符合 required capabilities 的 dataset 上執行，UI 不誇大資料等價性。
12. 完整 run 的 dataset/config/code/result digests 可再次重現。
13. 全程沒有 broker order／CA／live-money side effect。

## 19. 實作前需要使用者最後確認的參數

架構與工作順序不需要再改，但開始 Phase 0 前應確認：

1. 第一個正式回測是否採 `BuyScore == 40` 才買入。
2. 是否採當日收盤前強制平倉，或允許隔夜持有。
3. 每檔 position sizing 比例與最大同時持倉數。
4. 實際券商手續費折扣／最低手續費。
5. 目標勝率、minimum OOS trades 與最大回撤 guardrail。
6. 是否接受第一版 entry／exit 都以 `ANY` 為預設，進階情境再選 `ALL` 或 `AT_LEAST_N`。
7. PostgreSQL 的部署位置與備份／保留年限；架構預設 completed runs 永久保留、只能 archive。

若尚未提供，系統可以先用「研究預設」建立 fixture 與 UI，但不得把預設 run 標示為使用者策略的正式通過證據。
