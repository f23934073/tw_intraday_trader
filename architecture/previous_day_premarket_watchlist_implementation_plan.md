# 前一交易日盤前觀察池 Implementation Plan

## 1. 目標與交付結果

在不接收盤前試撮行情、也不呼叫券商即時行情的前提下，使用「前一個已完成交易日以前」的不可變歷史資料，產生下一交易日的盤前觀察池。

第一版納入三個候選策略：

1. `previous_day_momentum_watchlist_v1`
2. `nr7_compression_watchlist_v1`
3. `previous_day_oversold_watchlist_v1`

系統完成後應具備以下能力：

- 每個目標交易日都能重現當時的觀察池結果。
- 觀察池產生過程不讀取目標交易日的開盤價、盤前試撮價或任何未來資料。
- 結果以不可變 artifact 保存，包含資料、策略、日曆、股票池與設定的版本證據。
- 觀察池可投影到 `CandidatePool`，但只代表「納入觀察」，不代表買進訊號。
- Dashboard 有獨立的「盤前觀察池（前日資料）」面板，不混入既有即時候選分數排序。
- 同一套純運算核心可用於歷史 walk-forward／out-of-sample 驗證。

## 2. 明確邊界

### 2.1 本次範圍

- 前一交易日 OHLCV 衍生資料與技術指標。
- Corporate-action 調整、日期有效的開盤參考價、漲跌停價與 one-price bar 分類。
- 台股交易日曆與目標交易日解析。
- 日期有效的股票資格篩選介面。
- 三個策略的確切公式、排序與版本化參數。
- 不可變觀察池 artifact 與持久化。
- `CandidatePool` 的 observation-only adapter。
- 只讀 API、Dashboard 面板與策略目錄顯示。
- 排程、手動 CLI、可重入與失敗關閉行為。
- 歷史回放、look-ahead 防護與測試。

### 2.2 不在本次範圍

- 盤前試撮價、委買委賣或即時 Tick/BidAsk。
- 新聞、ADR、TAIFEX 夜盤等跨市場訊號。
- 自動下單、券商登入、交易額度或部位管理。
- 修改既有 `BuyScore`、進場規則或出場規則。
- 把觀察池命中直接當作買進訊號。
- 將新策略直接標記為可正式交易；初始狀態一律為 `EXPERIMENTAL`。
- 修改既有 `premarket_gap_watchlist_v1`；它仍維持 `DRAFT`，且仍需要盤前試撮資料。

## 3. 核心時間契約

令：

- `T`：觀察池要服務的目標交易日。
- `P`：由版本化 TWSE／TPEX 交易日曆解析出的 `previous_trading_day(T)`。
- `generated_at`：artifact 實際建立時間，時區固定為 `Asia/Taipei`。

所有策略只能讀取 `session_date <= P` 的資料，並遵守以下規則：

1. 純策略引擎不得自行呼叫 `datetime.now()`；`T`、`P`、clock 與資料版本都由 application layer 傳入。
2. 每檔股票最新一筆完整日 K 必須等於 `P`，否則排除並記錄 `STALE_SYMBOL_HISTORY`。
3. 資料集本身必須宣告完整覆蓋至 `P`；不完整時整個工作 fail closed，不可退回舊資料默默產生名單。
4. 遇到假日、補班但不交易、臨時休市或天然災害停市，只依版本化交易日曆判定，不以週一至週五推算。
5. artifact 建立後若 `T` 臨時休市，標記為 cancelled／expired，不可自動挪用到下一交易日。

## 4. 架構決策

### 4.1 新增獨立 `watchlist` bounded context

新增 `watchlist/` 套件，避免與目前可能同時開發的市場層 `premarket/` 模組混用：

```text
watchlist/
  domain.py
  calendar.py
  reference_data.py
  adjustments.py
  daily_bars.py
  features.py
  strategies.py
  artifacts.py
  application.py
  repository.py
  candidate_source.py
  costs.py
```

責任切分：

- `domain.py`：target/as-of、日 K、策略結果、artifact manifest、entry、排除原因。
- `calendar.py`：交易日曆介面、版本與 coverage 驗證。
- `reference_data.py`：日期有效 universe、corporate action、開盤參考價與價格限制資料介面。
- `adjustments.py`：raw／adjusted OHLC 轉換、factor coverage 與混用防護。
- `daily_bars.py`：不可變分鐘 K 資料轉日 K 與 digest。
- `features.py`：共用技術指標與流動性特徵。
- `strategies.py`：三個純策略與確定性排序。
- `artifacts.py`：manifest／entry 序列化與 content digest。
- `application.py`：資料驗證、工作協調、artifact 發布。
- `repository.py`：PostgreSQL／SQLite persistence port 與實作。
- `candidate_source.py`：artifact 到 `CandidateDiscovery` 的 read-only adapter。
- `costs.py`：Formal Validation 使用的日期有效成本契約；不參與盤前候選生成。

歷史資料與 durable job 的生命週期仍由既有 `BacktestApplicationService` 協調；`watchlist` 不直接讀 Provider，也不在 Dashboard request path 即時計算全市場資料。

### 4.2 抽出共用指標，而非複製公式

目前 backtest 已有 RSI、布林通道等純運算能力。實作時將可共用的技術指標抽到中立模組，例如：

```text
features/technical_indicators.py
```

`backtest/indicators.py` 保留相容 re-export，`watchlist/features.py` 使用同一份實作。需以 parity tests 證明抽取前後結果一致，避免回測與每日觀察池產生兩套公式。

所有價格、比率與門檻使用 `Decimal`；只有序列化邊界才轉成明確字串，不以 binary float 參與排名或 digest。

### 4.3 CandidatePool 僅接收觀察池投影

新增：

```python
CandidateSource.PREVIOUS_SESSION_WATCHLIST
```

並建立 `PreviousSessionWatchlistCandidateSource`：

- `discovered_at = artifact.generated_at`
- `expires_at = T 13:30:00 Asia/Taipei`
- `rank_types = matched_strategy_ids`
- `best_rank = overall_rank`
- evidence 只帶 artifact ID、artifact digest、target/as-of 與策略 ID
- 完整證據仍以不可變 artifact 為 source of truth

