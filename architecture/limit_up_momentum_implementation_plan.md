# 漲停加速態勢（Limit-Up Momentum）Implementation Plan

- 狀態：Implementation Phase 5 已完成；G5 Replay Dashboard gate 通過，G0 live qualification 仍未通過
- 日期：2026-08-18（Asia/Taipei）
- 目標：偵測「正在進入漲停加速階段」，不是預測個股一定漲停
- 第一版執行邊界：Research／Replay／qualified realtime Shadow／Dashboard alert
- 明確排除：自動下單、真錢交易、繞過 RiskGate、將初始門檻宣稱為正式策略參數

## 1. 結論

這個功能應新增為獨立的 `MomentumSignalEngine`，不應塞進 BuyScore。既有 `CandidateEngine` 的輸出則是 discovery source 之一，必須放在 `CandidatePool`／訂閱之前；被訂閱後的 realtime features 才進 Momentum detector，避免形成「先收到行情才能成為 candidate、先成為 candidate 才能收到行情」的循環。

但不能只新增六個 `if`。目前程式只有一次性 Snapshot 與最新一筆 `StockData`，沒有 2 分鐘歷史、逐筆量、前高、外盤變化、五檔，也沒有可跨 Web refresh 保存的狀態。正確順序是：

```text
Scanner／AUTO／MANUAL／Position discovery
    ↓
CandidatePool 與訂閱容量契約
    ↓
Quote 與 Tick+BidAsk 的 provider qualification
    ↓
Quote／Tick／BidAsk 正規化與 recent stores
    ↓
FeatureEngine（同一個 as-of 時點）
    ↓
OpeningMomentum／LimitUpMomentum（可解釋的 hypothesis evidence score）
    ↓
MomentumStateMachine（episode、去抖動、失效）
    ↓
Shadow projection / Dashboard alert
    ↓
歷史事件研究 + 前瞻五檔蒐集
    ↓
參數 review 後才可升級為 validated config
```

第一版可以保留提案中的 `1.5% / 3% / 1.5x / 70` 與 15/20/15/20/20/10 權重，但設定名稱與畫面都必須標示 `hypothesis_v0`。Evidence Score 只是規則證據加總；在歷史研究完成前，它只是一個可重播、可觀察的 detector，不能被描述為已驗證的交易策略或漲停機率。

## 2. 現況與缺口

目前可沿用：

- `MarketDataStore`：每檔股票最新 Snapshot projection。
- `CandidateEngine`：回答「值不值得監控」。
- `BuyScoreEngine`：回答目前一般買入條件強不強，並保留 breakdown。
- `dashboard/service.py`：後端組好 projection，前端只負責呈現。
- `dashboard/static/index.html`：已有 Candidate 詳情與繁中 Dashboard，可增加 Momentum 區塊。
- 既有 execution plan 的 `MarketEvent`、Replay clock、DataHealth、bounded queue、Shadow 與 subscription-management 契約；若尚未實作，Momentum 階段只補共同需要的最小部分，不建立第二套 runtime。

目前不能直接支援：

- `StockData` 沒有 limit price、外盤量、五檔、event time／received time 或 sequence。
- `MarketDataStore` 只留最新值，且目前是 last-call-wins；不能算 rolling return，也不能拒絕舊資料。
- `ShioajiProvider` 目前用 Snapshot request，沒有 Tick／BidAsk subscription lifecycle。
- `run_scan()` 每次重建所有 in-memory state，Dashboard refresh 不能當 realtime detector clock。
- Dashboard 明確標示 `snapshot / streaming=False`，目前只有手動重新掃描。
- 歷史畫面會把當日資料聚合成 5 分 K，不能拿來驗證 1／2 分鐘訊號。
- 現有程式註解把成交量 threshold 寫成「股」，但 Shioaji 普通股 Tick／Snapshot volume 是「張／lot」。Momentum 相關模型必須使用顯式單位，不能沿用模糊的 `volume` 名稱。

目前回歸基線：`71 passed`。

## 3. Scope 與不變條件

### In scope

- 普通交易時段的 TWSE／TPEx 主板普通股。
- Tick、普通股五檔 BidAsk、current-session contract reference／limit price。
- Scanner／既有 AUTO Candidate／MANUAL／Position 來源、CandidatePool 與容量受限的 SubscriptionManager。
- 1 分鐘 recent bars、2 分鐘 rolling features、最近五檔 projection。
- Opening Momentum（09:00～09:10）、Breakout、Volume Acceleration、Momentum Acceleration、Limit-Up Momentum。
- 一個可解釋的 `SignalResult` 與一個 episode-based state machine。
- `EntryMode.NORMAL` 與 `EntryMode.MOMENTUM` 的 decision-support contract。
- Replay／Shadow、Dashboard 即時告警與完整 evidence。
- 一年期回溯研究與前瞻五檔資料蒐集。

### Out of scope

- Emerging Stock Board、無漲跌幅標的、新上市無漲跌幅期間、權證／ETF／ETN／債券。
- 盤中零股與整股成交量混算；v1 只使用普通交易整股事件。
- ML 漲停機率模型或「一定漲停」宣稱。
- 自動建立 Broker order、MOMENTUM 訊號直通下單、任何 live-money mode。
- 在 request callback 或瀏覽器內計算策略。
- 用 Snapshot／historical ticks／Kbars 輪詢假裝 realtime feed。

### 不變條件

1. Candidate、BuyScore、Momentum、Risk、EntryConfirmation 各自回答不同問題。
2. Momentum 訊號不會修改 BuyScore，也不會把 Candidate 自動視為可買。
3. 所有 entry presentation 都必須經 RiskGate；RiskGate 尚未實作或資料不健康時，只顯示訊號，不顯示 `ENTRY AVAILABLE`。
4. 缺資料、資料 stale、session metadata 不符、queue overflow 或 time ordering 不可信時，禁止產生新的 entry opportunity。
5. 所有 hypothesis config、feature schema、dataset manifest 與 signal result 都要有版本。

## 4. 目標架構

```text
                         Market Discovery
        Scanner / Existing CandidateEngine(AUTO) / MANUAL / Position
                                  │
                                  ↓
                     CandidatePool（rank / TTL / priority）
                                  │
                                  ↓
                        SubscriptionManager
                                  │
               Shioaji Quote Stream（通過 Phase 0 parity gate 後）
                  fallback：separate Tick + BidAsk streams
                                  │
                      normalize + bounded enqueue
                                  │
                     ordered consumer per symbol
                                  │
          ┌───────────────────────┼────────────────────────┐
          ↓                       ↓                        ↓
  MarketDataStore         IntradayBarStore          OrderBookStore
   latest snapshot        rolling 1m/history        latest five levels
          └───────────────────────┼────────────────────────┘
                                  ↓
                            FeatureEngine
                                  │
                ┌─────────────────┼──────────────────┐
                ↓                 ↓                  ↓
        BuyScoreEngine      SignalEngines      supporting evidence
                            ├ OpeningMomentum（09:00～09:10）
                            ├ Breakout
                            ├ VolumeAcceleration
                            └ LimitUpMomentum（rolling baseline ready）
                                  │
                         MomentumStateMachine
                                  │
                               RiskGate
                                  │
                 EntryConfirmation / DecisionProjection
                                  │
                         Dashboard / Alert only
```

`run_scan()` 保留給既有 CLI／Snapshot Dashboard，不在裡面啟動 streaming。新的 `IntradayMomentumRuntime` 由 FastAPI lifespan 或獨立 process 啟動一次；HTTP refresh 只能讀 local projection，不能影響行情訂閱節奏。

### 4.1 Candidate discovery 與 CandidatePool

新增 `MarketScannerCandidateSource`，但 Scanner 只負責低頻 discovery，不能拿它的 snapshot 欄位直接算 realtime Momentum feature。每筆 discovery 正規化為：

```python
@dataclass(frozen=True)
class CandidateDiscovery:
    symbol: str
    source: CandidateSource       # SCANNER / AUTO / MANUAL / POSITION
    rank_types: tuple[str, ...]
    best_rank: int | None
    discovered_at: datetime
    expires_at: datetime | None
    priority: int
    evidence: Mapping[str, object]
```

`MarketScannerCandidateSource` 以漲幅、成交量、成交金額、tick count 等已設定 rankings 的 union 建池，再做 symbol dedupe、普通股 eligibility 與 session metadata 檢查。Scanner 一次最多 200 筆，但這不是 subscription capacity，也不能保證每個當下正在加速的股票都會進榜。

CandidatePool／SubscriptionManager 規則：

