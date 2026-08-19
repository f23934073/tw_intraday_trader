# 日 K SMA20／SMA60 交叉策略 Implementation Plan

## 1. 結論與範圍

本計畫新增一個獨立、預設不勾選的日 K 策略族，不修改既有
`ema_crossover_entry_v1`。它包含兩個可各自選擇的 `EXPERIMENTAL` 策略：

| Strategy ID | Role | 訊號 |
|---|---|---|
| `sma_20_60_golden_cross_entry_v1` | ENTRY | SMA20 由下往上穿越 SMA60 |
| `sma_20_60_death_cross_exit_v1` | EXIT | SMA20 由上往下跌破 SMA60 |

本文件將「MA20／MA60」定義為 **Taiwan timezone、完整日 K 收盤價的
simple moving average**，不是現有一分 K 的 EMA。策略只能在 sealed
historical dataset 中回測：訊號在當日日 K 完成後判斷，成交維持既有的
下一根日 K 開盤模型。

不包含：

- 修改 dashboard 圖表的 MA5／20／60 顯示或將其 Provider 回應當作策略輸入。
- Shioaji 下單、CA、帳務、即時自動交易或任何真實金流。
- 將原始 Kbar 的查詢區間長度當成日 K 解析度證據。
- 宣稱此策略具有獲利性；它僅是可重現的研究假說。

## 2. 目前程式的確認狀態

| 區域 | 現況 | 對本計畫的意義 |
|---|---|---|
| `dashboard/service.py::_moving_averages` | 3 個月圖表以日 K close 算 SMA5／20／60 | 僅供呈現；不可重用其 on-demand Provider 輸入。 |
| `backtest/strategies.py::EmaCrossoverEntryStrategy` | EMA(5) 上穿 EMA(20)，一分 K、每 session reset、12:45 前 | 不可改 period 或改成 SMA，否則舊 run 不可重現。 |
| `backtest/features.py::BarFeatureState` | 按 symbol-session 建立，且只保留 20 根 close | 不足以保存 60 個交易日。 |
| `backtest/engine.py` | 每個 session 內建立 feature state，先 fill 前一根 pending order，再更新 completed-bar features 並評估策略 | 可保留 next-bar execution；需新增跨 session 的 daily state。 |
| `backtest/dataset.py::_CadenceEvidence` | 能辨識 intraday / 1m；非 intraday 目前只有 `OHLCV` | 需要明確 `KBAR_DAILY` 資料契約。 |
| `backtest/application.py` | create-run 與 worker 都會驗證 strategy capabilities | 新 daily capability 可沿用 fail-closed gate，無需新回測 route。 |

## 3. 凍結的策略契約

### 3.1 計算與 warm-up

對 symbol 的第 `t` 根有效日 K close `C_t`：

```text
SMA20_t = (C_t + ... + C_(t-19)) / 20
SMA60_t = (C_t + ... + C_(t-59)) / 60
```

- 全部以 canonical `Decimal` 計算、比較與 digest；只有 API presentation 可轉為
  既有的 float payload。新 daily path 不接受 `Decimal(float)`：adapter 必須先保留
  source decimal/string value，再以 `Decimal(string)` 轉換。
- 定義 `canonical_decimal_v1`：拒絕 NaN／Infinity；把 `-0` 正規為 `0`；以
  `normalize()` 後的非科學記數法字串保存。因此 `103`、`103.0`、`103.00` 都是
  同一個 canonical input (`"103"`)；canonical JSON 的 key ordering、UTF-8 bytes
  與 SHA-256 也沿用同一版本。若 source SDK 僅給 Python float，dataset 必須留下
  `SOURCE_FLOAT_LOSSY` issue，不能升格為正式研究證據。
- `SMA20` 在第 20 根有效日 K 前為 `None`；`SMA60` 在第 60 根前為 `None`。
- 交叉至少需要 current 與 previous 的兩組 SMA，所以最早在第 61 根有效日 K
  才可能觸發。
- 週期是「每個 symbol 的有效、完成日 K 觀測數」，不是 20／60 個日曆日。
  週末、休市與停牌不以人工填價補齊。
