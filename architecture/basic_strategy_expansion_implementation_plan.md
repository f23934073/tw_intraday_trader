# 基本策略擴充 Implementation Plan

## 1. 結論

本計畫在現有歷史回測框架中新增五個固定版本、可追溯且預設不啟用的實驗策略：

1. `opening_range_breakout_entry_v1`：開盤區間突破買入。
2. `ema_crossover_entry_v1`：EMA 黃金交叉買入。
3. `rsi_bollinger_reversion_entry_v0`：RSI／布林通道均值回歸買入假說。
4. `atr_stop_exit_v1`：ATR 波動停損退出。
5. `time_stop_exit_v1`：持倉時間上限退出。

實作不從策略類別直接開始。P0 必須先補齊「資料集 Kbar 週期能力預檢」與「只讀到當下已完成 Kbar 的 bounded rolling feature state」，否則日 K、多標的不規則 Kbar、未完成開盤區間或未完成 indicator warm-up 都可能被錯誤當成有效訊號。

本計畫只涵蓋歷史研究與既有本機紙上模擬邊界，不包含：

- Shioaji 委託、CA、帳戶部位或真實交易。
- 將歷史策略直接接到即時自動下單。
- 從網路複製程式碼或宣稱網路參數可直接獲利。
- 任意 Python／YAML 策略 DSL。
- 瀏覽器任意調參或自動尋優。
- 把 TAIEX futures、DJIA 或其他市場研究結果當成台灣現股通過證據。

## 2. 目前程式的確認狀態

目前 `StrategyRegistry` 有五個可執行回測策略：

- ENTRY：`legacy_gap_volume_vwap_entry_v1`、`momentum_breakout_entry_v1`。
- EXIT：`stop_loss_exit_v1`、`take_profit_exit_v1`、`end_of_day_exit_v1`。

既有框架已具備可沿用的核心能力：

- `HistoricalBar` 保存 timezone-aware OHLCV 與 optional amount。
- 訊號在 Kbar close 形成，成交使用下一根 Kbar open。
- ENTRY／EXIT 可分別使用 `ANY`、`ALL`、`AT_LEAST_N` 聚合。
- 同一 symbol、event、side 的多個策略只產生一個 decision／order。
- 策略定義以 `strategy_id + version + definition_digest` immutable 保存。
- 回測策略只有在資料庫 definition 與 server-side binding／digest 一致時才可選。
- 決策、成交、交易、歸因與 result digest 已可持久化。

本次需要補齊的缺口：

1. Dataset manifest 目前只有泛用 `OHLCV` capability。
2. `KBAR_1M_V1` profile 以「單日總資料筆數」推測，未按 symbol-session 驗證 cadence；多標的日 K 可能被誤判。
3. 建立 run 時尚未把 strategy `required_capabilities` 與 dataset capabilities 做 fail-closed 比對。
4. `StrategyContext` 沒有 opening-range、rolling close、EMA、RSI、Bollinger、ATR 或 position lifecycle feature。
5. 現有 realtime `features/` 依賴 Tick、BidAsk、DataHealth 與 event ID，不適合直接當歷史 Kbar indicator engine。
6. Dashboard 目前會預選第一個 ENTRY、全部 EXIT；若直接註冊新策略，可能無意間改變既有 baseline。
7. `engine_version` 已存在於 run config，但目前沒有真正的 engine-version dispatch；新增 rolling semantics 後要保護舊 run 的重現契約。

## 3. 核心設計決策

### 3.1 策略版本代表邏輯契約，不代表績效通過

五個策略第一版一律使用：

- `status=EXPERIMENTAL`。
- `source=CODE`。
- 固定 parameters。
- immutable execution binding。
- `real_money=false` 的研究邊界寫入說明或 tags。

版本號只表示公式與參數已凍結。即使名稱為 `v1`，也不能顯示為「有效」、「已驗證」或「可上線」。若參數、公式、warm-up、session window 或 trigger 定義有任何改變，建立新版本，不覆寫既有 definition。

### 3.2 不加入 TA-Lib runtime dependency

新增小型、pure、Decimal-based indicator functions，原因如下：

- 本次只需要 EMA、RSI、Bollinger 與 ATR。
- 現有專案不依賴 NumPy／TA-Lib native runtime。
- 手算 fixture、固定 seeding 與明確 warm-up 更容易重現。
- 不同套件對 EMA／RSI／ATR 初值與 unstable period 可能不同，必須以本專案版本化 contract 為 source of truth。