- Position 與 active Momentum episode 不可被 eviction；MANUAL 預設 pinned；AUTO 與 Scanner 再依 priority／rank 分配。
- Scanner candidate 需有 TTL、grace period 與 admission／eviction hysteresis，避免排行榜小幅變動造成頻繁 unsubscribe/resubscribe。
- `subscription_ack_at` 成功後才算 coverage；只放入 CandidatePool 不算已監控。
- `usable_subscriptions = 200 - reserved_headroom`；`max_symbols = floor(usable_subscriptions / subscriptions_per_symbol)`。Phase 0 若證明單一 Quote 等價，`subscriptions_per_symbol=1`；fallback Tick+BidAsk 時為 2。
- Scanner cadence 使用可設定、可快取、可觀察的低頻值；在官方未提供 numeric Scanner request rate 且尚未實測前，不在 plan 先寫死秒數。
- 研究與 Dashboard 必須區分 `not_discovered`、`capacity_evicted`、`subscription_not_acked`、`data_incomplete`、`signal_false`，不能統稱 missed signal。

要保存每次 Scanner response／CandidatePool decision／subscription ack，才能做 prospective `Candidate/subscription recall @ -10m/-5m/-3m/-1m`。一年歷史 event study 若沒有當時的 Scanner 排名快照，只能先報告 oracle-universe detector quality；不得用收盤後榜單冒充歷史 discovery recall。

### 4.2 Quote subscription qualification

官方 `Quote` schema 已包含成交價、均價、累計量／額、`tick_type`、累計內外側統計與五檔 bid/ask；欄位面足以建立 `TickEvent` 與 `BidAskEvent` projections。但「欄位存在」不等於 event cadence、ordering、latency 與 derived result 等價。

Phase 0 要在交易時段選少量標的，同時訂閱單一 Quote 與 separate Tick+BidAsk，產生帶來源標籤的 capture，逐項比較：

- 累計成交量／成交額守恆、每次 delta 與最後值。
- trade update rate、source time → received time 的 p50／p95／p99、negative-latency/clock-skew count、最大 gap 與 reconnect 後連續性。若來源時鐘領先本機，數值只能作相對 parity，不得宣稱為 one-way network latency。
- best／five-level book 最新值 parity、staleness 與 empty-side 行為。
- 同一 Replay clock 下的 feature digest、signal/stage transition、alert 次數與 lead-time delta。

Parity pass criteria 必須在 capture 前 review 並凍結。只有 detector-required invariants 全部通過，Quote 才成為預設；否則保留 Tick+BidAsk fallback 並降低 active universe capacity。callback 仍只做 validate／normalize／enqueue。

## 5. 核心資料契約

### 5.1 InstrumentReference

每日登入後從 Shioaji contract metadata 建立：

```python
@dataclass(frozen=True)
class InstrumentReference:
    symbol: str
    exchange: str
    session_date: date
    reference_price: Decimal
    limit_up_price: Decimal | None
    limit_down_price: Decimal | None
    price_limit_applies: bool
    trading_unit_shares: int
    source_updated_at: date | None
```

規則：

- `distance_to_limit` 使用 current-session `limit_up_price`，不要用 `previous_close * 1.10` 自算。
- `session_date`、contract `update_date` 或 limit price 無法確認時，標的不得進 Limit-Up Momentum evaluation。
- `limit_up_price=None` 或 `price_limit_applies=False` 的標的明確排除。
- 測試仍應覆蓋 TWSE／TPEx tick-size 邊界，避免 adapter 取得錯誤資料時無聲通過。

### 5.2 Normalized TickEvent

```python
@dataclass(frozen=True)
class TickEvent:
    event_id: str
    symbol: str
    session_date: date
    event_time: datetime       # Asia/Taipei, source time
    received_at: datetime      # timezone-aware local receipt wall time
    ingress_sequence: int      # process-local ordering only
    price: Decimal
    tick_volume_lots: int
    total_volume_lots: int
    average_price: Decimal | None
    intraday_high: Decimal
    intraday_low: Decimal
    raw_tick_type: int
    aggressor_side: AggressorSide
    buy_aggressor_total_lots: int | None
    sell_aggressor_total_lots: int | None
    suspended: bool
    simulated_trade: bool
    intraday_odd: bool
```

Adapter 只做 validate、normalize、enqueue，不在 callback 計算特徵。

`raw_tick_type` 的內／外盤命名在官方不同頁面有不一致，Phase 0 必須用一個實際交易日的 labeled capture 對照成交價、當時 bid/ask 與來源畫面後，凍結 `AggressorSide` mapping。完成前 `external_ratio_status=UNVERIFIED`，不得計分。

### 5.3 Normalized BidAskEvent

```python
@dataclass(frozen=True)
class BidAskEvent:
    event_id: str
    symbol: str
    session_date: date
    event_time: datetime
    received_at: datetime
    bid_prices: tuple[Decimal, ...]
    bid_volume_lots: tuple[int, ...]
    ask_prices: tuple[Decimal, ...]
    ask_volume_lots: tuple[int, ...]
    suspended: bool
    simulated_trade: bool
    intraday_odd: bool
```

必須檢查 price／volume 長度一致、最多五檔、非負量、單側空簿、crossed book、stale age 與 session boundary。

### 5.4 Store responsibilities

| Store | 保存內容 | 重要規則 |
|---|---|---|
| `MarketDataStore` | 每 symbol 最新 `StockData` projection | 保持既有 consumer 相容；新 adapter 不把歷史塞進這裡 |
| `InstrumentReferenceStore` | 當日 reference／limit／market metadata | 每個交易日重新載入，不跨日沿用 |
| `IntradayBarStore` | Tick 建出的 1m bars + 最近原始 rolling volume buckets | 以 session 分區、有限 retention、拒絕舊 session |
| `OrderBookStore` | 每 symbol 最新五檔與來源時間 | 不用 HTTP 讀取動作刷新，不用舊 book 配新 tick |
| `MomentumProjectionStore` | 最新 feature、signal、episode、alert | Dashboard read-only，無 provider side effect |

第一版每檔保留至少 20 分鐘 recent data；研究／Replay 使用 immutable dataset，不以 in-memory retention 取代歷史保存。

### 5.5 Ordering、freshness 與 shutdown

- Tick 與 BidAsk 各自維持來源順序；不要假造兩個 stream 的 exchange-time 全序。
- Feature snapshot 以 Tick 的 `as_of` 為主，只可配對 `event_time <= as_of` 且 age 在允許範圍內的 BidAsk。
- duplicate event idempotent；舊事件不得覆蓋新 projection。
- `event_id` 優先使用來源提供的 stable identity。來源沒有 identity 時，live callback 使用 session/stream/ingress sequence 保證同 process 唯一；Replay 使用 dataset manifest hash + row index。不要把內容完全相同的兩筆合法成交誤判為 duplicate。
- 第一版同 symbol 由同一 consumer 處理；未來分區也要保證 symbol affinity。
- queue bounded；overflow 不是 silent drop，必須讓 DataHealth 進入 `BLOCKED`，停止新訊號／entry opportunity。
- shutdown 順序：停止訂閱 producer → drain queue → finalize bars/projections → flush research capture → 關閉 session。
- 新 session 清空 bars、state、external cumulative baseline 與 book；不得帶著昨日 stage 開盤。

## 6. FeatureEngine v0

`FeatureEngine.evaluate(current_tick, context)` 以已套用的當前 Tick 作為唯一 as-of 錨點，回傳 immutable、versioned `IntradayFeatureSnapshot`。`context` 明確攜帶 DataHealth、連續 Tick coverage 起點、aggressor mapping 驗證狀態與可選 Opening volume context；每個值都帶 `VALID / MISSING / STALE / UNVERIFIED` 狀態、來源 timestamp 與 event IDs。

### 6.1 精確公式

```text
price_above_vwap = price > vwap

previous_intraday_high =
    max(price/high strictly before current evaluation event)

breakout = price > previous_intraday_high

return_2m = price(as_of) / price_at_or_before(as_of - 2m) - 1

distance_to_limit = limit_up_price / price(as_of) - 1

volume_2m = sum(common-lot tick volume in (as_of - 2m, as_of])

baseline_2m = median(
    five non-overlapping complete 2m windows immediately before current window
)

volume_acceleration_2m = volume_2m / baseline_2m

external_ratio_session =
    buy_aggressor_total_lots /
    (buy_aggressor_total_lots + sell_aggressor_total_lots)

external_ratio_rising =
    external_ratio_session >= 0.60
    and external_ratio_session > external_ratio_session_at_or_before(as_of - 2m)

bid_depth_5 = sum(valid bid_volume_lots[:5])
ask_depth_5 = sum(valid ask_volume_lots[:5])
bid_ask_ratio_5 = bid_depth_5 / ask_depth_5
book_imbalance_5 = (bid_depth_5 - ask_depth_5) / (bid_depth_5 + ask_depth_5)
```

補充規則：