CandidatePool 的 admission 只擴充訂閱／觀察範圍，不修改 BuyScore、模擬交易或下單條件。若既有 active episode 需要延續，沿用 CandidatePool 現有生命週期規則，不由觀察池 artifact 強制結束。

## 5. 資料契約

### 5.1 版本化交易日曆

新增設定與資料：

```text
config/watchlist.py
config/twse_calendar_YYYY.json
```

日曆資料至少包含：

- `calendar_id`
- `version`
- `timezone`
- `coverage_start`
- `coverage_end`
- 正常交易日、休市日、臨時異動
- canonical JSON SHA-256 digest

規則：

- `T` 或 `P` 超出 coverage 時回傳 `CALENDAR_OUT_OF_COVERAGE` 並停止產生 artifact。
- 日曆更新需建立新版本，不覆寫已被 artifact 引用的舊版本。
- 測試 fixture 必須涵蓋週末、連假、補班日與臨時休市。

### 5.2 股票資格 universe

不得用「四位數代碼」推斷普通股。定義 `EquityUniversePort`，至少回傳：

- symbol、名稱、market
- security type
- listing start／end
- suspension／delisting 狀態
- `effective_from`／`effective_to`
- universe version 與 digest

兩種證據層級：

- `DATE_EFFECTIVE`：能還原 `T` 當時可交易股票，才可用於正式歷史 out-of-sample 研究。
- `CURRENT_SNAPSHOT`：只可產生當日前瞻觀察池，artifact 必須標記 `research_eligible=false` 與 `SURVIVORSHIP_LIMITED`。

### 5.3 日 K 衍生層

不可在每次 Dashboard request 時讀完整 JSONL 並重新聚合。針對每個不可變歷史資料集建立一次日 K derivation：

- base dataset：聚合所有分鐘 K。
- incremental dataset：只聚合本次 delta，查詢時沿 parent dataset chain 解析有效日 K。
- 以 `(dataset_id, symbol, session_date)` 唯一識別日 K。
- 每列保存 `source_bar_count` 與 row digest，derivation 保存整體 content digest。

日 K 欄位：

- raw open、high、low、close、volume
- adjusted open、high、low、close
- `price_adjustment_factor`、可用時的 `volume_adjustment_factor`
- corporate-action type／source／version／digest
- reference price、limit-up price、limit-down price
- touched／closed-at-limit 與 one-price flags
- `traded_value_proxy = sum(minute_close × minute_volume)`
- first／last bar time
- source row count
- source digest

`traded_value_proxy` 必須明確命名為代理值，不得宣稱為交易所公布的真實成交金額。

新增或補充資料能力宣告：

- `DAILY_OHLCV`
- `ADJUSTED_DAILY_OHLC`
- `CORPORATE_ACTIONS`
- `REFERENCE_PRICE_LIMITS`
- `TRADING_CALENDAR`
- `EQUITY_UNIVERSE`

舊資料集沒有完成日 K derivation 時，application layer 應建立／等待 derivation job；不得在讀取 API 裡臨時計算。

### 5.4 Corporate action 與價格限制契約

每個日 K 必須同時保留市場原始證據與研究用調整序列：

```text
adjusted_open  = raw_open  × price_adjustment_factor
adjusted_high  = raw_high  × price_adjustment_factor
adjusted_low   = raw_low   × price_adjustment_factor
adjusted_close = raw_close × price_adjustment_factor
comparable_volume = raw_volume × volume_adjustment_factor
```

規則：

1. 每次產生 target `T` 的 artifact，都建立 `adjustment_as_of = P` 的 view；factor chain 只包含 `effective_date <= P` 的 actions，並以 `P` 的價格尺度為 anchor。`P` 之後才發生或才公告的 action 不得改寫這次輸入。
2. 同一個 indicator window 只能使用同一 adjustment snapshot/version 的 adjusted OHLC，不可只調 close 或混用 raw high／adjusted close。
3. Corporate-action action type 至少區分 cash dividend、stock dividend、split、capital reduction、rights／subscription、other。
4. `adjustment_as_of`、`price_adjustment_factor`、action source、effective date、available-at timestamp、version 與 digest 都必須進入 adjusted-view digest。
5. 現金股利不應改寫真實成交量；遇到 split、股票股利或減資等改變股數基礎的事件，只有具備可信 `volume_adjustment_factor` 時才可跨事件比較量能。缺少時將相關 lookback 排除為 `UNADJUSTED_VOLUME_CORPORATE_ACTION_WINDOW`。
   - 沒有股數基礎變更的 window，`volume_adjustment_factor = 1`。
   - 有股數基礎變更時，只接受 source-defined、方向與 anchor 已版本化的 factor；不得由價格 factor 猜測。
6. 流動性代理值仍使用當時實際 raw price × raw volume，不用 adjusted price 偽造真實成交金額。
7. 正式研究遇到 factor coverage 缺口、來源衝突或無法辨識 action 時 fail closed；不得以 raw close series 繼續計算 RSI、Bollinger 或 Momentum。

價格限制必須使用日期有效、已按交易所價格級距處理的 reference／limit prices，不可直接以 `reference_price × 1.1` 或固定百分比自行推算。以下 flags 以 raw price 判斷：

```text
touched_limit_up   = raw_high == limit_up_price
touched_limit_down = raw_low == limit_down_price
is_limit_up        = raw_close == limit_up_price
is_limit_down      = raw_close == limit_down_price
is_one_price_bar   = raw_open == raw_high == raw_low == raw_close
is_limit_locked_one_price =
  is_one_price_bar AND (is_limit_up OR is_limit_down)
```

- NR7 hard-exclude `is_one_price_bar`，避免零振幅被誤判成最佳壓縮。
- 只觸及或收在漲跌停、但仍有真實日內 range 的標的保留為具名 cohort，不自動排除。
- Momentum 的 limit-up observations 必須帶 flag 並與一般動能分開排名／評估。
- `high == low` 時 `close_location` 為 `None`，不可用零或一代替。