TA-Lib 只作公開指標介面與非必要 qualification 對照，不作 production runtime source of truth。

### 3.3 Historical Kbar features 與 realtime Tick features 分離

新增 `backtest/indicators.py` 與 `backtest/features.py`，不把 Kbar 塞入現有 `features/engine.py`。

- `backtest/indicators.py`：pure indicator calculations 與 bounded state。
- `backtest/features.py`：symbol-session feature lifecycle、opening range、current／previous snapshot。
- `features/`：繼續服務 Tick/BidAsk momentum runtime。

將來若要讓同一策略進 Replay／Shadow，先以相同一分鐘 Kbar fixture 做 parity；未通過 parity 前不宣稱歷史與即時等價。

### 3.4 所有訊號只讀取已完成 Kbar

對 event `t`：

- current feature 可以包含 `t` 這根已完成 Kbar。
- previous feature 僅可包含 `< t` 的 Kbar。
- signal 在 `t` close 形成。
- 最早成交是下一根相同 symbol 的 Kbar open。
- 修改 `> t` 的任何 bar，不得改變 `t` 或更早的 feature、evaluation、decision digest。

ATR exit 的參考值尤其要固定：entry fill bar 的 high／low 尚未知時，不得拿整根 fill bar 計算 `entry_atr`。

### 3.5 不在第一版開放任意參數調校

Dashboard 顯示 strategy parameters，但不增加 sliders、任意 JSON editor 或 grid-search 按鈕。需要測試不同參數時：

1. 建立新的 code-owned strategy version。
2. 使用相同 immutable dataset 與 cost config。
3. 以 baseline／challenger run 比較。
4. 保存 change note 與 definition digest。

## 4. Dataset capability contract（P0）

### 4.1 新 capability

新產生的 dataset manifest 至少可包含：

- `OHLCV`：已有 OHLCV。
- `KBAR_INTRADAY`：同一 symbol-session 有多根盤中 Kbar。
- `KBAR_1M`：主要 cadence 是一分鐘。
- `KBAR_5M`：主要 cadence 是五分鐘；本次新策略不使用。
- `SESSION_BOUNDARIES`：可辨識 Asia/Taipei regular session 與 session date。
- `AMOUNT`：只有 amount coverage 通過時才標示；本批策略不強制。

第一批五個策略全部要求：

```text
OHLCV + KBAR_INTRADAY + KBAR_1M + SESSION_BOUNDARIES
```

這刻意限制成一分鐘 Kbar，避免 `15 bars` 在 1m 與 5m 代表完全不同時間，也避免 EMA／RSI window 跨資料週期後被誤當同一版本。

### 4.2 Capability 推導

不要再用單日所有標的的總 row count 推測 profile。改成：

1. 依 `(symbol, session_date)` 分組。
2. 驗證 timestamp timezone 與 minute alignment。
3. 對各組計算相鄰 bar timestamp delta 分布。
4. 使用 coverage-weighted dominant cadence，並保存 cadence summary。
5. daily、mixed、irregular 或 evidence 不足時，不標示 `KBAR_1M`。
6. 缺少某分鐘可以保留 dataset，但 strategy evaluation 必須對受影響 window 回傳 `INSUFFICIENT_DATA`。
7. 增量 dataset 必須重新以 parent＋delta 的有效資料推導 capability，不能只繼承 parent 字串。

舊 manifest 不做 in-place rewrite。它們沒有 `KBAR_1M` 時，五個新策略在 preflight 直接拒絕，使用者需建立新版 dataset。

### 4.3 Strategy capability preflight

建立 run 前：

1. 解析所有 selected strategy definitions。
2. 合併 `required_capabilities`。
3. 與 dataset manifest capabilities 比對。
4. 缺少 capability 時回傳清楚錯誤，例如：

```text
資料集缺少 opening_range_breakout_entry_v1 所需能力：KBAR_1M、SESSION_BOUNDARIES
```

API、worker preflight 都要驗證；不可只靠 disabled checkbox。worker 必須再次驗證，避免 queued run 在 catalog／dataset 狀態改變後繼續執行。

## 5. Historical feature contract

### 5.1 `BarFeatureSnapshot`

新增 immutable snapshot，至少包含：