- `previous_intraday_high` 必須排除當前 Tick；若直接拿 Snapshot 的 current `high` 比，`price > high` 永遠不會成立。
- `price_at_or_before(t-2m)` 要有明確 tolerance；不能用 `t-1m59s` 的未來值補齊。
- `baseline_2m` 至少 4/5 個完整 window 且 DataHealth 無 gap 才有效。完整 baseline 未 ready 時不可假設加速度為 0；09:00～09:10 交給獨立 `OpeningMomentumSignal`，不改寫此公式。
- 同時保留 `volume_vs_previous_2m` 與上述 median baseline，供研究比較；v0 Evidence Score 只使用已凍結的一種定義。
- `external_ratio_session` 與 rolling `external_ratio_2m` 分開保存，不互相冒充。
- `ask_depth_5 == 0` 時 raw ratio 不設成 infinity；回傳 missing/reason，bounded imbalance 也要處理總深度為 0。
- 五檔容易受撤單影響，v0 先作 supporting evidence，不加入 100 分 Evidence Score；至少完成前瞻研究後才 review 是否加權。
- Decimal 用於 limit／price 邊界；Dashboard 才轉為顯示數字。

### 6.2 Feature completeness

`LIMIT_UP_MOMENTUM` 至少要求以下來源有效：

- current price／VWAP／prior high／2m price history
- current-session limit-up price
- current 2m volume 與 baseline windows
- realtime DataHealth healthy、非 suspend、非 simulated trade、非 intraday odd

外盤 ratio 與五檔若未驗證或 stale，可以明確顯示為 missing，但不能偽造；外盤少 10 分，五檔在 v0 不影響 Evidence Score。

### 6.3 Opening session feature contract

時間 routing 使用 exchange event time：`09:00:00 <= as_of < 09:10:00` 評估 `OpeningMomentumSignal`；`as_of >= 09:10:00` 僅在完整 rolling baseline ready 時評估 `LimitUpMomentumSignal`。09:10 不是把 missing volume acceleration 當 0 的捷徑。

Opening family 沿用 price above VWAP、strict-prior-high breakout、short-window return、distance to limit，以及 mapping 已驗證時的 external ratio；volume evidence 使用獨立、versioned `opening_volume_context`。Phase 0／research 只選定其中一種後凍結：

- 依過去交易日同 elapsed-time 累計量計算的 RVOL。
- 今日 opening cumulative volume／昨日總量比例。
- 今日 opening cumulative volume 相對歷史 opening profile 的 cumulative RVOL。

三種定義不可在 runtime 自動互相 fallback，也不可使用當日尚未發生的最終量。沒有有效 opening baseline 時，SignalResult 必須明確 `INSUFFICIENT_DATA`。Opening 與 post-warm-up 使用不同 config：`opening_momentum_hypothesis_v0`、`limit_up_momentum_hypothesis_v0`。

## 7. MomentumSignalEngine v0

### 7.1 Model

```python
class MomentumSignal(StrEnum):
    NONE = "NONE"
    OPENING_MOMENTUM = "OPENING_MOMENTUM"
    BREAKOUT = "BREAKOUT"
    VOLUME_ACCELERATION = "VOLUME_ACCELERATION"
    MOMENTUM_ACCELERATION = "MOMENTUM_ACCELERATION"
    LIMIT_UP_MOMENTUM = "LIMIT_UP_MOMENTUM"


@dataclass(frozen=True)
class SignalResult:
    symbol: str
    as_of: datetime
    config_version: str
    feature_version: str
    signal_family: str
    signal: MomentumSignal
    triggered_signals: tuple[MomentumSignal, ...]
    momentum_acceleration_confirmed: bool
    evidence_score: int
    evidence_max_score: int
    passed_rule_count: int
    total_rule_count: int
    coverage: float
    details: tuple[SignalDetail, ...]
    data_health: str
    evaluation_status: SignalEvaluationStatus
    block_reasons: tuple[str, ...]
```

`details` 必須保存 rule、實際值、threshold、是否通過、分數、來源時間與 missing reason，不能只回傳總分。

`momentum_acceleration_confirmed` 是給 downstream 的 family-neutral domain semantic：

```text
true when the active signal family has passed its versioned acceleration gate

opening_momentum_hypothesis_v0:
    signal == OPENING_MOMENTUM

limit_up_momentum_hypothesis_v0:
    signal == LIMIT_UP_MOMENTUM
```

StateMachine 只讀 `momentum_acceleration_confirmed` 與 breakout episode 狀態，不 import、switch 或列舉 `OPENING_MOMENTUM`／`LIMIT_UP_MOMENTUM`。具體 family → semantic mapping 由各 SignalEngine/config version 負責並保留在 result provenance。

Engine 由五個可單測 component 組成：

```text
BreakoutSignal
VolumeAccelerationSignal
MomentumAccelerationSignal = 2m return + volume acceleration
LimitUpMomentumSignal      = composite Evidence Score + regime/data guards
OpeningMomentumSignal      = 09:00～09:10 專用 opening-volume context + guards
```

因此畫面可以同時說明 breakout、volume acceleration 與 composite signal，但 state machine 仍只保留一個 current stage。

### 7.2 `hypothesis_v0` Evidence Score

| Evidence | 初始條件 | 分數 |
|---|---:|---:|
| Above VWAP | `price > vwap` | 15 |
| New intraday high | `price > previous_intraday_high` | 20 |
| 2m momentum | `return_2m >= 1.5%` | 15 |
| Within limit-up range | `distance_to_limit <= 3%` | 20 |
| Volume acceleration | `volume_acceleration_2m >= 1.5` | 20 |
| External ratio rising | `ratio >= 60%` 且高於 2 分鐘前 | 10 |

```text
signal = LIMIT_UP_MOMENTUM
when evidence_score >= 70
and price_above_vwap
and breakout
and all required feature inputs are valid
and DataHealth allows evaluation
```

`price_above_vwap` 與 `breakout` 是 v0 regime guards，避免單靠近漲停、量或外盤湊到 70 分卻沒有形成突破態勢；它們與其他門檻一樣需要在歷史研究中做 ablation，不是永久規則。

以上 threshold、weights、70 分 gate 全部放在 `MomentumHypothesisConfig(version="limit_up_momentum_hypothesis_v0")`，不得散落在 rules 或 JavaScript。Opening family 使用自己的 config 與 evidence definition。研究完成後新增版本，例如 `validated_v1`；不要覆寫舊版本，確保 Replay 可重現。

`evidence_score / evidence_max_score` 只表示這個 version 的規則成立程度，不是碰漲停機率。即使未來觀察到各 score bin 的 event rate，也必須先經 calibration 與 holdout 驗證，才能另外發布 probability 欄位；不可把 Evidence Score 改名成 probability。

## 8. Momentum state machine

### 8.1 公開 stage

```text
WATCH → STRONG → BREAKOUT → ACCELERATING → NEAR_LIMIT_UP → LIMIT_TOUCHED
```

建議 v0 語意：

| Stage | 條件 |
|---|---|
| `WATCH` | 已在 active universe，暖機／等待特徵 |
| `STRONG` | price above VWAP，且必要資料健康 |
| `BREAKOUT` | `STRONG` + breakout confirmed |
| `ACCELERATING` | active breakout episode + current result 的 `momentum_acceleration_confirmed=true` |
| `NEAR_LIMIT_UP` | 已 accelerating 且 `distance_to_limit <= 1%`（暫定） |
| `LIMIT_TOUCHED` | price 等於 contract limit-up，或來源 change type 明確為 limit-up |

`distance <= 3%` 是 Evidence Score rule；`NEAR_LIMIT_UP <= 1%` 是 state threshold。兩者分開，才符合「278 是 ACCELERATING、約 282 才 NEAR_LIMIT_UP」的時間線。這兩個值仍是 hypothesis，Phase 0 review 後凍結。

### 8.2 Episode lifecycle

Episode 不使用一個會被覆寫的 `config_version`，而是保存建立來源、目前來源與不可變 history：

```python
@dataclass(frozen=True)
class StageTransition:
    occurred_at: datetime
    from_stage: MomentumStage
    to_stage: MomentumStage
    signal_family: SignalFamily
    config_version: str
    evidence_snapshot_id: str


@dataclass(frozen=True)
class EvidenceUpdate:
    occurred_at: datetime
    signal_family: SignalFamily
    config_version: str
    evidence_snapshot_id: str
    momentum_acceleration_confirmed: bool


@dataclass(frozen=True)
class MomentumEpisode:
    episode_id: str
    created_by_signal_family: SignalFamily
    created_by_config_version: str
    current_signal_family: SignalFamily
    current_config_version: str
    highest_stage: MomentumStage
    transitions: tuple[StageTransition, ...]
    evidence_updates: tuple[EvidenceUpdate, ...]
```