### 5.5 共用最低資格

所有策略先套用共用條件：

- symbol 在 `T` 的 eligible equity universe 內。
- 最新完整 session 等於 `P`。
- 至少 21 個有效完成交易日。
- session 唯一、時間順序正確，且都落在交易日曆內。
- `volume_P > 0`。
- 最近 20 日平均 `traded_value_proxy >= 20,000,000 TWD`。
- Momentum／RSI／Bollinger 所需期間具有完整且同版本的 adjusted-price coverage。
- 任何跨 corporate-action 的量能視窗具有可信 volume adjustment，否則以具名原因排除。

`20,000,000` 是第一版 `EXPERIMENTAL` 預設值，必須屬於策略／觀察池版本化參數並進入 config digest，不可只存在全域 mutable config。

個別股票不合格時排除並累計具名原因；若資料集整體不完整、日曆失效或 digest 不一致，則整份工作 fail closed。

## 6. 三個策略的精確規格

以下索引皆以 `P` 為最後一個完成交易日，排序最後固定以 symbol 升冪打破同分，確保 replay digest 穩定。

### 6.1 `previous_day_momentum_watchlist_v1`

特徵：

```text
sma20_close       = mean(adjusted_close[P-19 : P])
rolling_high20    = max(adjusted_high[P-19 : P])
volume_baseline20 = mean(comparable_volume[P-20 : P-1])
volume_ratio      = comparable_volume[P] / volume_baseline20
breakout_proximity = adjusted_close[P] / rolling_high20
adjusted_daily_return = adjusted_close[P] / adjusted_close[P-1] - 1
reference_daily_return = raw_close[P] / reference_price[P] - 1
close_location =
  (raw_close[P] - raw_low[P]) / (raw_high[P] - raw_low[P])
```

命中條件：

```text
adjusted_close[P] > sma20_close
adjusted_close[P] >= rolling_high20 × 0.98
volume_ratio >= 1.5
```

這三項只定義 baseline candidate，不代表已通過獲利驗證。Phase 3 同時輸出下列 versioned research variant membership：

| Variant | 額外條件 | 用途 |
|---------|----------|------|
| `baseline` | 無 | 保留原始候選母體 |
| `positive_return` | `adjusted_daily_return > 0` | 排除收跌爆量樣本 |
| `strong_close_060` | `close_location >= 0.6` | 研究帶量收強、減少長上影樣本 |
| `positive_return_strong_close_060` | 同時符合上述兩項 | 較嚴格 challenger |

`0.6` 是 `EXPERIMENTAL` 研究參數，不是正式 production threshold。任何門檻變更都建立新的 variant config digest；不得用全期間結果回頭挑選門檻。

排序：

1. `breakout_proximity` 降冪
2. `volume_ratio` 降冪
3. `close_location` 降冪；baseline 中為 `None` 者排在有值者之後
4. 20 日平均 `traded_value_proxy` 降冪
5. symbol 升冪

注意：量能基準排除 `P`，所以此策略最低需要 21 個 sessions。排行先依 `NORMAL`、`LIMIT_UP_CLOSE`、其他價格限制 cohort 分區，再在區內使用上述順序；不可把漲停樣本與一般動能混成單一績效母體。

### 6.2 `nr7_compression_watchlist_v1`

特徵：

```text
range_pct[d] =
  (adjusted_high[d] - adjusted_low[d]) / adjusted_close[d-1]
```

命中條件：

```text
range_pct[P] <= min(range_pct[P-6 : P])
AND is_one_price_bar[P] == false
```

排序：

1. `range_pct[P]` 升冪
2. 20 日平均 `traded_value_proxy` 降冪
3. symbol 升冪

這是 normalized range-percentage NR7 variant，不宣稱等同傳統 raw `high-low` NR7。它只表示波動壓縮，方向為 neutral；`NR7 -> watchlist -> next-session NR7-high／ORB／VWAP confirmation -> LONG bias`，沒有盤中確認時不得交給進場決策。觸及價格限制但保有真實 range 的樣本需以 cohort 分開評估。

### 6.3 `previous_day_oversold_watchlist_v1`

特徵：

- `RSI(14)`：Wilder smoothing，以完成交易日 adjusted close 計算。
- `Bollinger(20, 2)`：20 日 adjusted close、population standard deviation、上下軌倍數 2。
- `lower_band_distance = (lower_band - adjusted_close[P]) / lower_band`。

命中條件：

```text
rsi14[P] <= 30
adjusted_close[P] < bollinger_lower20_2[P]
```

排序：

1. `rsi14[P]` 升冪
2. `lower_band_distance` 降冪
3. 20 日平均 `traded_value_proxy` 降冪
4. symbol 升冪

RSI 在無漲無跌的平坦序列採現有共用指標契約回傳 50，並以 fixture 鎖定。

此策略只輸出 mean-reversion candidate，`OVERSOLD != BUY`。至少等待目標交易日的 VWAP reclaim、first-5m high breakout、昨日 low reclaim 或版本化量價反轉確認，才可交給 BuyScore。Oversold 保持 `EXPERIMENTAL`，不阻塞 Momentum 第一版。

## 7. 策略目錄整合

在 strategy catalog 新增三個 immutable definitions：

```text
candidate.previous_day_momentum_watchlist_v1
candidate.nr7_compression_watchlist_v1
candidate.previous_day_oversold_watchlist_v1
```

共同屬性：

- category：`CANDIDATE`
- session：`PRE_MARKET`
- lifecycle：`EXPERIMENTAL`
- required capabilities：`DAILY_OHLCV`、`ADJUSTED_DAILY_OHLC`、`CORPORATE_ACTIONS`、`REFERENCE_PRICE_LIMITS`、`TRADING_CALENDAR`、`EQUITY_UNIVERSE`
- implementation binding 指向 `watchlist.strategies`
- threshold、lookback、排序與 universe 要求全部進入 definition digest

啟動時做 binding 驗證：目錄參數、code-owned defaults 與 artifact 使用參數不一致即拒絕執行。

## 8. 不可變 artifact