- 若同一 symbol/date 有重複、不一致或未被驗證為 finalized daily bar，資料集
  不可獲得 `KBAR_DAILY`；策略不可執行。單一 symbol 歷史不足時則回傳
  `INSUFFICIENT_DATA`，不影響資料集中其他 symbol 的評估。

### 3.2 Crossing 與 strategy evidence

| 策略 | `previous` | `current` | 結果 |
|---|---|---|---|
| Golden ENTRY | `sma20 <= sma60` | `sma20 > sma60` | `TRIGGERED` |
| Death EXIT | `sma20 >= sma60` | `sma20 < sma60` | `TRIGGERED` |

- equality 只允許發生在前一根，current 必須嚴格跨到另一側；因此 MA 持續位於
  同側不會重複訊號。
- 每個有效 crossing transition 只會產生一筆 SMA `TRIGGERED` evidence；same-side
  observation 產生零筆 SMA trigger evidence。這和 `ANY`／`ALL`／`AT_LEAST_N`
  聚合後是否形成 trade decision 是兩件獨立且各自測試的事。
- `death_cross_exit` 只在已有 position 時評估；沒有 position 時不產生 sell
  decision。它不可強迫替換使用者明確選擇的其他 exit policy。

### 3.3 Execution horizon、跨 session pending 與 end-of-data

`context.is_last_bar` 在目前 engine 的意思是「該 symbol 在**當前 session**的最後
一根」，不是整份 dataset 的最後一根。這個語意必須保留給既有
`end_of_day_exit_v1`；daily dataset 每個 session 只有一根 bar，不能把它拿來判斷
日 K trade 是否要在 signal close 成交。

新增 code-owned `ExecutionHorizon`，並將它記錄在 `StrategyEvaluation`、
`TradeDecision`、`_PendingOrder` 與 order result：

| Horizon | 適用對象 | 成交／收斂規則 |
|---|---|---|
| `INTRADAY_NEXT_BAR` | 既有 ORB／EMA／RSI 與一般 intraday exits | 僅可在同一 resolved session 的後一根 bar open 成交；session 結束仍未成交則以既有/明確 cancel reason 收斂。 |
| `DAILY_NEXT_BAR` | SMA golden ENTRY 與 death EXIT | pending 必須跨 session 保存，僅能在同一 symbol 的下一個 resolved daily session 首根有效日 K open 成交。 |
| `SESSION_CLOSE` | 只有 `end_of_day_exit_v1` | 只在該 session 最後一根以 close 成交。 |

DecisionAggregator 仍依 policy 和 priority 選 primary trigger，但 execution horizon
必須由 primary strategy 的 immutable definition 決定並存入 decision。若聚合的
triggered strategies 有不同 horizon，result 必須保留所有 evidence、primary ID 與
chosen horizon；不可用目前的 `is_last_bar` shortcut 隱式決定成交時點。

engine 在完整 dataset 事先計算每 symbol 的真正 terminal bar（不是 session-last
bar）。對 `DAILY_NEXT_BAR`：Day T completed close 產生 pending，Day T+1 resolved
daily session open 才 fill；若不存在下一有效 daily bar，evaluation/decision evidence
仍保存，但 order 收斂為 `UNFILLED_END_OF_DATA`，不可遺留模糊的 `SUBMITTED`。

### 3.4 Strategy definition

兩個 definition 皆須包含：

```text
version: v1
status: EXPERIMENTAL
required_capabilities: OHLCV, KBAR_DAILY
parameters:
  fast_period: 20
  slow_period: 60
  ma_type: SMA
  bar_resolution: DAILY
  price_field: CLOSE
  price_adjustment_policy: RAW
  signal_as_of: COMPLETED_DAILY_CLOSE
  execution_horizon: DAILY_NEXT_BAR
  feature_version: daily-sma-features-v1
```

ENTRY／EXIT 的 `display_name_zh_tw`、description、`execution_binding` 與
`code_identity` 都必須不同。回測結果的 `observed` 至少保存 current／previous
SMA20、SMA60、有效日 K 數、feature input digest、cross direction 與 source
dataset id/digest、`price_adjustment_policy`、resolved session date 與 execution
horizon。