- `symbol`
- `session_date`
- `as_of`
- `bar_interval_seconds`
- `bars_seen`
- `opening_range_status`
- `opening_range_high`
- `opening_range_low`
- `ema_fast`
- `ema_slow`
- `rsi`
- `bollinger_middle`
- `bollinger_upper`
- `bollinger_lower`
- `atr`
- `validity`／`missing_reasons`
- `feature_version`
- `input_digest`

每個值要能區分 valid 與 insufficient，不以 `0`、`NaN` 或 infinity 冒充可用數值。

### 5.2 Bounded symbol-session state

每個 symbol 只保存本 session 所需的 bounded state：

- opening range：前 15 根一分鐘 Kbar。
- EMA：previous/current accumulator。
- RSI：14-period Wilder gain/loss state。
- Bollinger：20 closes deque 與 sum/sum-of-squares，或等價 deterministic state。
- ATR：previous close 與 14-period Wilder state。
- previous feature snapshot。

不得為每個 strategy 各自複製整段 history。最大保留窗口固定在 20 bars；feature state 的 memory 應為 `O(symbols × max_window)`。

### 5.3 公式凍結

#### EMA

- `alpha = 2 / (period + 1)`。
- 第一個 EMA 以該 period 的 SMA seed。
- 後續使用 `EMA_t = alpha × close_t + (1-alpha) × EMA_(t-1)`。
- crossover 要求 previous 與 current 的 fast／slow 都 valid。

#### RSI

- period：14。
- gain/loss 取 consecutive close difference。
- 初值用前 14 個 difference 的 simple average。
- 後續使用 Wilder smoothing。
- average loss 為 0 且 average gain 大於 0 時 RSI=100。
- gain/loss 都為 0 時回傳 neutral 50；此行為列入 contract fixture。

#### Bollinger Bands

- period：20。
- middle：20-period SMA。
- standard deviation：population variance（除以 N）。
- upper/lower：middle ± `2 × standard deviation`。

#### ATR

- true range：`max(high-low, abs(high-prev_close), abs(low-prev_close))`。
- period：14。
- 初值為前 14 個 true ranges 的 average。
- 後續使用 Wilder smoothing。
- 第一根沒有 previous close 時，true range 使用 `high-low`，並在 fixture 固定。

所有 rounding 僅在 UI 顯示邊界做；indicator 與 threshold comparison 使用 Decimal 全精度。

## 6. 五個策略的固定 contract

### 6.1 Opening Range Breakout ENTRY v1

Definition：

```text
strategy_id: opening_range_breakout_entry_v1
version: v1
role: ENTRY
session_phase: OPENING
status: EXPERIMENTAL
binding: backtest.opening_range_breakout_entry_v1
parameters:
  opening_range_minutes: 15
  breakout_buffer_pct: 0.001
  entry_window_start: "09:15"
  entry_window_end: "11:00"
  require_complete_opening_range: true
```

規則：

1. 使用 09:00～09:14 共 15 根完整一分鐘 Kbar 的 high／low。
2. 09:15 起凍結 opening range；後續高點不得回寫 range high。
3. 若 15 根中缺任一分鐘，當日 ORB 回傳 `INSUFFICIENT_DATA`，不縮短區間。
4. 在 `[09:15, 11:00)`，current close `>= range_high × 1.001` 時觸發。
5. 11:00 之後回傳 `NOT_TRIGGERED`／outside-window reason。
6. Decision 仍在下一根 Kbar open 才成交。

Observed evidence 至少保存 range high/low、current close、buffer price、opening bar count 與 window。

### 6.2 EMA Crossover ENTRY v1

Definition：

```text
strategy_id: ema_crossover_entry_v1
version: v1
role: ENTRY
session_phase: INTRADAY
status: EXPERIMENTAL
binding: backtest.ema_crossover_entry_v1
parameters:
  fast_period: 5
  slow_period: 20
  reset_each_session: true
  entry_window_end: "12:45"
```

規則：

1. 每個 session 重新建立 EMA state，不跨日攜帶。
2. previous fast `<=` previous slow，且 current fast `>` current slow 才觸發。
3. 只要 fast 高於 slow但沒有發生 crossing，不重複觸發。
4. 任一 current／previous EMA 未完成 warm-up，回傳 `INSUFFICIENT_DATA`。
5. 12:45 之後不建立新 entry，避免接近收盤才以 next-bar 成交。

### 6.3 RSI／Bollinger Mean Reversion ENTRY v0

Definition：