### 8.1 `WatchlistArtifactManifest`

至少包含：

- `artifact_id`、`schema_version`
- `target_session`、`as_of_session`
- `generated_at`、timezone
- historical dataset ID／digest
- daily derivation ID／digest
- calendar ID／version／digest
- universe type／version／digest
- corporate-action source／version／digest／coverage
- reference-price／price-limit source／version／digest／coverage
- `adjustment_as_of` 與 adjusted-view digest
- strategy IDs／definition digests
- Momentum variant config IDs／digests
- config digest
- input cutoff session
- artifact status
- `research_eligible`
- input／eligible／excluded／entry counts
- exclusion reason counts
- issues
- entries content digest
- manifest digest

### 8.2 `WatchlistEntry`

至少包含：

- symbol、名稱、market
- target／as-of session
- matched strategy IDs
- 各策略 rank 與 overall rank
- raw／adjusted OHLC、adjustment factor 與 corporate-action flags
- reference／limit prices、limit／one-price flags 與 market-state cohort
- adjusted close、SMA20、20 日高、volume ratio
- adjusted／reference daily return、close location
- Momentum variant memberships
- NR7 compression range percentage
- RSI、布林下軌、lower-band distance
- 20 日平均 `traded_value_proxy`
- 實際 thresholds
- 輸入日 K row digests
- entry digest

overall rank 需使用明確、版本化的 aggregation 規則。第一版建議以每個命中策略的 percentile rank 取最佳值，再以命中策略數、流動性代理值與 symbol 打破同分；不得依賴 dict 或資料庫未指定的自然順序。

artifact 只保存當時可知資訊；未來報酬、目標日開盤或盤中是否觸發，不得寫入 artifact，必須另存 evaluation report。

## 9. Persistence 與 migration

新增 PostgreSQL migration，例如：

```text
backtest/migrations/004_previous_day_watchlists.sql
```

並同步更新 SQLite schema。建議資料表：

### 9.1 `backtest_daily_derivations`

- dataset ID／digest
- parent dataset ID
- status
- row count
- content digest
- started／completed／created timestamps
- error code／message

### 9.2 `backtest_daily_bars`

- dataset ID
- symbol
- session date
- raw OHLCV 的 Decimal 字串
- `traded_value_proxy` 的 Decimal 字串
- source bar count
- row digest
- primary key：`(dataset_id, symbol, session_date)`

### 9.3 `backtest_daily_adjusted_views`

- dataset／raw derivation ID
- `adjustment_as_of`
- adjustment/reference snapshot digests
- symbol、session date
- adjusted OHLC、price／volume adjustment factors
- corporate-action type／source digest／available-at timestamp
- reference／limit prices 與 limit／one-price flags
- feature payload／row digest
- primary key：`(dataset_id, adjustment_as_of, adjustment_snapshot_digest, symbol, session_date)`

raw daily bars 永遠不因新的 corporate action 改寫。歷史 `T` 必須查詢 `adjustment_as_of=P` 的 view；新的 action 或修正版 snapshot 產生新 view/digest，不更新舊 row。

### 9.4 `candidate_watchlist_artifacts`

- artifact ID
- target／as-of session
- dataset／daily derivation／calendar／universe／config digests
- status
- research eligibility
- manifest JSON
- artifact digest
- created timestamp

唯一鍵至少涵蓋：

```text
(target_session, dataset_digest, calendar_digest, universe_digest,
 strategy_set_digest, config_digest)
```

### 9.5 `candidate_watchlist_entries`

- artifact ID
- symbol
- overall rank
- payload JSON
- entry digest
- primary key：`(artifact_id, symbol)`

repository 寫入必須以 transaction 發布 manifest 與 entries。相同 idempotency key 重跑只能回傳同一 artifact；若內容 digest 不同，回報 `NON_DETERMINISTIC_REPLAY`，不可覆寫。

## 10. Application service、排程與 CLI

### 10.1 工作流程

```text
resolve T/P
  -> validate calendar coverage
  -> resolve immutable dataset complete through P
  -> validate/build raw daily derivation
  -> resolve only reference data available/effective through P
  -> validate/build adjustment_as_of=P daily view
  -> resolve equity universe as of T
  -> calculate shared features once
  -> execute enabled strategy definitions
  -> deterministic rank/merge
  -> build and hash artifact
  -> transactional publish
  -> expose read-only projections
```

工作狀態：

- `WAITING_FOR_DATA`
- `DERIVING_DAILY_BARS`
- `GENERATING`
- `READY`
- `DEGRADED`
- `FAILED_CALENDAR`
- `FAILED_DATASET`
- `FAILED_NON_DETERMINISTIC`

個別 symbol 缺資料可以產生 `DEGRADED` artifact，但必須列出排除數量與原因；calendar／dataset／digest 級錯誤不可降級繼續。

Corporate-action、reference-price 或 price-limit coverage 缺失時，該 symbol 不得進入 Formal Validation；若缺口影響整個資料來源或無法確認 factor version，整份工作回報 `FAILED_REFERENCE_DATA`。不可退回 raw prices 默算。

### 10.2 排程

排程只在以下條件成立後觸發：

1. `P` 的 incremental historical sync 完成。
2. immutable dataset 狀態為 `READY`，且 coverage 明確包含 `P`。
3. daily derivation 為 `READY`。
4. `T` 在 calendar coverage 內。

建議 job ID：

```text
watchlist-{T}-{dataset_digest[:12]}-{config_digest[:12]}
```

Dashboard 或 API request 不得觸發 Provider download、Shioaji login 或全市場重新計算。

### 10.3 手動重現 CLI

新增：

```text
scripts/generate_previous_day_watchlist.py
```

介面範例：

```bash
python scripts/generate_previous_day_watchlist.py \
  --dataset-id <immutable_dataset_id> \
  --target-session 2026-08-20
```

輸出 artifact ID、digest、target/as-of、狀態、entry count 與 exclusion summary。CLI 不接受「直接用現在時間猜 target session」作為唯一模式；production job 必須顯式解析並記錄 `T`。

## 11. API 與 Dashboard