## 4. Daily dataset contract（P0）

### 4.1 為何不可直接用現有 dashboard 或 heuristic

`MarketDataProvider.get_kbars()` 目前不帶 requested interval。Mock provider 在
多日查詢時回傳日 K，但 Shioaji mapping 視回傳內容為原始 Kbar；因此「一次查
多天」或「某日剛好只看到一根 bar」都不能證明這是 finalized daily close。

策略輸入必須是新 sealed manifest，至少有：

```text
profile: KBAR_DAILY_V1
capabilities: OHLCV, KBAR_DAILY
timezone: Asia/Taipei (由各 HistoricalBar 驗證)
session_contract:
  version: tw_equity_regular_session_v1
  resolver: calendar-backed
  calendar_id: <official calendar version>
price_adjustment_policy: RAW
corporate_action_adjusted: false
daily_bar_contract: EXPLICIT_SOURCE_DAILY_V1 or DERIVED_FINALIZED_SESSION_V1
parent_dataset_id: <source dataset id, if derived>
parent_dataset_digest: <source digest, if derived>
derivation_version: daily-ohclv-v1 (if derived)
```

`DatasetManifest` 應以可選 `daily_bar_contract`／`derivation`／`session_contract`／
`price_adjustment_policy` metadata 保存上述欄位；它們必須進入新 manifest digest。
舊 manifest 不加欄位、也不重算其 digest。新的 `KBAR_DAILY` capability 只會由
明確 daily source 或通過下列 finalized-session gate 的 derived dataset 取得，不由
`_CadenceEvidence` 對非 intraday 資料的 fallback 推論。

### 4.2 P0：price adjustment 與 resolved session date

v1 明確凍結 `price_adjustment_policy: RAW`：OHLCV 是未做 backward／forward
adjustment 的原始價格序列，並記錄 `corporate_action_adjusted: false`。derived
dataset 必須原樣繼承 parent policy；不同 policy 的資料不得混合、不得與同一 run
比較成同一價格序列。完整除權息調整可後續加入 `BACKWARD_ADJUSTED` 或
`FORWARD_ADJUSTED` version，但沒有對應 corporate-action source 與 reconciliation
前，`formal_research_eligible` 必須為 false。

新增 calendar-backed `SessionResolver`（建議 `backtest/session.py`）及 additive
`HistoricalBar.session_date`。source ingestion 要先把 timestamp 正規到
`Asia/Taipei`，再依 versioned official calendar/session contract 解析 session date；
daily aggregation、dataset cadence、engine session grouping、daily feature snapshot
和 daily pending fill 全部使用 resolved value，禁止在 daily path 直接呼叫
`timestamp.date()`。

為維持舊 dataset：`session_date` 是 legacy bar 的 optional serialized field，舊
intraday path 可保留目前行為；但新 `KBAR_DAILY` manifest 必須保存完整 session
contract，且每根輸入／輸出日 K 都必須有 resolved session date。

### 4.3 Gate D0：資料來源資格

在寫 daily derivation 前，先以可保存的 provider fixture 驗證實際 ordinary-stock
Kbar 內容：

1. 同一 source contract 是否提供已收盤的 daily OHLCV，或只能提供 intraday
   bars。
2. raw timestamp 的 timezone、calendar/session resolver 結果、交易日邊界、無成交
   分鐘與收盤完整性表達方式。
3. 最後一個未完成交易日如何識別與排除。
4. 使用者下載日期區間跨 29 天分段時，是否會出現重複／缺 bar／分段邊界差異。

若能證明 direct daily source，實作 `EXPLICIT_SOURCE_DAILY_V1` importer。
若只有 intraday source，實作 `DERIVED_FINALIZED_SESSION_V1`：以一個已 sealed、
已驗證 session completion 且帶 resolved session date 的 base dataset 為來源，按
`(symbol, resolved_session_date)` 聚合 first open / max high / min low / last close /
sum volume（amount 同樣加總）。未通過 completion gate 的 session 不能輸出日 K，
必須保留明確 issue。

若 D0 無法得到 finalized-session evidence，停止在資料契約階段；不可先註冊可在
不完整日 K 上運行的 SMA 策略。