- 每次由 WATCH／STRONG 形成 breakout 時建立 `episode_id`，另保存 breakout level、first seen 與 peak price；created fields 之後不可變。
- 每次 family/config handoff 更新 current fields 並 append `EvidenceUpdate`；每次 stage 上升 append `StageTransition`，兩者都要帶當下 family/config 與 evidence snapshot id。
- 同一 episode 的 `highest_stage` 只向上，不因一個 Tick 抖動反覆通知。
- 若跌回 breakout level 下方、跌破 VWAP、2m momentum 轉負、資料 stale 或超過 episode TTL，將 episode 關閉為 `INVALIDATED / EXPIRED / DATA_BLOCKED`，不把歷史改寫成從未發生。
- invalidation 後進 cooldown；只有重新突破且滿足 reset 條件才建立新 episode。
- `LIMIT_TOUCHED` 保存第一次碰板的 `limit_touched_at`，此歷史事實不因後續開板而倒退。
- Episode 另存 `limit_locked: bool | None`、`limit_lock_evidence_as_of`、`limit_locked_at`、`limit_unlocked_at`。`None` 表示五檔 stale／缺失／尚未驗證，不能誤顯示成已開板。
- v0 lock policy 建議要求：last trade 在 limit-up、best bid 在 limit-up、且沒有可成交 ask／ask side empty，連續滿足 versioned confirmation duration。精確秒數與 empty-book semantics 必須在 Phase 0 capture 後凍結。
- lock state 可以由 true 變 false 並記 `limit_unlocked_at`；stage 仍保留 `LIMIT_TOUCHED`。Dashboard 分別顯示「碰觸漲停」「鎖住」「已打開」「資料不足」。
- Opening → post-warm-up 的 09:10 handoff 保留同一 `episode_id`、breakout level 與最高 stage；更新 `current_signal_family/current_config_version` 並 append `EvidenceUpdate`，不得改寫 created fields、偽造 stage transition 或重複告警。
- transition 必須有 hysteresis／minimum confirmation（以 Tick 數或秒數定義），避免臨界值附近 chatter；參數同樣版本化。

### 8.3 Alert deduplication

告警 identity：

```text
(session_date, symbol, episode_id, event_type, stage_or_lock_transition)
```

- 僅在 stage 上升時立即通知。
- `config_version` 保存於 alert payload／audit metadata，不放入 dedup identity；09:10 family/config handoff 不可藉版本變更重送相同 stage。
- 同 stage 的 Evidence Score／price 更新只更新卡片，不重複彈窗。
- DataHealth blocked、episode invalidated、limit touched、limit locked、limit unlocked 可發不同 event type。
- Browser reload 只讀 projection，不重播已 acknowledge 的 alert。

## 9. EntryMode 與 Risk 邊界

```python
class EntryMode(StrEnum):
    NORMAL = "NORMAL"
    MOMENTUM = "MOMENTUM"
```

### NORMAL

- 等待突破點／VWAP 回踩與再次確認。
- 較低追價與滑價風險，但可能錯過直攻漲停。

### MOMENTUM

- 需要 active acceleration episode（current/highest stage 至少 `ACCELERATING`）且 current family 在 `MomentumEntryPolicyConfig.enabled_signal_families`。
- RiskGate 仍需檢查資料健康、spread／book freshness、position/cash limits、單股曝險、重複 entry、停損／失效價與交易狀態。
- 使用獨立且較小的 position-size cap；實際倍數不是 Momentum engine 的責任。
- `invalidation_price` 應來自 breakout level／VWAP／risk policy，不在 Dashboard 寫死。

```python
@dataclass(frozen=True)
class MomentumEntryPolicyConfig:
    version: str
    enabled_signal_families: frozenset[SignalFamily]


momentum_entry_hypothesis_v0 = MomentumEntryPolicyConfig(
    version="momentum_entry_hypothesis_v0",
    enabled_signal_families=frozenset({
        SignalFamily.OPENING_MOMENTUM,
        SignalFamily.LIMIT_UP_MOMENTUM,
    }),
)
```

Entry Policy 讀的是 episode semantic + policy allowlist，不依賴具體 SignalEngine class。若未來要禁止 Opening entry，只調整 versioned policy 並顯示明確 policy reason；不能靠 hard-coded signal name 或時段副作用達成。即使 family 被允許，RiskGate 非 PASS 仍只能是 `WAITING/BLOCKED`。

建議輸出：

```python
@dataclass(frozen=True)
class EntryOpportunity:
    mode: EntryMode
    status: Literal["WAITING", "AVAILABLE", "BLOCKED"]
    signal_id: str
    risk_decision_id: str | None
    risk_level: Literal["HIGH", "VERY_HIGH"]
    position_size_cap: Decimal | None
    invalidation_price: Decimal | None
    reasons: tuple[str, ...]
```

目前 repository 沒有可用的 RiskGate。因此前幾個 phase 只能顯示：

```text
正在進入漲停加速階段
Momentum Entry 候選（高風險）
RiskGate 尚未完成，不能標示為 AVAILABLE
```

待 execution-layer RiskGate 可用後，才允許顯示 `MOMENTUM ENTRY AVAILABLE`。即使未來接策略自動下單，Signal 也只能產生 evidence／intent，不能直接呼叫 Broker。

## 10. Dashboard 與 API

### 10.1 Backend projection

新增 local-read endpoints：

```text
GET /api/dashboard/momentum
GET /api/dashboard/momentum/{symbol}
GET /api/dashboard/momentum/events       # SSE，僅讀 local events
```

回傳欄位至少包含：

- symbol／name／as_of／data age
- current price／VWAP／limit-up price／distance
- current stage／highest stage／episode id／first seen
- episode created-by family/config、current family/config、最近 transitions/evidence updates
- evidence score／max、passed／total rule count、signal family／config version／coverage
- 六項 evidence breakdown 與五檔 supporting evidence
- signal／block reasons／DataHealth
- entry mode suggestion 與 Risk status（若存在）
- limit touched time／`limit_locked`／lock evidence time／limit-unlocked 狀態
- alert acknowledgement／invalidation 狀態

SSE 只傳 projection event，不啟動 Provider、不查 account、不做策略運算。若第一小步先用 1 秒 polling local projection，也要保留相同 response contract，且不能把 polling 傳到 Shioaji。

### 10.2 UI

在既有繁中 Dashboard 增加：

1. Top bar「漲停加速」狀態與 active alert 數。
2. Candidate list 的 stage badge：觀察／強勢／突破／加速／近漲停／碰觸漲停，另顯示鎖住／已打開／資料不足。
3. Candidate detail 的 Momentum 區塊：Evidence Score、成立規則數、完整 evidence、資料 freshness、signal family 與 hypothesis badge。
4. 可關閉但不重複跳出的警示卡：

```text
🚨 8039 台虹：強勢突破加速
目前 278｜漲停 284.5｜距離 2.34%
突破 275 前高 + 2 分鐘動能 + 外盤增加
Evidence Score 100 / 100（limit_up_momentum_hypothesis_v0）
代表 6/6 條 evidence 成立，不代表 100% 會漲停
高風險；RiskGate 未通過前不代表可買
```

5. 狀態時間線與失效原因，讓使用者看到 WATCH 到目前 stage 的演進。

前端不可自行重算 Evidence Score、limit price 或 state；所有文字與數值來自 backend projection。

## 11. 8039 台虹 golden testcase

### 11.1 截圖可直接確認的輸入

| Field | 09:16 | 09:18 |
|---|---:|---:|
| Price | 272 | 278 |
| VWAP | 269.59 | 270.76 |
| Observed intraday high | 275 | 278 |
| Cumulative volume | 8,806 lots | 11,112 lots |
| External ratio | 56.15% | 62.27% |
| Limit-up price | 284.5 | 284.5 |

可直接推出：

- `return_2m = 2.2059%`
- `previous_intraday_high = 275`，09:18 的 278 為 breakout
- `distance_to_limit = 2.3381%`
- 2 分鐘成交 2,306 lots
- external ratio 上升 6.12 percentage points

不能直接推出：`volume_acceleration >= 1.5`，因為沒有前五個 2 分鐘 baseline windows。

### 11.2 兩個 fixture，不混淆事實與補值

`test_8039_screenshot_only_is_incomplete`：

- 只放截圖可確認資料。
- above VWAP／breakout／2m return／within 3%／external rising 為 true。
- known Evidence Score 是 80；volume acceleration 狀態為 missing。
- 因 required rolling-volume history 不完整，SignalResult 必須標示 `INSUFFICIENT_DATA`，不能假裝得到 85 或 100。

`test_8039_enriched_replay_emits_limit_up_momentum`：

- 額外放入明確標為 synthetic 的前五個完整 2m volume windows，例如 median baseline 1,400 lots。
- `2,306 / 1,400 = 1.6471`，volume acceleration 為 true。
- 六項全中時，依目前權重的 Evidence Score 是 `100 / 100`，不是 85，也不是 100% 機率。
- expected：Candidate fixture 已在 active universe、breakout true、momentum acceleration true、`within_3pct_of_limit=true`、signal `LIMIT_UP_MOMENTUM`、stage `ACCELERATING`。
- 若 review 決定把 `NEAR_LIMIT_UP` 定義為 3%，才把 stage expected 改成 `NEAR_LIMIT_UP`；同一 config version 不能同時採兩種定義。

Candidate 預期要在 fixture 明確給定（例如 replay watchlist）；現有畫面沒有足夠的開盤 gap／Candidate rule 證據，不能倒推「今天一定由 CandidateEngine 選中」。研究報告另計算 subscription/Candidate recall，避免 detector 只對已知成功案例有效。

### 11.3 其他必要測試