### 11.1 只讀 API

新增：

- `GET /api/dashboard/watchlists/latest`
- `GET /api/dashboard/watchlists/{target_session}`
- `GET /api/dashboard/watchlists/{target_session}/{symbol}`

回應必須包含：

- target／as-of session
- generated time、status
- data／calendar／universe／strategy digests
- research eligibility 與警告
- entries、matched strategies、rank、evidence
- exclusion summary

`latest` 的語意是「最新已發布 target session」，不可用目前日期臨時重算。無 artifact 時回傳明確的 not-ready response，不退回即時掃描結果。

### 11.2 Dashboard 面板

新增獨立區塊：`盤前觀察池（前日資料）`，顯示：

- 目標交易日、資料截止日、產生時間。
- `READY`／`DEGRADED`／not ready 狀態。
- `research eligible` 或 `survivorship limited` badge。
- 三策略篩選與命中交集。
- overall rank、流動性代理值與關鍵證據。
- 點選股票後顯示公式輸入、門檻與 artifact digest。
- 固定說明：「不含盤前試撮行情；納入觀察不等於買進訊號」。

既有即時 candidate score 列表保持原狀，不能把歷史觀察池項目無標示地混入分數排序。

## 12. 歷史驗證與防止 look-ahead

同一個 `WatchlistApplicationService.generate()` 必須能針對歷史 `T` 執行，禁止另寫一套回測專用策略公式。

正式研究模式要求：

- DATE_EFFECTIVE universe。
- 對應期間的版本化 calendar。
- immutable dataset 與 daily derivation digest。
- 日期有效且 coverage 完整的 corporate-action、reference-price 與 price-limit evidence。
- 每個 `T` 僅允許讀取 `session_date <= P`。
- 以 walk-forward／out-of-sample 切分，不以全期間最佳門檻回填歷史。

另建 evaluation report，衡量：

- 每日候選數與策略重疊率。
- 次日／多日 forward return。
- 盤中既有 ORB／EMA 進場條件的轉換率。
- gross PnL。
- commission、minimum fee、transaction tax、bid/ask spread 與 slippage 各自成本。
- net PnL、net expectancy 與成本占 gross edge 比例。
- turnover、最大回撤與分年度穩定度。

成本模型使用日期有效的 `CostSchedule`：commission rate／discount／minimum fee、依日期／商品／當沖資格適用的 transaction-tax schedule、bid/ask fill model 與 versioned slippage assumptions。稅率與費率不可寫死成永久常數；每個 evaluation report 保存 cost-policy ID、effective dates 與 digest。

Net-of-cost 是 Formal Gate，不是附加報表：只有 gross 結果、缺少任一成本元件、或只用 next-day close-to-close return 的研究一律不得推進 lifecycle。evaluation report 可以引用 artifact，但不得修改 artifact。策略由 `EXPERIMENTAL` 升級前，需同時通過 net OOS、最大回撤、跨期間穩定度與人工 review。

## 13. 實作階段與檔案清單

### Phase 0：P0 契約與 Formal Gate 凍結

目的：先把「哪些資料缺失時不能研究」寫成可測的 domain contract，避免 Phase 1/2 完成後才發現 raw／adjusted、漲跌停或成本語意不一致。

檔案：

- `architecture/previous_day_premarket_watchlist_implementation_plan.md`
- `config/watchlist.py`
- `watchlist/domain.py`
- `watchlist/costs.py`
- `strategy_catalog/service.py`
- `tests/test_watchlist_domain.py`
- `tests/test_watchlist_costs.py`

工作：

1. 在開始改碼前重跑全套測試並記錄當時 baseline 與 dirty-worktree ownership；目前工作樹有其他進行中變更，不能沿用舊數字或覆寫其他工作。
2. 凍結 `T`／`P`、timezone、input cutoff、`adjustment_as_of=P`、失敗關閉、research eligibility 與 immutable artifact schema version。
3. 定義並禁止隱式轉換：
   - `PriceBasis = RAW | ADJUSTED`
   - `CorporateActionType`
   - `AdjustmentEvidence`
   - `ReferencePriceLimitEvidence`
   - `PriceLimitState`
   - `MomentumVariantSpec`
   - `CostSchedule`
4. 凍結策略語意：
   - `previous_day_momentum_watchlist_v1` 是候選生成器。
   - `nr7_compression_watchlist_v1` 是 direction-neutral compression，不再使用 breakout 名稱。
   - `previous_day_oversold_watchlist_v1` 是等待 reversal confirmation 的候選，不是 BUY。
5. 將以下條件定義為 Formal Validation hard gates：
   - date-effective calendar／universe 完整。
   - corporate-action factor 與 reference／limit-price coverage 完整。
   - 同一 indicator window 不混用 raw／adjusted price。
   - 使用日期有效的 commission／minimum fee／tax／spread／slippage model。
   - 結論以 net-of-cost OOS 指標為準，不以 gross PnL 或 next-day return 代替。
6. 建立 feature flags，初始全部關閉；Phase 0 不啟動 scheduler、Dashboard 或 CandidatePool。
7. 為舊的 `candidate.nr7_breakout_watchlist_v1` 明確定義為「尚未發布、直接更名」，不得建立 alias 讓兩個 ID 看似不同策略；若已有外部 artifact，才另寫 migration decision record。

驗收：

- Domain tests 證明缺 adjustment／limit／cost evidence 時 Formal Validation 必定 fail closed。
- `high == low` 的 `close_location` 契約回傳 `None`。
- 三個 planned definitions 的 lifecycle 都凍結為 `EXPERIMENTAL`，且文字明確表示 observation-only／confirmation-required；Phase 3 只發布 Momentum executable binding，NR7／Oversold 到 Phase 5 實作時才發布，避免未綁定 definition 被誤認為可執行。
- 無 Provider 初始化、Shioaji 登入、BuyScore 變更或 broker dependency。
- Phase 0 contract review 通過後才能開始 reference-data adapter。

### Phase 1：日期有效 Reference Data 與 Corporate-action Foundation