```text
strategy_id: rsi_bollinger_reversion_entry_v0
version: v0
role: ENTRY
session_phase: INTRADAY
status: EXPERIMENTAL
binding: backtest.rsi_bollinger_reversion_entry_v0
parameters:
  rsi_period: 14
  rsi_oversold: 30
  bollinger_period: 20
  bollinger_stddev: 2
  confirmation: REENTER_LOWER_BAND
  reset_each_session: true
  entry_window_end: "12:45"
```

規則：

1. Previous bar 必須同時滿足 `previous_close < previous_lower_band` 與 `previous_rsi <= 30`。
2. Current bar close `>= current_lower_band` 才視為重新進入通道並觸發。
3. RSI 或 Bollinger 任一尚未 warm-up，回傳 `INSUFFICIENT_DATA`。
4. 不使用 current bar 的 low 代替 close confirmation。
5. 12:45 後不建立新 entry。

此策略保留 `v0`，因為它是用來增加與突破策略不同的 mean-reversion hypothesis，不是已確認適合台股盤中的 baseline。

### 6.4 ATR Stop EXIT v1

Definition：

```text
strategy_id: atr_stop_exit_v1
version: v1
role: EXIT
session_phase: POSITION_LIFECYCLE
status: EXPERIMENTAL
binding: backtest.atr_stop_exit_v1
parameters:
  atr_period: 14
  atr_multiplier: 1.5
  atr_reference: ENTRY_SIGNAL_BAR
  execution_model: NEXT_BAR_OPEN
```

規則：

1. Entry decision 建立時，把該 completed signal bar 的 ATR snapshot 帶入 pending entry。
2. Entry 在下一根 Kbar open 成交後，固定 `stop_price = entry_fill_price - 1.5 × entry_signal_atr`。
3. 後續 completed bar 的 low `<= stop_price` 時產生 EXIT decision。
4. 沿用目前回測契約，在下一根 Kbar open 成交；這是 bar-close ATR exit signal，不宣稱是盤中 broker stop order。
5. Entry signal ATR 不可用時回傳 `INSUFFICIENT_DATA`，不得改用 fill bar 未完成資訊。

第一版不做 trailing。ATR trailing 需要定義同一 Kbar 內「先創新高或先打停損」的路徑歧義，應另建版本與 worst-case fill contract。

### 6.5 Time Stop EXIT v1

Definition：

```text
strategy_id: time_stop_exit_v1
version: v1
role: EXIT
session_phase: POSITION_LIFECYCLE
status: EXPERIMENTAL
binding: backtest.time_stop_exit_v1
parameters:
  max_completed_holding_bars: 12
  bar_interval_seconds: 60
  execution_model: NEXT_BAR_OPEN
```

規則：

1. `bars_held_completed` 包含 entry fill bar。
2. Entry fill bar 不做 exit evaluation，沿用既有 engine guard。
3. 當第 12 根持倉 Kbar close 完成時觸發 EXIT decision。
4. 下一根 Kbar open 成交。
5. 若同時觸發停損／停利／EOD，以 strategy-set priority 決定 primary attribution，但只建立一張退出 order。

## 7. Engine v2 與 context 改動

### 7.1 `StrategyContext`

避免繼續平鋪新欄位。新增：

```text
features: BarFeatureSnapshot
previous_features: BarFeatureSnapshot | None
position: PositionStrategyContext | None
```

`PositionStrategyContext` 至少包含：

- entry fill price／time／event index。
- bars held completed。
- entry signal ATR。
- fixed ATR stop price（若可用）。

既有欄位先保留，避免一次重寫五個 legacy strategies；等 v2 golden parity 完成後才考慮整理。

### 7.2 Bar processing order

每根 bar 的固定順序：

1. 使用上一個 event 建立的 pending order，在 current bar open 嘗試成交。
2. 將 current bar 視為完成事件，更新 symbol-session feature state。
3. 建立 current／previous immutable feature snapshots。
4. 若持倉存在且不是 entry fill event，先評估所有 selected EXIT strategies。
5. 無持倉、無 pending、當日尚未進場時，評估 selected ENTRY strategies。
6. Aggregator 最多建立一個 side decision／pending order。
7. 保存 decision evidence 與 deterministic identities。

Entry order 建立時需保存 entry signal feature reference，讓下一根 bar fill 後建立 ATR position context；不可在 fill 時回頭使用 current bar 完整 high／low。

### 7.3 Engine version

新增 server-owned `backtest-engine-v2`：