- threshold 邊界：`1.4999% / 1.5%`、`3.0001% / 3%`、`1.499x / 1.5x`、Evidence Score `69 / 70`。
- prior-high 必須排除 current Tick。
- duplicate／out-of-order Tick 不重複加 volume 或產生第二個 alert。
- 09:00 session reset、午盤前 stale、suspend、simulated trade、odd lot 排除。
- baseline 為 0、ask depth 為 0、空五檔、crossed book。
- BidAsk 比 Tick 舊、兩個 stream 同 timestamp 不同 arrival order。
- breakout 後失效、cooldown、重新建立新 episode、limit-up 後打開。
- `LIMIT_TOUCHED` 後 lock true／false／unknown、解鎖時間、book stale 時不誤判 unlocked。
- 09:03、09:09:59 的 Opening fixture；09:10 family handoff 不換 episode、不重複 alert。
- Opening confirmation 可直接把 active breakout episode 推進 `ACCELERATING`；StateMachine 不列舉 signal family。
- Momentum Entry policy 對 supported／unsupported family、RiskGate PASS／BLOCKED 做組合測試。
- Episode created/current provenance、StageTransition、EvidenceUpdate 在 09:10 handoff 後可完整 Replay。
- Opening baseline missing、opening volume context 無 look-ahead、不同 opening baseline 定義不可偷偷 fallback。
- 同一 replay 連跑 10 次，feature／signal／transition／alert digest 一致。
- Dashboard reconnect 不重放 notification，前端不重算 score。

## 12. 一年期歷史驗證設計

### 12.1 研究問題

Detector 的主要問題不是「漲停股之前有沒有上漲」，而是：

> 在所有當時可觀察、可訂閱的股票中，這個 signal 能多早發現後續 1／3／5／10 分鐘碰到漲停的事件，同時每天造成多少錯誤告警？

### 12.2 資料層

1. `instrument_session`：symbol、market、date、reference、limit-up、eligible／exclusion reason。
2. 全 eligible universe 的 1m OHLCV／amount，建立 first-limit-up minute 與價格／量 features。
3. Positive event 與 matched controls 的 historical Ticks，重建精確 return、aggressor volume、VWAP 與 first-hit time。
4. Candidate／subscription decision log，確認 signal 發生前是否真的已進 active universe。
5. 五檔歷史目前不在 Shioaji historical response；另外跑 qualified realtime Shadow 保存 BidAsk，至少累積 20～30 個交易日後單獨評估。
6. Scanner response、CandidatePool decision、subscribe request／ack 需要 prospective archive；沒有這些歷史快照時，retro study 分開報 oracle-universe detector quality，不宣稱 discovery recall。

所有原始與 normalized artifact immutable，保存 source、SDK version、query parameters、timezone、schema version、row count、min/max timestamp 與 SHA256 manifest。空 response／流量限制／缺日要 fail closed，不當成「當天沒交易」。

### 12.3 Label

每個 evaluation time 建立：

```text
hit_limit_within_1m
hit_limit_within_3m
hit_limit_within_5m
hit_limit_within_10m
first_limit_up_at
held_limit_for_1m / 3m / 5m
limit_unlocked_after_hit
max_favorable_excursion_10m
max_adverse_excursion_10m
```

只看「9:00～10:00 最終漲停股」會有 selection bias。Negative/control 至少包含：

- 同日、同市場、相近價格與流動性的未漲停股。
- 有 breakout／高 Evidence Score 但 10 分鐘內未碰漲停的股票。
- 碰到 3% 距離區但反轉的 false-near-limit 案例。
- 曾漲停但 signal 太晚、或 Candidate 根本未訂閱的 missed cases。

### 12.4 Split 與防 leakage

- 使用 chronological walk-forward；最後 20% 日期完全 holdout，不用來選 threshold。
- `previous_intraday_high` 只使用 evaluation time 之前資料。
- 1m bar 只在完成後可見；若以 Tick 做 intrabar detector，Replay 也必須逐 Tick，不可偷看該分鐘 high／close／volume。
- limit-up label、當日最終 high、未來成交量不可回填到當下 feature。
- 同一 stock-day 不可拆到不同 train/test fold。
- 參數搜尋、缺值政策、alert cooldown 與 Candidate universe policy 都視為 strategy version 的一部分。

### 12.5 指標

- event recall：早盤 limit-up events 中，在碰板前 1／3／5／10 分鐘已 alert 的比例。
- alert precision：alert 後 1／3／5／10 分鐘內碰板比例。
- median／p10 lead time。
- false alerts per day、per 100 subscribed stock-hours。
- Candidate/subscription recall：成功事件在 alert window 前 `-10m/-5m/-3m/-1m` 已被發現、admit 且 subscribe ack 的比例。
- missed-reason funnel：not discovered／capacity evicted／subscription not acked／data incomplete／signal false。
- Evidence Score bins 的 observed event rate 與各 evidence 的 ablation；未完成 calibration 前不稱 probability calibration。
- Opening 與 post-warm-up 分層的 recall／precision／lead time／false alerts。
- false breakout 後的 MAE、limit locked rate、limit unlocked rate、alert episode duration。
- DataHealth coverage、missing external ratio／book ratio、queue drop（必須為 0）。

Threshold promotion 需先登記可接受 gate，例如最低 recall、最大 daily false alerts 與最短 lead time，再用 validation set 選參數；不能看完 holdout 才決定成功標準。初始 70 分不保證是最佳門檻。

## 13. Implementation phases

### Phase 0 — Contract freeze 與 provider qualification

工作：

1. review 並凍結外盤 raw mapping、volume unit、普通股 eligible universe、`NEAR_LIMIT_UP` threshold、required-feature policy 與 `LIMIT_TOUCHED` lock evidence policy。
2. 用 current SDK fixture 驗證 contract `reference/limit_up/update_date`、Tick、BidAsk、Quote、odd-lot flags 與 timestamp。
3. 在少量標的同時 capture Quote 與 Tick+BidAsk，先凍結 parity criteria，再比較 volume conservation、book staleness、event cadence／lag／gap、reconnect 與 feature/signal/alert digest。
4. 定義 Scanner rankings、union/dedupe、TTL、priority、eligibility、可設定 cadence 與 response archive；不先發明官方未公布的 request-rate 數字。
5. 選定一種 `opening_volume_context`，凍結 09:00～09:10／09:10 交界、missing 與 no-look-ahead semantics。
6. 將 `opening_momentum_hypothesis_v0`、`limit_up_momentum_hypothesis_v0`、`momentum_entry_hypothesis_v0`、feature、family-neutral acceleration semantic、signal、episode provenance 與 discovery schemas 寫成 versioned models。

Gate G0：provider capture 可重播、Quote parity 結論與 fallback 明確、Scanner／Opening／lock contracts 及 8039 fixtures review 完成，才寫 engine。Parity 不通過不擋後續 Replay，但 runtime 固定用 Tick+BidAsk fallback。

2026-08-18 implementation checkpoint：

- 已完成 family-neutral acceleration、Entry enabled-family policy、Episode created/current/transition provenance、normalized Tick/BidAsk/InstrumentReference 與 fail-closed parity report contracts。
- 8039 的 20 秒 capture 因鎖板期間無 callback，只能證明 subscribe/unsubscribe/session cleanup；不得用來判定 parity。
- 2330 的 20 秒 capture 有 Quote 62／Tick 3／BidAsk 47 callbacks，trade terminal fields 與 latest book 一致，但 Quote book-change count 與 BidAsk event count 不同；目前只是一份短樣本。
- G0 仍開放：production pass criteria、長樣本／多 symbol、reconnect、derived feature/signal/stage/alert digests、來源時鐘校準、raw tick-side mapping、Scanner cadence/headroom、Opening volume context 與 lock confirmation duration。
- 在 G0 關閉前，既有 runtime 保持 Tick+BidAsk，不切換 Quote mode，也不開始 SignalEngine。

### Phase 1 — Discovery 與 subscription allocator

工作：

1. 實作 `MarketScannerCandidateSource`、existing AUTO Candidate adapter、MANUAL／POSITION sources 與 `CandidatePool`。
2. 實作 rank union、dedupe、TTL／grace／hysteresis、pinned/active episode 保護及 deterministic eviction。
3. 實作 `SubscriptionManager` capacity formula、reserved headroom、request／ack state 與 Quote／Tick+BidAsk mode。
4. 保存 Scanner response、pool decision、subscribe request／ack／unsubscribe reason；加入 discovery/admission/coverage metrics。
5. 用超額 candidate、榜單抖動、ack timeout、disconnect/reconnect、active episode 不可 eviction 等 fixtures 測試。

Gate G1：在固定輸入下 subscription set／eviction digest 一致；永遠不超過 `200 - headroom`；只有 acked symbols 計入 coverage；miss reason 可分類。

2026-08-18 implementation checkpoint：