目的：先建立可重現的 calendar、universe、corporate action、reference／limit price 與 cost-policy snapshots，再允許日 K 衍生。

檔案：

- `config/twse_calendar_YYYY.json`
- `config/watchlist.py`
- `watchlist/calendar.py`
- `watchlist/reference_data.py`
- `watchlist/adjustments.py`
- `watchlist/costs.py`
- `tests/fixtures/watchlist_corporate_actions.json`
- `tests/fixtures/watchlist_reference_price_limits.json`
- `tests/fixtures/watchlist_cost_schedules.json`
- `tests/test_watchlist_calendar.py`
- `tests/test_watchlist_reference_data.py`
- `tests/test_watchlist_adjustments.py`
- `tests/test_watchlist_costs.py`

工作：

1. 實作 calendar coverage、`previous_trading_day(T)` 與臨時休市失敗關閉。
2. 定義 `EquityUniversePort`，區分 `CURRENT_SNAPSHOT` 與 `DATE_EFFECTIVE`，後者才具有 Formal Validation 資格。
3. 定義不可變 `ReferenceDataSnapshot`，保存 source、effective dates、取得時間、schema version、content digest 與 coverage：
   - corporate actions／price factors。
   - 可用時的 volume factors。
   - raw opening reference price。
   - 已依價格級距處理的 limit-up／limit-down prices。
   - 日期有效的交易成本 schedule。
4. 實作 point-in-time factor-chain validation：每個 `P` 只能看 `available_at <= generation_cutoff` 且 `effective_date <= P` 的 actions，以 `P` 為 anchor 對 raw OHLC 使用同一 price factor 產生 adjusted OHLC；禁止只調 close 或使用 `P` 之後的 action。
5. 現金股利保留 raw volume；split／股票股利／減資等股數基礎改變事件若缺可信 volume factor，標記 `UNADJUSTED_VOLUME_CORPORATE_ACTION_WINDOW`。
6. 價格限制 flags 以官方 reference／limit prices 與 Decimal raw OHLC 判斷，不以固定 ±10% 或浮點 tolerance 推算。
7. 把來源衝突、factor gap、unknown action、reference-price gap、calendar gap 轉成穩定 error codes 與 coverage report。

驗收：

- 除息 fixture 的 raw `100 -> 95` 不會在 adjusted return 中被誤判成市場下跌 5%。
- 在 `P` 之後新增 corporate action 不會改變 `adjustment_as_of=P` 的 adjusted series 或 artifact digest。
- split、股票股利與減資 fixtures 的 adjusted OHLC 連續；缺 volume factor 時量能策略 fail closed，而不是沿用不可比 volume。
- raw OHLCV 保持 byte-for-byte source evidence，adjusted series 可由 snapshot 重算並得到相同 digest。
- one-price limit-up、one-price limit-down、收在限制價但有 range、僅盤中觸及限制價四種 fixtures 產生不同 flags。
- 週末、連假、補班但休市與 coverage 外測試通過。
- 成本 schedule 具有 effective dates 與 digest，沒有永久硬編碼單一稅率。

### Phase 2：Corporate-action-aware Daily Derivation、Features 與 Persistence

目的：把分鐘 K 與 Phase 1 reference snapshot 轉成一次性、不可變且可供 Momentum 使用的日資料，不在 Dashboard request path 臨時計算。

檔案：

- `features/technical_indicators.py`
- `backtest/indicators.py`
- `watchlist/daily_bars.py`
- `watchlist/features.py`
- `watchlist/repository.py`
- `backtest/migrations/004_previous_day_watchlists.sql`
- `backtest/repository.py`
- `tests/test_watchlist_daily_bars.py`
- `tests/test_watchlist_features.py`
- `tests/test_watchlist_repository.py`
- `tests/test_backtest_incremental_sync.py`
- 現有 backtest indicator tests

工作：

1. 對 base／incremental datasets 聚合 raw daily OHLCV、實際 `traded_value_proxy`、source count 與 row digest。
2. 保持 raw derivation 不可變，另以 `(raw_derivation, adjustment_as_of=P, reference_snapshot_digest)` 建立 adjusted view，保存 adjusted OHLC、price／volume factors、corporate-action metadata、reference／limit prices 與所有 limit／one-price flags。
3. 計算一次共用 features：
   - adjusted SMA20／rolling high20。
   - 量能 baseline／ratio；跨 action 且無可信 volume factor時不可計算。
   - `adjusted_daily_return`。
   - `reference_daily_return`，用於資料品質對照。
   - `close_location`；one-price bar 必須為 `None`。
   - RSI14、Bollinger20／2 與 normalized range percentage，全部使用同版本 adjusted price series。
4. 從 `backtest/indicators.py` 抽出共用 Decimal indicator，保留相容 re-export 與 parity tests。
5. 完成 PostgreSQL／SQLite schema、parent-chain resolution、transaction boundaries 與 old-schema read compatibility。
6. Raw derivation digest 只依 source dataset；adjusted-view digest 必須包含 `adjustment_as_of`、calendar、universe、corporate-action 與 reference-price schema／content digests。任一輸入變更都產生新 view，不覆寫舊資料。
7. 產生 data-quality report，至少統計 stale symbol、factor gap、unknown action、reference-price gap、unadjusted-volume window、one-price 與各 limit cohort。

驗收：

- 相同輸入即使列舉順序不同，daily rows、features 與 content digest 完全一致。
- incremental parent-chain 結果與同期間完整重算一致。
- raw／adjusted 欄位混用的 fixture 被拒絕，不能只記 warning 後繼續。
- ex-dividend、split、capital-reduction windows 不產生機械式假 Momentum／Oversold 訊號。
- 加入 `P` 之後才生效或才可得的 action，既有 `adjustment_as_of=P` view 完全不變。
- one-price bar 的 close location 為 `None`，NR7 eligibility 為 false。
- backtest indicator parity、flat RSI 與 Bollinger population-standard-deviation tests 通過。
- 日 K derivation 只能由 application/job path 建立；API／Dashboard read 不會觸發重算或 Provider 連線。

### Phase 3：Momentum v1、OOS Variants 與 Immutable Artifact 垂直切片