- v1 completed runs 繼續可讀。
- v1 retry 走 frozen v1 engine；若 v1 engine 無法保留，明確拒絕 retry，不可悄悄用 v2 重跑。
- 新 run 預設 v2。
- v1 與 v2 run 比較時，現有 config comparability 應回傳 `NOT_COMPARABLE`。
- 若要衡量新策略邊際效果，先用 v2 重建 legacy-only baseline，再建立同 dataset／cost／engine 的 challenger。

## 8. Catalog、API 與 Dashboard

### 8.1 Catalog／Registry

修改：

- `backtest/strategies.py`：註冊五個實作，或按可讀性拆成 `backtest/strategy_entries.py`、`backtest/strategy_exits.py`。
- `strategy_catalog/service.py`：將五個 execution bindings 加入 code-owned allowlist。
- 不新增 database-executable Python。
- 不修改任何既有 `strategy_id + version` definition。

新 strategies 只有在 definition digest 與 runtime binding 完全一致時才出現在回測選單。

### 8.2 API

沿用：

- `GET /api/strategies`
- `GET /api/backtests/strategies`
- `POST /api/backtests/runs`

新增行為：

- Strategy list 回傳 status 與 required capabilities。
- Dataset list 回傳精確 cadence capabilities／summary。
- 建立 run 時缺能力回 HTTP 400 與策略名稱、缺少能力清單。
- Worker preflight 重做相同驗證。

不新增 strategy-specific endpoint。

### 8.3 Dashboard default safety

新增策略後不可更改現有預設 baseline：

- ENTRY 預設選第一個 `ACTIVE` legacy strategy，不選 `EXPERIMENTAL`。
- EXIT 預設選既有 `ACTIVE` exits，不自動選新 `EXPERIMENTAL` exits。
- Experimental strategy 顯示「實驗中」badge。
- Dataset 不相容時 strategy checkbox disabled，並顯示缺少 `KBAR_1M`／`SESSION_BOUNDARIES`。
- 若使用者切換 dataset，重新計算 disabled／selected state；不得保留已失效的隱藏選擇。
- Parameters 保持唯讀顯示。

## 9. Persistence 與 migration

### 9.1 SQL

第一版預期不需要新增 SQL table：

- strategy definitions 已能保存 parameters／capabilities／digest。
- dataset manifest 已是 JSON。
- decisions／results／trades 已保存 JSON payload。

若 engine-version dispatch 需要獨立欄位，優先沿用 `config_json.engine_version`，不複製 source of truth。

### 9.2 Manifest migration

- 新 dataset 寫入新版 capability inference identity，例如 `dataset-capabilities-v2`。
- 舊 manifest 不修改 checksum／digest。
- 舊 manifest 不具新能力時，新策略 fail closed。
- 增量 parent／delta 產生新 manifest 與新 digest。

### 9.3 Strategy definition migration

- Bootstrap 只新增五筆 immutable versions。
- 相同 `strategy_id + version` 已存在但 digest 不同時啟動失敗，要求人工確認；不可 overwrite。
- Experimental 通過研究 gate 後，以新 version 建立 ACTIVE definition，不改寫舊 status。

## 10. Implementation phases 與 Gates

### Phase 0 — Baseline 與 contract freeze

工作：

1. 保存目前五個 executable strategy definitions／digests。
2. 保存 legacy-only engine v1 golden result digest。
3. 凍結本文件五個策略的 formula、window、status、binding 與 session semantics。
4. 記錄目前完整測試結果與 Dashboard default selection。

Gate G0：只產生 planning／golden evidence，現有 run 與 UI 無變化。

### Phase 1 — Dataset cadence 與 capability preflight

工作：

1. 修正 per-symbol/session cadence inference。
2. 新 manifest 寫入 `KBAR_INTRADAY`、`KBAR_1M`、`SESSION_BOUNDARIES`。
3. 建立 selected strategies 對 dataset capabilities 的 API／worker preflight。
4. Dashboard 顯示缺少能力原因。

Gate G1：daily、5m、mixed、irregular fixtures 均不會被誤當 1m；舊 manifest 對新策略 fail closed。

### Phase 2 — Pure indicators 與 feature state

工作：

1. 實作 Decimal EMA／RSI／Bollinger／ATR。
2. 實作 bounded `BarFeatureState`／snapshot／digest。
3. 實作 opening range freeze 與 missing-minute detection。
4. 擴充 StrategyContext／PositionStrategyContext。
5. 加入 engine v2 dispatch，但尚不註冊五個新策略。