- 已實作 Scanner rank union 與 defensive Shioaji 1.7.2 adapter；Scanner response 保留 source time、row evidence 與 deterministic digest，且尚未配置 runtime polling cadence。
- 已實作 AUTO／MANUAL／POSITION adapters，以及 CandidatePool 的 source dedupe、Scanner repeated-observation admission、TTL、grace、pinned／active-episode protection、withdraw 與 deterministic decision digest。
- 已實作 explicit-policy SubscriptionManager。Quote 或 Tick+BidAsk mode、reserved headroom、ack timeout、retry backoff 與 minimum dwell 都必須由呼叫端明確提供；`SUBSCRIPTION_CAPACITY_PHASE0` 仍然 fail closed。
- subscribe request、ack、timeout、failure、unsubscribe、disconnect 與 retry 都有 append-only audit event；Scanner response、pool decision 與 subscription decision 目前由 long-lived runtime 接手前先保存在 process-local immutable logs，尚未宣稱為跨重啟 prospective archive。
- 只有 `ACKED` 計入 coverage；ack timeout／unsubscribe failure 在 provider 狀態未釐清前仍占容量，replacement 必須等 unsubscribe ack，因此不會短暫超額。
- fixed-input Gate G1 已由 23 個 focused tests 通過，整個 repository 130 tests 通過。G0 的 live Quote promotion、Scanner cadence/headroom 選值與其他實證 gate 仍維持開放，沒有啟動 live subscription runtime。

### Phase 2 — Deterministic recent-data foundation

工作：

1. 實作／沿用 MarketEvent metadata、DataHealth 與 deterministic Replay clock。
2. 新增 `InstrumentReferenceStore`、`IntradayBarStore`、`OrderBookStore`。
3. Tick 建 1m bar；處理 duplicate、out-of-order、session reset、zero/missing data。
4. 建立 synthetic replay fixtures 與 immutable dataset loader。
5. 保持現有 `MarketDataStore`／`run_scan()`／Dashboard snapshot 相容。

Gate G2：同 dataset 10 次 digest 一致；舊／重複資料不改變 volume；既有 regression 全過。

2026-08-18 implementation checkpoint：

- 已擴充 framework-free canonical `EventEnvelope`、stream kind、watermark、typed projection／ingestion result；Envelope 會驗證 payload 的 identity、session、source、symbol、time 與 sequence 一致。
- 已實作 `InstrumentReferenceStore`、`IntradayBarStore` 與 `OrderBookStore`。全部以 session 分區、至少保留 20 分鐘 recent history，支援 deterministic digest／finalize，且沒有修改既有 `MarketDataStore`、`run_scan()` 或 Dashboard snapshot path。
- Tick 以 unique event ID 累積 common-lot volume；同內容但不同 ID 的合法成交仍各自成立。cumulative delta 小於 tick volume 會拒絕，大於 tick volume 會保留已觀察 tick 但將 DataHealth 設為 `BLOCKED`，不以累計差額補造 rolling volume。
- Tick 與 BidAsk 分別維護 `(event_time, ingress_sequence)` watermark；OrderBook 保留 bounded history，Feature 階段只能取 `event_time <= as_of` 且通過 freshness 的 book。
- 已實作 DataHealth、lock-protected bounded queue 與 canonical ingestor。duplicate、out-of-order、session id/date mismatch、missing reference、crossed book、gap、source clock skew 與 overflow 都有 typed result／counter／reason；`BLOCKED` 只可由新 reconnect epoch + verified resync recovery。
- 已實作不讀 wall clock／network 的 `ReplayClock`、manifest SHA-256 loader 與 Replay runner。Replay event identity 使用 manifest hash + row index，received-order、timezone、reference、row count 與 content hash 在 dispatch 前驗證。
- synthetic 8039 fixture 保存 09:16～09:18 的 272→278、8,806→11,112 與五檔例子，但仍沒有補造 volume baseline 或 signal。相同 dataset 連跑 10 次 digest 一致。
- Gate G2 由 36 個 focused tests 與 165 個 repository tests 通過；新 Phase 2 核心模組 focused coverage 約 92%。沒有啟動 live subscription、SignalEngine、Dashboard alert、Broker 或 order path，G0 仍開放。

### Phase 3 — FeatureEngine + MomentumSignalEngine

工作：

1. 實作 as-of feature snapshot 與完整 validity metadata。
2. 實作 Opening 與 post-warm-up time router、兩組 versioned configs、Evidence Score breakdown 與 family-neutral `momentum_acceleration_confirmed`。
3. 加入 screenshot-only 與 enriched 8039 fixtures。
4. 加入 09:03／09:09:59／09:10 handoff、threshold、missing/stale、zero denominator、unit/property tests。

Gate G3：公式與 golden results 固定；missing baseline 不會產生完整 signal；六項全中 Evidence Score 為 100；Opening 不偷看未來量；兩個 family 都能輸出相同 acceleration semantic。

2026-08-18 implementation checkpoint：

- 已實作 immutable `FeatureValue`／`IntradayFeatureSnapshot` 與 as-of `FeatureEngine`。strict-prior high 排除目前 Tick；2 分鐘價格只取 target 或更早且在 30 秒 tolerance 內的 Tick；rolling volume 使用 `(start, end]`，並要求明確 continuous Tick coverage 起點與 healthy/no-gap DataHealth。
- `baseline_2m` 固定為目前 rolling window 前五個不重疊 2 分鐘 window 的 median，至少 4/5 完整才有效。零 baseline、缺 coverage、DataHealth gap／blocked 都回傳 missing/block reason，不轉成 0、infinity 或補造 volume。
- 外盤累積 ratio 與兩分鐘前 ratio 分開保存；mapping 未經 labeled capture 驗證時為 `UNVERIFIED` 且不計 10 分。五檔只取 `event_time <= current_tick.event_time` 且預設 5 秒 freshness 的 book；ask depth 為 0 時 raw ratio missing，但總深度非零時 bounded imbalance 仍可計算。
- 已實作 `OpeningMomentumSignal`、`LimitUpMomentumSignal` 與 event-time router。`09:00:00 <= t < 09:10:00` 走 Opening；`t >= 09:10:00` 走完整 rolling family。兩者都輸出 family-neutral `momentum_acceleration_confirmed`，並新增 `TRIGGERED / NOT_TRIGGERED / INSUFFICIENT_DATA / OUTSIDE_WINDOW` evaluation status 與 deterministic result digest。
- Opening baseline 模式仍未由 G0 選定，因此預設 `opening_momentum_hypothesis_v0` 繼續 fail closed；測試只在明確注入 `HISTORICAL_ELAPSED_TIME_RVOL` research context 時證明 09:03／09:09:59 可確認 acceleration，且 future source timestamp 會被拒絕。
- screenshot-only 8039 Replay 在 09:18 得到 known Evidence Score `80/100`、`BREAKOUT` component 與 `INSUFFICIENT_DATA`，原因是 0/5 baseline windows；enriched synthetic Replay 明確提供 1,400-lot median baseline，得到 `2306/1400 = 1.647142857...`、六項全中 `100/100` 與一次 `LIMIT_UP_MOMENTUM`。
- 新增只讀 `scripts/replay_momentum_signal.py`，可列出每筆 Replay 的 signal family、evaluation status、Evidence Score、details、block reasons 與 digest；它不連 live provider、Dashboard、RiskGate、Broker 或 order path。
- Gate G3 由 32 個 focused tests 通過，Phase 3 新核心 focused coverage 88%；共享 worktree 最新完整 regression 為 207 passed、1 skipped。StateMachine／Projection／Entry、Dashboard alert 與 realtime Shadow 尚未實作，G0 仍開放。

### Phase 4 — State machine、projection、entry contract

工作：

1. 實作 episode id、created/current family+config、transition/evidence-update provenance、highest-stage watermark、invalidation、cooldown、`LIMIT_TOUCHED` 與 lock/unlock evidence。
2. 實作 alert deduplication 與 `MomentumProjectionStore`。
3. 新增 `EntryMode`／`EntryOpportunity`／`MomentumEntryPolicyConfig` contract；RiskGate 不存在時固定 `BLOCKED`。
4. 用 Replay 驗證 8039、Opening→post-warm-up handoff、limit touched→locked→unlocked 與 false-breakout timelines。

Gate G4：Opening 可在 09:10 前推進 `ACCELERATING`；handoff 保留 episode 與 created provenance、不偽造 transition、不重複 alert；lock unknown 不顯示已開板；沒有 supported family + RiskDecision PASS 就沒有 AVAILABLE。

2026-08-18 implementation checkpoint：