目的：只交付 Momentum 候選 artifact，證明資料截止、corporate-action safety、market-state cohort、確定性與證據鏈；不接 CandidatePool、Dashboard、scheduler 或進場決策。

檔案：

- `watchlist/strategies.py`
- `watchlist/artifacts.py`
- `watchlist/application.py`
- `watchlist/repository.py`
- `strategy_catalog/service.py`
- `scripts/generate_previous_day_watchlist.py`
- `tests/test_watchlist_strategies.py`
- `tests/test_watchlist_artifacts.py`
- `tests/test_watchlist_application.py`
- `tests/test_strategy_catalog.py`

工作：

1. 實作 `previous_day_momentum_watchlist_v1` baseline：adjusted close above SMA20、within 2% of adjusted 20-day high、volume ratio at least 1.5。
2. 每個 baseline entry 同時計算四個 immutable variant memberships：
   - `baseline`
   - `positive_return`
   - `strong_close_060`
   - `positive_return_strong_close_060`
3. `0.6` 只存在 versioned `MomentumVariantSpec`；Phase 3 不選出「最佳」variant，也不改成 ACTIVE／production threshold。
4. 依 `NORMAL`、`LIMIT_UP_CLOSE`、`LIMIT_DOWN_CLOSE`、其他限制狀態分 rank partition；artifact 顯示 cohort，歷史報告不得混成單一母體。
5. artifact 保存 raw／adjusted evidence、`adjustment_as_of`、adjustment／reference digests、daily returns、close location、limit flags、variant memberships、row digests 與所有實際 thresholds。
6. 完成 transactional publish、idempotency key、replay digest、`NON_DETERMINISTIC_REPLAY` 防護與 strategy-definition binding 驗證。
7. 提供 deterministic CLI；指定 dataset ID 與 `T`，輸出 artifact／coverage／exclusion／cohort／variant summaries。
8. catalog 與 CLI 固定顯示「盤前候選、非買進訊號、尚未通過 net-of-cost Formal Validation」。

驗收：

- 高量但收弱 fixture 仍可落在 baseline，但 `positive_return`／`strong_close_060` membership 正確失敗，證明 evidence 能區分可能的沖高出貨。
- `open=97, high=102, low=97, close=98.5` 的 close location 為 0.3，不得誤列為 strong-close variant。
- one-price bar 不會偽造 close location；one-price limit-up 可保留為獨立 cohort evidence，但不能進 strong-close variant。
- 一般與 limit-up Momentum 分區排名，evaluation 不混樣本。
- 除息／減資 fixture 使用 adjusted series，不產生機械式 Momentum 命中或排除。
- 指定相同 dataset／reference snapshots／`T` 重跑得到同一 artifact ID 與 digest。
- 注入 `T` 或之後的毒化資料，artifact 完全不變。
- 注入 `P` 之後才發生／可得的 corporate action，artifact 完全不變。
- 修改 factor、reference-price、variant config 或策略 definition 會建立新 digest，不覆寫舊 artifact。
- Phase 3 結束時沒有 CandidatePool admission、Dashboard 顯示、scheduler 啟用、BuyScore 變更或 broker call。

### Phase 4：CandidatePool、API 與 Dashboard

檔案：

- `candidate/models.py`
- `watchlist/candidate_source.py`
- `candidate/pool.py`（只有必要的 source handling）
- Dashboard API route／service 檔案
- `dashboard/static/index.html`
- `tests/test_watchlist_candidate_source.py`
- `tests/test_watchlist_api.py`
- `tests/test_watchlist_dashboard_ui.py`

工作：

- 新增 `PREVIOUS_SESSION_WATCHLIST` source。
- artifact 投影到 CandidatePool。
- 新增獨立只讀 UI，不改既有 candidate score 語意。

驗收：觀察池能被訂閱／檢視，但不會觸發 BuyScore、模擬單或 broker call。

### Phase 5：NR7 Compression 與 Oversold Confirmation Candidates

檔案：

- `watchlist/strategies.py`
- strategy catalog definitions
- strategy／artifact／UI tests

工作：

- 使用 Phase 2 的 adjusted-price features 實作 `nr7_compression_watchlist_v1` 與 `previous_day_oversold_watchlist_v1`。
- NR7 排除 one-price false compression，保留 limit-touch／limit-close cohorts，且不產生方向或 LONG bias。
- Oversold artifact 固定標示 confirmation-required，不得因 RSI／Bollinger 同時命中就提高 BuyScore。
- 完成每策略 rank、overall rank aggregation 與多策略交集 UI。

驗收：固定 fixture 的公式、邊界值、排序與 digest 全部穩定；NR7／Oversold 在沒有目標日 VWAP／ORB／reclaim confirmation 時不會形成 entry decision。

### Phase 6：排程、歷史研究與 rollout

檔案：

- scheduler／runtime composition 檔案
- watchlist evaluation service／repository
- runbook／README
- scheduler、historical replay、integration tests

工作：

- 在 immutable sync／derivation READY 後自動產生下一交易日 artifact。
- 加入歷史 walk-forward evaluation。
- 實作日期有效 `CostSchedule` 與 gross-to-net attribution，將 net-of-cost OOS、最大回撤與跨期間穩定度設為 Formal Gate。
- 補監控、runbook、feature flag 與 rollback 演練。

驗收：連續多個歷史 target sessions 可重現；所有 evaluation reports 都包含 commission／minimum fee／tax／spread／slippage 與 net PnL；缺任一成本元件時不得推進 lifecycle；production 啟用前完成 shadow run 與人工核對。

## 14. 測試矩陣

### 14.1 Calendar／時間

- 週五 `P` 到週一 `T`。
- 跨農曆年等長假。
- 補班但休市。
- calendar coverage 外失敗關閉。
- artifact 建立後目標日臨時休市。
- timezone-aware timestamps 與 DST 無關性。

### 14.2 資料品質