### 4.4 Lineage、calendar 與研究資格

- Derived daily dataset 需完整 materialize 自己的 `bars.jsonl`、checksum 與
  manifest，並以 `parent_dataset_id` / digest 做 lineage；不得原地覆寫 base。
- `research_eligible` 預設繼承 base 的較嚴格值；base 為 `CURRENT_SNAPSHOT`
  或有 survivorship issue 時，derived dataset 也不能被標為正式研究證據。
- `price_adjustment_policy: RAW` 或 `corporate_action_adjusted: false` 的資料也不能
  被標為 formal research eligible；它可用於可重現的 hypothesis run，但不能隱藏
  除權息可能造成 crossover 的限制。
- v1 的 SMA period 採有效日 K sequence，不將 calendar-date gap 自動視為缺資料；
  但 manifest 必須輸出 resolver version、每 symbol resolved-session count、first/
  last session date 與 skipped/incomplete sessions，供 qualification 檢查。
- 正式績效宣稱前另需 ordinary-stock trading calendar、date-effective universe、
  corporate-action/adjustment policy 與 reconciliation；這些不以 TAIFEX night
  session calendar 代替。

## 5. Feature 與 engine design

### 5.1 新增 isolated daily feature state

新增 `backtest/daily_features.py`，不擴張現有 session-local
`BarFeatureState`：

```text
DailySmaFeatureSnapshot
  symbol, resolved_session_date, as_of, daily_bars_seen, close
  sma20, sma60
  validity, missing_reasons
  feature_version, input_digest

DailySmaFeatureState(symbol)
  deque(maxlen=60), rolling_sum_20, rolling_sum_60
  current snapshot
```

- `apply()` 只接收 timestamp 嚴格遞增、同一 symbol 且帶 resolved session date 的
  valid daily bar。
- 使用 bounded queue / rolling sums；空間為 `O(symbols × 60)`，不能回讀整個
  dataset 或讓各 strategy 私藏 unbounded history。
- `input_digest` 包含 feature version、previous digest / complete 60-close window、
  canonical decimal close、resolved session date、price adjustment policy、current bar
  identity 與 window count；同一數學 input 必須有同一 canonical digest。
- `backtest/indicators.py` 新增 pure `simple_moving_average` golden tests，daily
  state 必須與該公式完全一致。

### 5.2 Engine integration

在 `HistoricalBacktestEngine.run()`：

1. 以 resolved session date 分組；保留 `is_last_bar` 的既有「session 最後一根」
   語意，另計算每個 symbol 的 `is_terminal_dataset_bar`。daily path 不可使用
   `timestamp.date()` 作分組或 terminal 判斷。
2. 從 selected IDs 判斷是否需要 daily features；只有選了 SMA family 且 preflight
   已通過 `KBAR_DAILY` 時才建立 `daily_feature_states[symbol]`。
3. 將此 map 放在 session loop 外，因此同一 symbol 跨交易日維持 state；既有
   `BarFeatureState` 仍在 session loop 內，行為完全不變。
4. 每日 Kbar 的既有處理順序保持：先依 `ExecutionHorizon` fill older pending
   order，再把 current
   completed daily bar 更新進 daily state，形成 current/previous snapshot，接著
   exit、entry aggregation。
5. 在 `StrategyContext` 新增 optional `daily_features`、
   `previous_daily_features`、`resolved_session_date` 與 `is_terminal_dataset_bar`；
   既有 strategy、fixture 與 v1/v2 legacy run 保留其原本的 session-last 行為，
   不可改變結果 digest。
6. `_evaluate_exit()` 只讓 `SESSION_CLOSE` strategy 在 session-last bar close
   成交。SMA death exit 一律建立 `DAILY_NEXT_BAR` pending，不能因 daily bar 是
   session-last 而走 EOD shortcut。
7. 在 engine finalization 取消／標記真正 terminal bar 後仍未有 future eligible
   bar 的 pending orders，並把 reason、origin decision、chosen horizon、resolved
   session date 與 dataset end timestamp 寫入 result。這個修正要同時覆蓋 daily
   entry 與 daily exit，且要回歸既有策略。