- 已實作 family-neutral `MomentumStateMachine`。它只讀 `momentum_acceleration_confirmed`，不依 Opening／Limit-Up 具體 family 決定是否加速；family/config 僅作建立、目前與 transition/evidence provenance。
- Episode 保存 deterministic id、breakout level、peak、last progress、最高 stage、closure/cooldown、touch/lock/unlock 與完整 digest。09:10 handoff 保留同一 episode，不偽造 transition。
- TTL 依「最後一次新高或 stage 進展」計算，不以 created-at 硬切仍在推進的走勢。只有 `INVALIDATED` 套用 cooldown；`EXPIRED`／`DATA_BLOCKED` 恢復健康後可立即重新評估。
- 已實作 in-memory `MomentumProjectionStore`。告警 identity 不含 config version；一次 evaluation 即使同時跨 BREAKOUT／ACCELERATING，也只通知最後可告警 stage。同 stage update、Replay duplicate 與 09:10 handoff不重複通知。
- `LIMIT_TOUCHED` 與 lock condition 分離。預設 lock duration 仍未由 G0 凍結，因此保持 unknown；只有測試明確注入 duration 時才可產生 locked/unlocked transition。
- 已實作 `EntryOpportunity`。`AVAILABLE` 同時要求 active acceleration episode、policy 支援目前 family、RiskGate PASS 與可稽核 risk decision id；Replay 因 RiskGate 未整合固定顯示 `BLOCKED`，不產生 order。
- 只讀 Replay CLI 現在會輸出 signal、episode state/provenance、alerts、Entry block reason 與 deterministic projection digest。8039 完整 enriched timeline 在 09:18 保留由 Opening 建立的同一 episode，current family 為 Limit-Up、stage 為 `ACCELERATING`。
- Gate G4 由 35 個 focused tests 通過，核心 state/projection/model/config coverage 為 90%；共享 worktree 完整 regression 為 250 passed、1 skipped。沒有接 Dashboard、live Shadow、Broker 或 order path，G0 仍開放。

### Phase 5 — Dashboard（先接 Replay／Mock projection）

工作：

1. 新增 local projection API 與 SSE／polling contract。
2. 新增繁中警示卡、stage badge、Evidence Score／非機率 disclaimer、lock/unlock、timeline、data-health 與 hypothesis 標示。
3. 確認 browser refresh 不會呼叫 provider，不在前端重算 score。
4. 做窄螢幕、keyboard、screen-reader live-region 與 reconnect tests。

Gate G5：使用 8039 replay 可在 state transition 後一個 UI refresh interval 內顯示一次告警；重連不重播；畫面不出現 Momentum probability 或含糊的 `LIMIT_UP` stage。

2026-08-18 implementation checkpoint：

- 已新增獨立的 `MomentumDashboardService`，由 immutable enriched 8039 Replay 建立長存於 process 內的 `MomentumProjectionStore`。API refresh 只讀本機 projection，不會建立 runtime composition、呼叫 Provider／Scanner、連 Broker 或送出委託。
- 新增 `GET /api/dashboard/momentum`、單一 symbol projection 與 alert acknowledgement API。來源回傳 dataset id、schema、content SHA-256、session、as-of、`is_live=false` 與 projection digest；acknowledgement 在同一 server process 內可跨 browser reload 保存且 idempotent。
- 既有繁中 Dashboard 已增加獨立的「漲停加速態勢」區塊，顯示 8039 台虹的 `ACCELERATING`、價格 278、漲停 284.5、距離 2.34%、2 分鐘動能 2.21%、Evidence Score 100/100、6/6 evidence、Opening 建立到 Limit-Up 接手的 episode provenance，以及 `RiskGate` 未通過所造成的 Entry 阻擋。
- UI 明確標示 `Replay fixture／非即時`、`hypothesis_v0` 與「Evidence Score 不是漲停機率」。前端只格式化後端 projection，不重算 threshold、score、signal 或 stage；兩秒 polling 只有 projection digest 改變時才重繪 live region。
- 實際 browser QA 已確認告警確認後由 2 則變 1 則且 reload 不重播、console 無錯誤、桌面沒有水平 overflow；390px viewport 的三張 Momentum 卡片均落在可視範圍內，Evidence 單欄、價格雙欄。
- Gate G5 由 17 個 Dashboard focused tests、93% `dashboard.momentum` focused coverage 與完整 repository regression `261 passed, 1 skipped` 通過；JavaScript syntax、Python compile 與 `git diff --check` 皆通過。沒有啟動 realtime Shadow、live subscription、Broker/order path 或升級 hypothesis 參數，G0 仍開放。

### Phase 6 — Shioaji realtime Shadow

工作：

1. 建立單一 session owner、輕量 callback、bounded queue、ordered consumers。
2. 使用 Phase 0 通過的 Quote mode；若 parity 未通過，使用 Tick+BidAsk fallback 與較小 capacity。
3. 接上 Phase 1 CandidatePool／SubscriptionManager，驗證 Scanner discovery 到 subscription ack 的 end-to-end latency 與 churn。
4. queue overflow、disconnect、stale、reconnect、shutdown drain 全部可觀測並 fail closed。
5. 靜態與 runtime 測試證明此 path 不 import/call `place_order`。

Gate G6：Shadow 期間 queue silent drop 為 0、重複 alert 為 0、DataHealth gaps 全部有紀錄；subscription capacity 不超限；Snapshot/Ticks/Kbars 未被當盤中輪詢 feed。

Phase 6 implementation checkpoint（2026-08-18）：

- 新增 market-data-only `MomentumMarketDataStream` port、Shioaji Tick+BidAsk adapter 與單一 `MomentumShadowRuntime`。callback 只做正規化與 bounded enqueue；ordered consumer 才執行 ingestion、features、signals、state、projection 與 alerts。
- runtime 固定使用尚未升級的 Tick+BidAsk fallback；capacity 由顯式 account limit/headroom 以每檔兩個 subscriptions 計算。雙流 ACK 後才算 covered；partial subscribe rollback 未 ACK 前仍占容量，cleanup 未知時 DataHealth `BLOCKED`。
- disconnect／stale 進入 resync epoch。重新連線與重新訂閱 ACK 不會直接恢復健康；所有 covered symbols 都收到新且真正 `APPLIED` 的 Tick+BidAsk 後才 recover，帶 cumulative-volume gap 的 Tick 不算 recovery evidence。
- Shadow snapshot 提供 health、queue、callback silent-drop invariant、source lag、coverage/capacity、ACK latency、missed-reason funnel、signal、alert、reconnect 與 adapter/runtime error metrics。新增顯式參數的 Scanner Shadow CLI，持續輸出 JSON status 與新 Momentum alerts。
- fake-adapter focused tests、coverage、完整 regression、compile、CLI help 與 no-order static checks 均通過。完成時已過普通交易時段，因此沒有把盤後登入當成 live stream 證據；G6 prospective market-hours run、長時間 silent-drop/recall 報告仍待完成。

### Phase 7 — Historical event study + prospective discovery/order-book study

工作：

1. 先用 1m Kbars 建 universe、labels、positive/matched-control samples。
2. 對 samples 取得 historical Ticks，驗證外盤與精確 lead-time features。
3. 跑 chronological walk-forward、ablation、threshold curves 與 error analysis。
4. 分開評估 Opening 與 post-warm-up signal，不共用一個模糊總平均。
5. 五檔、Scanner/CandidatePool/subscription ack 另用 prospective Shadow capture 研究，報告 source coverage 差異。
6. 產出 immutable report：樣本、排除原因、oracle detector quality、prospective discovery recall、coverage、metrics、參數版本、限制。

Gate G7：研究 report review 後，才決定保留、調整或刪除 1.5%／3%／1.5x／60%／70 與 Opening volume hypothesis。

### Phase 8 — Parameter promotion

- 通過 review 時新增 `validated_v1`，保留 v0 Replay 能力。
- 未通過時保持 Research-only，Dashboard 明確標示實驗訊號。
- 即使通過 detector gate，也只代表偵測品質可接受，不自動授權 Simulation／Live order。

## 14. 預計檔案地圖

```text
candidate/
  sources.py                        # Scanner/AUTO/MANUAL/POSITION adapters
  pool.py                           # union, rank, TTL, priority, admission

market_data/
  events.py                         # normalized Tick/BidAsk + metadata
  clock.py                          # injected Clock + deterministic ReplayClock
  ingestion.py                      # ordered consumer + bounded queue outcomes
  instrument_reference.py           # current-session reference/limit store
  intraday_bar_store.py             # Tick-derived recent 1m bars/windows
  order_book_store.py               # latest five-level projection
  replay.py                         # immutable fixture loader + replay digest
  scanner.py                        # low-frequency Scanner client/capture
  momentum_stream.py                # market-data stream port + lifecycle
  shioaji_momentum_stream.py        # callbacks -> canonical events
  subscriptions.py                  # bounded active-universe policy
  quote_qualification.py            # Quote vs Tick+BidAsk parity report
  shioaji_quote_capture.py          # bounded data-only A/B capture
  health.py                         # freshness/gap/overflow status

features/
  models.py                         # IntradayFeatureSnapshot + validity
  engine.py                         # as-of rolling feature computation

signals/
  models.py                         # SignalResult, details, EntryMode
  momentum.py                       # MomentumSignalEngine + rule breakdown
  opening_momentum.py               # 09:00-09:10 signal family
  momentum_state.py                 # episode state machine
  projection.py                     # dashboard read model + alert dedup

runtime/
  momentum_shadow.py                # long-lived realtime Shadow orchestration

research/
  momentum_dataset.py               # immutable acquisition/normalization
  momentum_labels.py                # limit-up event/control labels
  momentum_evaluation.py            # walk-forward metrics/ablation

config/
  momentum.py                       # versioned hypothesis configs

dashboard/
  service.py                        # read MomentumProjection only
  server.py                         # projection endpoints / SSE
  static/index.html                 # alert, stage, evidence, timeline

tests/
  fixtures/8039_2026-08-18_*.json
  test_scanner_candidate_source.py
  test_candidate_pool.py
  test_subscription_manager.py
  test_quote_stream_parity.py       # credentialed/market-hours tagged test
  test_shioaji_quote_capture.py     # offline mapper/tracker tests
  test_intraday_bar_store.py
  test_order_book_store.py
  test_feature_engine.py
  test_momentum_signal_engine.py
  test_opening_momentum_signal.py
  test_momentum_state_machine.py
  test_limit_lock_state.py
  test_momentum_projection.py
  test_shioaji_momentum_stream.py
  test_momentum_shadow_runtime.py
  test_momentum_shadow_cli.py
  test_momentum_dashboard.py
  test_momentum_replay.py

scripts/
  capture_quote_parity.py           # one-symbol market-hours capture CLI
  replay_momentum_signal.py         # immutable Replay signal inspection CLI
  run_momentum_shadow.py            # explicit Scanner + realtime Shadow CLI

research/captures/quote_parity/
  *.json                            # credential-free immutable live artifacts
```