- dataset coverage 不到 `P`。
- 個股最新 session 舊於 `P`。
- 重複 session、負 volume、OHLC 不合理。
- incremental parent chain 有缺口。
- universe 缺少日期有效證據。
- `traded_value_proxy` 與 true turnover 標示不混淆。
- corporate-action factor coverage 缺口／衝突／unknown action。
- 除息、split、股票股利與減資的 raw／adjusted continuity。
- 跨股數事件但缺 volume factor 時量能 feature fail closed。
- reference／limit price coverage 缺口與價格級距後 Decimal equality。
- one-price、limit-touch、limit-close、limit-locked-one-price 分類。

### 14.3 策略公式

- 門檻正好等於 0.98、1.5、30 時的 inclusive/exclusive 行為。
- Momentum volume baseline 確認排除 `P`。
- Momentum 四個 variant memberships、`daily_return > 0` 與 `close_location >= 0.6` 邊界。
- `high == low` 時 close location 為 `None`，不能進 strong-close variant。
- Momentum 的一般與 limit-up cohorts 分開排名／評估。
- NR7 compression 包含 `P` 在七日視窗、排除 one-price，並固定 tie 行為。
- RSI flat series 回傳 50。
- Bollinger 使用 population standard deviation。
- 所有同分最後以 symbol 打破。

### 14.4 Look-ahead／確定性

- 在 `T` 或更晚加入極端毒化 K 線，artifact 完全不變。
- 任意 shuffle 輸入列，entry order 與 digest 不變。
- 同一 idempotency key 重跑回傳相同 artifact。
- 相同 key 但不同內容被拒絕為 non-deterministic。
- current snapshot universe 的 artifact 永遠不是 research eligible。

### 14.5 整合與安全

- API 讀取不建立 Provider connection。
- Dashboard 讀取不觸發歷史下載或日 K 重算。
- CandidatePool admission 不改 BuyScore。
- 無 Shioaji credential 仍可啟動只讀觀察池 API。
- artifact 到期後不被下一交易日默默沿用。
- 既有 `premarket_gap_watchlist_v1` 狀態與定義不變。

### 14.6 Formal Validation 成本與確認

- 同一筆歷史交易同時輸出 gross PnL、各成本元件與 net PnL。
- Cost schedule 依交易日期、商品與當沖資格選版，並保存 effective dates／digest。
- minimum commission、bid/ask fill、零／低成交量 slippage 與價格跳空 fixtures。
- 缺 tax／commission／spread／slippage 任一設定時 Formal Gate fail closed。
- NR7／Oversold 沒有盤中 confirmation 時只統計候選，不建立假設成交。
- variant threshold 只在 train／validation 區間選擇，holdout 不回填調參。

## 15. Feature flags、觀測與 rollback

新增 feature flags：

- `PREVIOUS_DAY_WATCHLIST_ENABLED`
- `PREVIOUS_DAY_WATCHLIST_SCHEDULER_ENABLED`
- `PREVIOUS_DAY_WATCHLIST_DASHBOARD_ENABLED`

啟用順序：

1. migration 與 daily derivation。
2. 手動 CLI shadow generation。
3. scheduler shadow generation。
4. Dashboard read-only 顯示。
5. CandidatePool adapter。

監控項目：

- 最新 READY artifact 的 target/as-of 與年齡。
- input／eligible／excluded／entry counts。
- 各 exclusion reason 比例。
- generation／derivation latency。
- digest mismatch、calendar coverage、dataset incomplete 次數。
- 每策略候選數與交集異常。

Rollback 只需依序關閉 CandidatePool、Dashboard、scheduler flags；不可刪除或覆寫已發布的 immutable artifacts。schema 採向前相容 migration，不做 destructive rollback。

## 16. Definition of Done

- 三個策略都有固定版本、精確公式、排序與 strategy catalog definition digest。
- 所有輸入明確截止於 `P`，poison-future tests 通過。
- calendar、dataset、daily derivation、universe、corporate-action、reference／limit-price、variant config 與 cost schedule 全部可追溯到 digest。
- raw OHLCV 完整保留；所有價格型指標只用同版本 adjusted OHLC，量能跨 action 的可比性有明確 gate。
- one-price／limit flags 正確；NR7 不把鎖漲跌停或零振幅 bar 當作一般壓縮。
- Momentum 保存 daily-return／close-location evidence，四個 OOS variants 不被誤標為正式門檻。
- 日 K 衍生結果能處理 base／incremental datasets，且 replay deterministic。
- artifact transaction、idempotency、schema migration 與舊 artifact 讀取測試通過。
- current universe 與 date-effective universe 的研究資格標示正確。
- CandidatePool 只增加觀察來源，不改變買賣決策語意。
- Dashboard 明確標示「前日資料、不含試撮、非買進訊號」。
- API／Dashboard 讀取路徑不連線 Provider 或 broker。
- Formal Validation 報告具備完整 gross-to-net attribution；只有 net-of-cost OOS 結果可通過 promotion gate。
- PostgreSQL、SQLite、unit、integration、static UI 與全套 regression tests 通過。
- shadow run 至少涵蓋正常交易日、週末後開市與連假後開市，人工核對公式與 artifact 證據完成。
- runbook 記載產生、重跑、失敗關閉、calendar 更新、feature flag 與 rollback 流程。

## 17. 建議的第一個可審查切片

第一個 PR／commit 僅做 Phase 0 到 Phase 3 的 Momentum 垂直切片：

- P0 target/as-of、raw／adjusted、Formal Gate 與 observation-only 契約。
- calendar、date-effective universe、corporate-action、reference／limit-price 與 cost-policy snapshots。
- corporate-action-aware immutable daily derivation 與共用指標抽取。
- `previous_day_momentum_watchlist_v1` baseline、四個 OOS variants 與 market-state cohorts。
- evidence-rich artifact repository、deterministic CLI 與 poison-future／replay tests。
- 無 CandidatePool、無 Dashboard、無排程啟用。

這個切片先證明資料截止、corporate-action correctness、漲跌停分類、variant evidence、確定性與不可變證據；它不宣稱 Momentum 已獲利，也不建立進場決策。通過後才把相同基礎延伸到 NR7 Compression、Oversold Confirmation 與觀察介面。