Gate G2：hand-worked fixtures 全部吻合；future-bar mutation 不影響早期 snapshot；memory 隨 session 長度不成長。

### Phase 3 — ORB 第一個 end-to-end slice

工作：

1. 實作／註冊 ORB definition 與 binding。
2. API／UI 顯示 experimental strategy，但不預選。
3. 建立 missing opening bar、range freeze、11:00 cutoff、next-bar fill fixtures。
4. 用同一 dataset 建立 v2 legacy baseline 與 ORB challenger。

Gate G3：ORB 可從 Web 選取、完成 deterministic run、查看逐筆 evidence；未宣稱研究通過。

### Phase 4 — EMA 與 RSI/Bollinger entries

工作：

1. 實作／註冊 EMA crossover。
2. 實作／註冊 RSI/Bollinger re-entry。
3. 驗證 warm-up、session reset、single crossing、flat price、zero loss、zero variance。
4. 驗證與 ORB 使用 ANY／ALL／AT_LEAST_N 時只形成一個 order。

Gate G4：三個 entry strategies 可獨立與組合執行，全部保存 observed／threshold evidence。

### Phase 5 — ATR 與 Time Stop exits

工作：

1. Pending entry 保存 signal-bar ATR reference。
2. Position context 保存 fixed stop 與 bars held。
3. 實作／註冊 ATR stop 與 time stop。
4. 驗證 exit priority、同 bar 多 exit trigger、EOD fallback 與 unresolved position。

Gate G5：ATR 不讀 fill bar future high/low；time stop 無 off-by-one；多 exit 同時觸發只建立一張 order。

### Phase 6 — Research qualification

工作：

1. 使用同一 immutable、date-effective dataset 建立 v2 baseline／challengers。
2. 分別比較單策略與 strategy combination，不只比較勝率。
3. 至少報告 OOS trades、Wilson CI、expectancy、Profit Factor、drawdown、cost sensitivity、strategy attribution。
4. 使用多個 chronological folds；參數只由 training period 選擇，OOS 不回頭調整。
5. 一般股票 `0.3%` sell tax 與符合資格的當沖 `0.15%` scenario 分開，不混成單一結果。
6. 保存 failed／insufficient evidence，不只保留最好結果。

Gate G6：未通過預先定義 gate 的版本維持 EXPERIMENTAL；通過也只代表研究 gate，不代表真實交易授權。

## 11. Test matrix

### 11.1 Indicator unit tests

- EMA SMA seed、recursive update、insufficient warm-up。
- RSI all-up=100、flat=50、mixed hand calculation。
- Bollinger population variance、zero variance、exact bands。
- ATR first TR、gap TR、Wilder seed/update。
- Decimal repeated-run exact equality。

### 11.2 Data capability tests

- 單一／多標的 daily data。
- 完整 1m data。
- 5m data。
- mixed 1m＋5m data。
- missing minute／停牌／零量 bar。
- timezone／session boundary error。
- legacy manifest without cadence capability。

### 11.3 Strategy tests

- ORB range 只取 09:00～09:14，09:15 後不漂移。
- ORB 缺 opening bar fail closed。
- EMA 只在 crossing event 觸發。
- EMA／RSI／Bollinger 每日 reset。
- Mean reversion 需要 previous setup＋current confirmation。
- ATR 使用 signal bar ATR，不使用 fill bar future range。
- Time stop 第 12 根 close 觸發，下一根 open 成交。
- 12:45 entry cutoff、11:00 ORB cutoff、EOD priority。

### 11.4 Engine invariants

- 同 fixture 連跑十次 output/result digest 相同。
- 修改 future bar 不改變 earlier decisions。
- 多策略同時 trigger 只有一張 order。
- v1 golden result 不因 v2 rollout 改變。
- v1/v2 comparison 顯示 `NOT_COMPARABLE`。
- cancel／retry／clone 保存正確 engine version。

### 11.5 API／UI tests

- 五個 definitions 顯示 status、parameters、required capabilities。
- Dataset 不相容時無法 submit。
- Experimental strategies 預設不勾選。
- Existing legacy defaults 不改變。
- Browser refresh／clone 恢復合法 selections。
- Strategy evidence 與 trade attribution 顯示繁體中文名稱與 version。

### 11.6 Safety tests