`pyproject.toml` 必須確認 `candidate*`、`market_data*`，並把 `features*`、`signals*`、`runtime*`、`research*` 加入 package discovery，再加 build/install smoke test，避免 editable install 可用但 wheel 漏檔。

## 15. Observability

至少記錄：

- Scanner request/cached response age、rank source、discovery count／latency
- Candidate admission／TTL expiry／eviction reason／pool churn
- subscription requested／acked／failed／unsubscribed、ack latency、count／capacity/headroom
- discovery/subscription coverage @ -10m/-5m/-3m/-1m 與 missed-reason funnel
- callback ingress rate、queue depth/high-water mark、overflow count
- source-to-received lag、feature age、book age、stale duration
- duplicate／out-of-order／cross-session event counts
- feature missing／unverified ratio，尤其 external／book
- Opening/post-warm-up evaluation、signal、family-handoff、stage-transition、invalidation、limit touched/locked/unlocked、alert counts
- alerts per day、per symbol、dedup suppress count
- config／feature／SDK／dataset version
- Shadow reconnect、shutdown-drain result

Log 不記 API secret、完整身份或帳務資料。

## 16. Definition of Done

第一個可交付版本完成時，必須同時滿足：

- 既有 71-test regression 持續通過。
- 8039 screenshot-only fixture 誠實回報 incomplete，不宣稱 volume acceleration。
- enriched 8039 replay 在 09:18 只發一次 `LIMIT_UP_MOMENTUM`，依 v0 權重的 Evidence Score 為 100／100，且 UI 明示不是 100% 機率。
- 09:03 early-move fixture 可由 `OpeningMomentumSignal` 評估，不為此放寬 post-warm-up rolling baseline；09:10 handoff 不更換 episode 或重複 alert。
- Opening confirmation 在 active breakout episode 可立即進 `ACCELERATING`；StateMachine 與 Entry Policy 不硬綁 `LIMIT_UP_MOMENTUM`。
- Episode 的 created/current family+config 與 transition/evidence-update provenance 可完整重播 09:10 handoff。
- Scanner／AUTO／MANUAL／POSITION 可形成 CandidatePool；capacity、priority、TTL、eviction 與 subscribe ack 有 deterministic tests。
- Quote 與 Tick+BidAsk parity report 能決定 runtime mode；失敗時安全 fallback 並按 headroom 公式降低 symbols。
- previous-high、2m return、volume baseline、external ratio、distance 與五檔公式都有 boundary／missing tests。
- duplicate／out-of-order／stale／overflow／session reset 全部 fail closed。
- `LIMIT_TOUCHED` 與 nullable `limit_locked`／locked/unlocked timestamps 可重播，book 不完整時不謊稱 unlocked。
- Dashboard 在本地 projection 更新後即時顯示繁中 evidence，不靠手動全市場 Snapshot 才刷新。
- RiskGate 缺失或拒絕時，畫面不顯示 `ENTRY AVAILABLE`。
- Shadow path 可證明沒有下單 API。
- 一年研究包含 negative/control、chronological holdout、Opening/post-warm-up 分層與 false-alert metrics；沒有歷史 Scanner snapshots 時只報 oracle detector quality。
- prospective Shadow 報告 Scanner discovery／Candidate admission／subscription ack recall 與 missed-reason funnel。
- 五檔歷史缺口被明確拆成 prospective study，沒有用假資料補研究結論。
- threshold promotion 產生新 config version，沒有覆寫 `hypothesis_v0`。

## 17. Feature flag 與 rollback

- `MOMENTUM_ENABLED=false` 時不啟動 Momentum evaluation、state transition 或 alert，但既有 Snapshot Dashboard／Candidate／BuyScore 行為保持不變。
- `MOMENTUM_DISCOVERY_ENABLED=false` 時停止 Scanner source；MANUAL／POSITION 與既有 Snapshot flow 不受影響。
- `MOMENTUM_OPENING_ENABLED=false` 時 09:00～09:10 顯示 warming/inactive，不改用未完成的 rolling baseline。
- `MOMENTUM_QUOTE_MODE=quote|tick_bidask` 可切回通過契約的 fallback；兩種模式都必須重新計算 capacity/headroom。
- `MOMENTUM_STREAMING_ENABLED=false` 時允許 Replay／Mock projection，禁止建立 Shioaji quote subscription，方便隔離 provider 問題。
- `MOMENTUM_ALERTS_ENABLED=false` 時仍可計算並保存 Shadow evidence，但不向 Dashboard 推播。
- 任何 queue overflow、timestamp/session mismatch、reference metadata 無效或 stale 超限，都自動降為 DataHealth `BLOCKED`；不需要等人工切 flag 才停止新 signal／entry opportunity。
- rollback 不刪歷史 dataset、episode 或 research capture；保留 manifest/config version 供事後分析。
- 新 API/UI 區塊在 projection unavailable 時顯示「Momentum 暫停」，不得讓整個既有 Dashboard 失效。

## 18. Review 結果與 Phase 0 尚待凍結項目

本輪 review 已接受：

1. `NEAR_LIMIT_UP` state 用 `<= 1%`，`<= 3%` 保留為 Evidence Score rule。
2. v1 只處理普通交易整股，所有 volume 明確以 `lots` 命名。
3. 8039 真實截圖 fixture 預期 incomplete；另用 synthetic baseline fixture 驗證完整 100 分 signal。
4. 第一版五檔只顯示 supporting evidence，不加入 Evidence Score；累積 20～30 個交易日後再 review。
5. 加入 Scanner/AUTO/MANUAL/Position discovery、CandidatePool 與 capacity-aware SubscriptionManager。
6. 09:00～09:10 使用獨立 Opening family，不破壞完整 rolling baseline。
7. 公開 stage 使用 `LIMIT_TOUCHED`，lock/unlock 是分開、可未知的 book condition。
8. API/UI 使用 Evidence Score 與規則成立數，明示不是漲停機率。
9. `ACCELERATING` 使用 family-neutral acceleration semantic，Opening 與 post-warm-up family 都可確認。
10. Momentum Entry 使用 versioned enabled-family policy + active acceleration episode + RiskGate PASS。
11. Episode 分開保存 created/current family+config，所有 transition/evidence update 各自保存 provenance。

Phase 0 仍須用 capture／fixtures 凍結三個實證項目：Quote parity pass criteria 與 runtime mode、Scanner 實際 cadence／headroom、Opening volume context 與 lock confirmation policy。完成這個 gate 後按 Phase 1 → Phase 3 先完成 discovery allocator 與 deterministic detector；Realtime Shadow 與 Dashboard streaming 再接續，不需要碰任何 Broker order。

## 19. 參考資料

- [Shioaji Stock Streaming](https://sinotrade.github.io/tutor/market_data/streaming/stocks/)
- [Shioaji Snapshot](https://sinotrade.github.io/tutor/market_data/snapshot/)
- [Shioaji Historical Market Data](https://sinotrade.github.io/tutor/market_data/historical/)
- [Shioaji Quote-Binding Mode](https://sinotrade.github.io/tutor/market_data/streaming/quote_binding/)
- [Shioaji Scanner](https://sinotrade.github.io/tutor/market_data/scanners/)
- [Shioaji Contract](https://sinotrade.github.io/tutor/contract/)
- [Shioaji Use Restrictions](https://sinotrade.github.io/tutor/limit/)
- [TWSE Trading Mechanism](https://www.twse.com.tw/en/products/system/trading.html)
- [TWSE 每日漲跌停價格計算](https://www.twse.com.tw/zh/products/system/trading.html?hl=zh-TW)
- [TPEx Trading Mechanism](https://www.tpex.org.tw/en-us/mainboard/trading/rules/system.html)