`backtest-engine-v2` 繼續承載新 family；把兩個 strategy ID 加入 v1 reject set。
舊 v1 retry 不可悄悄轉到 v2，舊 manifest 也不可被補上 `KBAR_DAILY`。

## 6. Registry、application 與 UI

### 6.1 Server-side registration

- `backtest/strategies.py`：新增兩個 strategy classes，註冊到 `StrategyRegistry`。
- `strategy_catalog/service.py`：新增兩個 immutable execution bindings 到
  `_BUILTIN_BINDINGS`；code definition 與 catalog digest 必須一致。
- `backtest/domain.py`／`backtest/decision_aggregator.py`：把 primary strategy 的
  `ExecutionHorizon` 納入 evaluation、decision digest/payload 與 aggregation audit。
- `backtest/engine.py`：擴充 experimental-v2 validation、daily feature injection、
  horizon-aware pending lifecycle 與 terminal-data finalization。
- `backtest/application.py`：沿用雙層 capability preflight。建立 run 或 worker
  發現 `KBAR_DAILY` 缺失時，錯誤需明確指出 strategy ID 與 capability。

不新增 browser-side calculation、strategy-specific evaluation API 或參數覆寫。

### 6.2 Dataset derivation command

將 daily dataset generation 做成 application/catalog use case，CLI 只是 thin
adapter，例如：

```text
python scripts/derive_backtest_daily_dataset.py \
  --base-dataset-id <sealed-base> \
  --idempotency-key <key>
```

use case 必須讀 READY base manifest、執行 D0 contract、materialize 新 dataset、
upsert repository metadata，並回傳 new dataset id/digest/capabilities/lineage。這讓
既有 dataset-list API 與 Dashboard 的 dataset selector 不需新 read endpoint。

若未來要從 Dashboard 觸發 derivation，必須另開 durable job（不可在 browser
refresh 同步跑全資料集）；不屬於本 slice。

### 6.3 Dashboard safety

既有 UI 已能：顯示 experimental status、disable missing capability、保留 ACTIVE
baseline default。此 slice 僅補：

- 以繁中說明 `SMA20／60 日 K`、`訊號於收盤完成`、`下一日開盤成交`。
- 當選擇 golden entry 或 death exit 時，若同時選了 `end_of_day_exit_v1`，顯示
  non-blocking warning：「EOD exit 會在每個日 K 收盤平倉，可能不符合 MA 趨勢持有。」
- 不自動勾選 SMA strategies、不自動取消使用者已選 exits、不把 warning 當成
  server-side bypass。
- 回測結果 summary／trade attribution 必須同時顯示 selected entry／exit strategy
  IDs、primary trigger、aggregation policy 和 execution horizon，避免把「SMA20/60
  回測」誤讀成沒有 EOD 或其他 exit 的單一策略績效。

## 7. Implementation phases and gates

### Phase 0 — Baseline and source qualification

1. 保存 current full test baseline、existing v1/v2 result digest fixtures、dirty
   worktree inventory。
2. 完成 D0 provider fixture：direct daily 或 raw intraday 的 actual shape、timezone、
   session resolver、finalization proof。
3. Freeze `price_adjustment_policy: RAW`、`corporate_action_adjusted: false`、
   decimal canonicalization、session contract、execution horizon、aggregation policy
   and incomplete-session behavior.

**Gate G0:** 沒有 source-completion / resolved-session evidence 時不寫 strategy code；
manifest 的 P0 adjustment / decimal / session / execution contracts 未凍結時也不得進入
feature implementation。現有 dashboard 與 run 均不變。

### Phase 1 — Immutable daily dataset

1. 在 `backtest/dataset.py` 增加 explicit daily manifest metadata 與
   `create_derived_daily_dataset()` / direct-daily importer。
2. 新增 deterministic aggregation、base lineage、checksum、per-symbol resolved daily
   coverage summary、incomplete-session issues、price adjustment policy and session
   contract propagation。
3. 建立 `KBAR_DAILY` capability，保留 legacy manifest serialization/digest；所有新
   policy fields 必須由 digest 覆蓋。