- 回測路徑不初始化 Shioaji order API。
- 沒有 CA activation、trade subscription 或 broker call。
- Browser parameters 不能變成 executable code。
- Database strategy metadata 不能繞過 server registry／digest。

## 12. File map

預計新增：

```text
backtest/indicators.py
backtest/features.py
tests/test_backtest_indicators.py
tests/test_backtest_strategy_expansion.py
```

預計修改：

```text
backtest/domain.py
backtest/dataset.py
backtest/engine.py
backtest/application.py
backtest/strategies.py
strategy_catalog/service.py
dashboard/static/index.html
tests/test_backtest_core.py
tests/test_backtest_api.py
tests/test_backtest_dashboard_ui.py
tests/test_strategy_catalog.py
README.md
```

只有確認 `backtest/strategies.py` 過大時，才拆成：

```text
backtest/strategy_entries.py
backtest/strategy_exits.py
```

不預先建立 plugin framework、策略 DSL 或新的 database table。

## 13. Rollout、rollback 與觀測

Rollout：

1. 先部署 capability preflight，尚不註冊新策略。
2. 部署 engine v2／indicator state，以 legacy v2 golden 驗證 parity。
3. 只開放 ORB experimental。
4. 再開放 EMA／RSI-Bollinger。
5. 最後開放 ATR／Time Stop。

Rollback：

- 從 v2 registry 移除尚未使用的新 binding，不刪除既有 definition／run/result。
- Dashboard 隱藏或停用 experimental definitions；completed results 仍可讀。
- 不回寫舊 dataset manifest。
- v1 engine 保留供舊 run 重現／retry；若不能安全執行，拒絕而非轉跑 v2。

最低觀測欄位：

- per-strategy evaluated／triggered／insufficient／blocked。
- capability preflight rejection count 與原因。
- indicator warm-up insufficient count。
- ORB missing-opening-range count。
- exit multi-trigger count 與 primary attribution。
- engine version、strategy digests、dataset capability identity。

## 14. Definition of Done

1. 新 dataset 能可靠區分 daily、1m、5m 與 irregular cadence。
2. API 與 worker 都會拒絕 capability 不足的 run。
3. EMA／RSI／Bollinger／ATR 有明確公式、warm-up、Decimal golden fixtures。
4. 五個新策略均有 immutable catalog definition、server binding 與 observed evidence。
5. 新策略在 Dashboard 可見但預設不勾選，existing baseline 不變。
6. 所有 signal 使用 completed as-of data，成交仍為 next-bar model。
7. ATR reference 沒有 entry fill-bar look-ahead；Time Stop 沒有 off-by-one。
8. 多 ENTRY／EXIT 策略同 event 只建立一張 order。
9. 同 fixture 十次結果 digest 一致，future mutation sentinel 通過。
10. v1 completed runs 不被覆寫；v1/v2 comparability 正確。
11. 完整 regression、static check、Dashboard interaction tests 通過。
12. 全程沒有 Shioaji order、CA、account 或 real-money side effect。
13. 所有新版本在正式研究證據完成前保持 `EXPERIMENTAL`。

## 15. 研究來源與使用限制

- Opening range research：NTU Scholars／IEEE Access，使用一分鐘 index-futures data 並包含 TAIEX。用途是支持 ORB 作為研究候選，不是台灣現股績效保證：<https://scholars.lib.ntu.edu.tw/entities/publication/d69ecf33-892c-4f8a-9a88-2af1bcc4efcd>
- Moving average／trading range research：Santa Fe Institute working-paper record。用途是確認規則屬於長期存在的基本技術規則，不直接移植其市場結果：<https://web-prod.santafe.edu/research/results/working-papers/simple-technical-trading-rules-and-the-stochastic->
- TA-Lib EMA／BBANDS：<https://ta-lib.github.io/ta-lib-python/func_groups/overlap_studies.html>
- TA-Lib RSI：<https://ta-lib.github.io/ta-lib-python/func_groups/momentum_indicators.html>
- TA-Lib ATR：<https://ta-lib.github.io/ta-lib-python/func_groups/volatility_indicators.html>
- TWSE regular session／fees／tax context：<https://wwwc.twse.com.tw/en/about/company/guide.html>

外部來源只用來選擇可研究的規則與校對指標概念。本專案的實際公式、資料範圍、成交模型、成本、版本與證據 gate 以本文件及 immutable run artifacts 為準。