4. 在 application service and CLI 接入 derivation，upsert 新 READY dataset。

**Gate G1:** 同一 canonical base bytes 永遠產生同一 derived bars checksum / manifest
digest；不完整 session、duplicate bar、timezone/session mismatch、non-READY parent、
missing adjustment policy 均 fail closed；base dataset 不變。

### Phase 2 — Daily Decimal features and session semantics

1. 新增 `daily_features.py`、SMA pure indicator 與 bounded snapshots/digests。
2. 在 engine 增加跨 session daily state、resolved session context、session-last /
   terminal-data distinction。
3. 實作 canonical decimal storage/digest path，驗證 equivalent numeric
   representations 有同一 feature evidence。
4. 驗證不選 SMA family 的 legacy v2 golden result digest 不變。

**Gate G2:** 20/60 warm-up、cross-session retention、repeated-run Decimal equality、
session resolver 與 terminal-data flags 都有 deterministic outcome。

### Phase 2.5 — Daily NEXT_BAR_OPEN execution

1. 實作 `ExecutionHorizon` 在 evaluation → aggregate decision → pending order → fill /
   cancel result 的不可變傳遞。
2. 保留 pending map 跨 session 的現有生命週期，但讓 `DAILY_NEXT_BAR` 明確只在下一
   resolved daily session fill；`INTRADAY_NEXT_BAR` 與 `SESSION_CLOSE` 不可被改成
   daily 行為。
3. 修正 `_evaluate_exit()`：only `SESSION_CLOSE` may fill at current session close；
   death-cross exit 必須 pending 到下一日 open。
4. 實作 real terminal-data finalization：不存在下一有效 bar 時寫
   `UNFILLED_END_OF_DATA`，含 horizon / origin / session evidence。

**Gate G2.5:** Day T close 的 golden ENTRY 和 death EXIT 都不會在 Day T close
fill；兩者在 Day T+1 resolved daily open 才 fill。最後一根、跨週末／休市、同日
多根 intraday、EOD exit 與 legacy v2 path 都有獨立 regression fixtures。

### Phase 3 — Strategy family and catalogue

1. 實作 golden-entry／death-exit definitions、evaluation evidence、execution horizon
   and registry bindings。
2. 加入 v1 engine reject set，並重用 application/worker capability preflight。
3. 讓 catalog persistence / API 回傳 immutable parameters, status and required
   capabilities。

**Gate G3:** 每一個 valid crossing transition 只產生一筆 SMA trigger evidence，
same-side observation 不產生 SMA trigger evidence。另獨立驗證 evidence 經 ANY /
ALL / AT_LEAST_N 與 priority 後的 aggregate decision / chosen horizon。daily strategy
never executes under v1 or a dataset without `KBAR_DAILY`.

### Phase 4 — Dashboard, documentation and qualification

1. 加入 strategy descriptions、EOD-exit selection warning 與 entry/exit/horizon result
   summary；保留 default selection。
2. README 記錄 CLI derivation、daily strategy timing、data qualification and no-live
   boundary。
3. 以 baseline/challenger runs 比較 current dataset；標示 CURRENT_SNAPSHOT /
survivorship issue 的限制，執行 OOS / walk-forward 前不得宣稱有效。

**Gate G4:** UI can select only compatible dataset strategies, all tests pass,
and the operation remains historical-data-only.

## 8. Test matrix

| Layer | Required cases |
|---|---|
| Dataset | direct daily / derived daily contract, parent digest lineage, RAW adjustment-policy propagation, resolved session date, OHLCV aggregation, no current unfinished session, duplicate/conflict/timezone/session rejection, old manifest digest unchanged |
| Decimal / digest | reject NaN/Infinity/binary-float daily source, canonical `103` = `103.0` = `103.00`, negative-zero, stable canonical JSON/SHA-256 and identical feature digest on replay |
| Features | SMA20/SMA60 hand-calculated windows, 19/20/59/60/61 warm-up, exact equality, cross-session retention by resolved session, bounded 60-close memory |
| Strategies | golden and death cross, equal previous MA, same-side no duplicate evidence, insufficient per symbol, position-only death exit |
| Engine | Day T close / Day T+1 open daily fill, no daily same-close exit, `DAILY_NEXT_BAR` cross-session persistence, `INTRADAY_NEXT_BAR` session regression, `SESSION_CLOSE` EOD regression, terminal pending finalization, legacy v2 no-change digest |
| Aggregation | isolate strategy trigger evidence from ANY/ALL/AT_LEAST_N decision behavior; priority deterministically selects and serializes horizon when multiple strategies trigger |
| Application | create-run and worker each reject missing `KBAR_DAILY`; v1 rejects both daily strategies; derived dataset is READY and selectable |
| Catalog / API | definition binding/digest consistency, parameters and capability exposure, no arbitrary parameter override |
| Dashboard | strategies default unchecked, missing capability disabled, selection warning appears only for MA + EOD pair, selected entry/exit/primary/horizon summary is visible, existing selections preserved |
| Safety | no Shioaji order API import/call, no CA activation, no live configuration added; Python compile, frontend script parse, `git diff --check`, full suite |

## 9. File map

| File | Change |
|---|---|
| `backtest/domain.py` | canonical Decimal functions, additive `HistoricalBar.session_date`, execution-horizon decision/order payloads |
| `backtest/session.py` | versioned Taiwan-equity session resolver and calendar/session-contract validation |
| `market_data/provider.py` | preserve qualified raw timestamp/numeric source representation before daily-domain canonicalization |
| `backtest/dataset.py` | daily / adjustment / session manifest metadata, derived/direct daily creation, capability and lineage validation |
| `backtest/application.py` | daily dataset derivation use case and existing preflight reuse |
| `scripts/derive_backtest_daily_dataset.py` | thin operational entry point for a sealed derived dataset |
| `backtest/indicators.py` | pure Decimal SMA helper and validation |
| `backtest/daily_features.py` | new bounded, cross-session daily feature state |
| `backtest/features.py` | no semantic change; retain session-local intraday contracts |
| `backtest/strategies.py` | two new experimental strategy classes, optional daily context fields, registry |
| `backtest/decision_aggregator.py` | primary-strategy horizon selection and aggregation audit fields |
| `backtest/engine.py` | daily state lifecycle, horizon-aware pending fills, v1 guard, true terminal-pending finalization |
| `strategy_catalog/service.py` | two new code-owned bindings |
| `dashboard/static/index.html` | daily strategy descriptions and MA/EOD selection warning only |
| `README.md` | operation, strategy semantics, data limits and research-only boundary |
| `tests/test_backtest_daily_sma_crossover.py` | daily dataset / feature / strategy / engine / service contracts |
| `tests/test_backtest_dashboard_ui.py` | default and warning regression |

No SQL migration is planned: the dataset manifest, strategy definition and run result
are existing JSON contracts. New manifest/bar fields must be optional and omitted from
legacy serialization; all new-manifest P0 policy fields must be canonicalized and
digest-covered. Never update sealed dataset files in place.

## 10. Rollout, rollback and Definition of Done

Rollout order: daily source qualification → dataset derivation → feature engine →
strategy registry → Dashboard visibility → research run. Each phase is additive.
Keep both family definitions `EXPERIMENTAL` and default-off until separately
qualified.

Rollback: stop presenting/selecting the two definitions and disable the derivation
command; do not delete derived datasets, historical runs or immutable evidence.
Existing v1/v2 runs remain readable and retry with their stored engine version.

Done means:

1. A sealed dataset can prove finalized daily-bar, resolved-session, RAW price-policy
   and lineage contracts.
2. SMA20／60 uses canonical Decimal inputs, is bounded, cross-session and deterministic.
3. Golden and death signals are distinct, evidence-rich, use `DAILY_NEXT_BAR`, and cannot reuse the
   intraday EMA contract.
4. Signal and fills obey completed-close / next-day-open timing; EOD close is exclusive
   to `SESSION_CLOSE`, and terminal pending orders have a defined outcome.
5. API and worker fail closed on incompatible data; UI shows both entry/exit context
   and stays default-safe.
6. Full regression, static checks and scope audit prove no broker/live order path
   was added.
