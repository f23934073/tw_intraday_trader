# Trade Management Enhancement Implementation Plan v0.4

- 狀態：Phase 0 review incorporated／APPROVED TO START PR-TM-001／尚未實作
- 日期：2026-08-20
- 專案：`tw_intraday_trader`
- 優先級：Trade Thesis／Thesis Exit 為 P0；Trading Guard 為 P1；Dashboard 為 P2
- 執行邊界：本機紙上模擬、歷史回測、Replay／Shadow decision support
- 明確排除：Shioaji 下單、真錢交易、自動實盤退出、CA、券商帳務操作

> 本文件只定義 implementation plan。這一輪不修改交易、行情、模擬、回測或
> Dashboard runtime。

## 1. 結論

原始方向正確，但不能直接照提案新增 `domain/trading/trade_thesis.py`、
`trade_management/thesis_monitor.py`、`risk/trading_guard.py` 三套孤立元件。
目前 repo 已有：

- `CandidateEngine` 與 `BuyScoreEngine` 的 entry evidence。
- legacy `PositionManager` 與 boolean Stop Loss／Take Profit rules。
- local paper 的委託、成交、持倉、realized PnL 與 Tick／BidAsk 更新。
- Journal-first `OrderApplicationService`、versioned `RiskGate`、daily loss rule。
- 可重播的 backtest entry／exit strategy、exit priority 與一分鐘特徵。
- 正在規劃中的 canonical market-event pipeline。

因此本計畫採以下方向：

1. `TradeThesis` 是 immutable entry contract，不是塞進 legacy `Position` 的幾個欄位。
2. actual fill 才啟用 thesis；signal、order submission、fill time 分開保存。
3. `ThesisMonitor` 是 pure evaluator，輸入明確且已完整 materialize 的 market context，
   不直接讀 Shioaji、FastAPI、wall clock 或 latest-only `MarketDataStore`。
4. `ExitDecisionEngine` 聚合 Price Risk、Thesis、Time、Take Profit，輸出可去重的
   decision；decision 不等於 order 或 fill。
5. `TradingGuard` 擴充既有 `trading.risk.RiskGate` 與 Journal projection，不建立第二套
   risk pipeline。
6. 第一階段只產生退出建議／local-paper projection；不得因本 plan 自動送出 SELL。
7. 所有新狀態都以 Journal event 可重建；Dashboard 只顯示 server projection，不重算規則。
8. `schema_version`、`strategy_version`、`thesis_version` 分開；歷史交易可回查真正執行的
   進場與持倉驗證邏輯。
9. Exit reason 使用 stable enum；partial SELL 的每個 exit leg 保留自己的 reason、數量、
   成交價與 recommendation provenance。
10. Canonical market time、ingress receipt time、fill time 與 Journal append order 各有單一
    語意；Thesis deadline 只從 authoritative `filled_at` 開始。
11. 每個 `trade_id` 同時最多一個 active exit recommendation；重複 INVALID events 只能更新
    同一 recommendation 的 evidence／priority。
12. `ThesisMonitor` 是 pure function boundary，不持有或修改 Position、Order、RiskState、
    Journal、projection 或 adapter。

目標資料流：

```text
Entry Strategy / Manual Thesis Draft
                │
                ↓
      immutable TradeThesisDraft
                │ opening fill
                ↓
        activated TradeThesis
                │
 Canonical Market Context + Clock
                │
                ↓
          ThesisMonitor
                │
                ├── VALID / WARNING / INSUFFICIENT_DATA
                └── INVALID
                         │
 Price Risk ─────────────┤
 Time Decay ─────────────┤
 Take Profit ────────────┤
                         ↓
              ExitDecisionEngine
                         │
                         ↓
             EXIT recommendation
                         │ closing fill
                         ↓
             TradeOutcome projection
                         │
                         ↓
                Trading Guard
                         │
               block new BUY only
```

## 2. Repository-grounded gap analysis

### 2.1 可直接沿用

| 現有能力 | 位置 | 本計畫用途 |
|---|---|---|
| Candidate rule evidence | `candidate/engine.py` | 保存 entry supporting evidence，不直接當 executable invalidation rule |
| Buy Score breakdown | `scoring/engine.py` | 保存進場時各 rule 的 observed score 與 version |
| Stop Loss／Take Profit | `position/exit_rules.py` | 先用 compatibility adapter 轉成 structured exit evaluation |
| Backtest strategy evaluations | `backtest/strategies.py`、`backtest/decision_aggregator.py` | 共用 priority／evidence pattern並做 thesis replay parity |
| Local paper fills／positions／PnL | `simulation/service.py`、`trading/local_paper.py` | thesis activation、trade lifecycle、guard state 的來源 |
| Journal／idempotency | `trading/journal.py`、`trading/postgres_journal.py` | 所有 thesis、exit、trade close、guard transition 的 authoritative record |
| RiskGate | `trading/risk.py` | 加入 consecutive-loss cooldown 與 entry-only guard reasons |
| Injected clock | `runtime/clock.py` | domain deadline、session date、Replay 測試 |
| Runtime composition | `runtime/composition.py` | 唯一 wiring point；不得在 route 或 callback 建 engine |
| Native ES-module UI | `dashboard/static/js/workspaces/simulation.js` | 顯示 thesis／guard server projection |

### 2.2 現況缺口

1. legacy `Position` 只有 `symbol`、`entry_price`、`quantity`，沒有 fill、strategy、
   decision、thesis 或 session identity。
2. `ExitRule.should_exit() -> bool` 無法保留 reason、threshold、observed evidence、
   evaluated time、data health 與 priority。
3. `MarketDataStore` 只保留最新 `StockData`；無法回答「進場後五分鐘內是否創新高」或
   「量能是否擴張」。
4. local paper 可以延後成交 pending order，但目前 Journal recorder 主要掛在 command
   acknowledgement；任何由後續 quote 觸發的 fill 都必須補成同一條 idempotent lifecycle
   event path，否則 thesis 與 guard 會漏事件。
5. current realized PnL 以 symbol 累計，沒有 `trade_id`／position lifecycle；無法可靠判斷
   三筆「交易」連敗。
6. `RiskGate` 已有 daily loss，但目前 entry-style blocker 並未完整區分 BUY 與 SELL。
   心理風控不得阻擋風險降低型 SELL。
7. automated strategy origin 目前刻意 disabled；thesis invalid 只能先產生 decision，不能
   越過 authorization 直接送單。
8. local paper 預設使用 in-memory Journal；若 enforcing guard 在 app restart 後消失，
   就不能宣稱具有 session-level protection。

## 3. 對原始 v0.1 的必要修正

| 原提案 | v0.4 決策 | 原因 |
|---|---|---|
| `reasons: list[str]` 同時代表理由與規則 | reason snapshot 與 executable condition 分開 | 字串可供顯示，但不能安全執行 threshold／time logic |
| 沒有獨立 thesis logic version | 增加 `thesis_type`／`thesis_version`，與 schema/strategy version 分開 | 同一 entry strategy 未來可能更換持倉驗證或退出邏輯 |
| Exit reason 使用自由字串 | 凍結 `ExitReason` enum；自由文字只作 detail | 統計、Replay、Dashboard 與 migration 需要 stable code |
| `entry_time` 在 BUY 時寫入 | `signal_at`、`submitted_at`、`filled_at` 分開；以 opening fill 啟用 thesis | pending order 可能晚成交或未成交 |
| `ExpectedBehavior(require_new_high=True, ...)` | 使用 versioned、typed、帶 threshold/baseline 的 condition specs | `True` 沒定義「高多少」、「相對誰」、「用 Tick 或 completed bar」 |
| `ThesisResult` 只有 VALID/WARNING/INVALID | 增加 `INSUFFICIENT_DATA` | 缺資料不可被誤判為 valid 或 thesis invalid |
| Monitor 直接吃 `market_data` | 吃 deterministic `ThesisMarketContext` 與前一 projection | latest snapshot 沒有 window history，也無法 Replay |
| `TimeDecayExitRule` 讀現在時間 | 使用 injected `Clock`／event time，明確 deadline boundary | Backtest、Replay、realtime 必須一致且可測 |
| 新建獨立 `TradingGuard` 風控路徑 | `TradingGuardProjection` + 現有 `RiskGate` | Manual／future strategy command 已在同一 journal-first boundary 匯流 |
| `TradeEvent` 另存一套 event store | 定義 versioned Journal record kinds | repo 已有 idempotent append-only Journal 與 projection checkpoint |
| PositionManager 直接負責所有狀態 | legacy manager 保留 compatibility view；fill-derived lifecycle 為權威 | 目前 manager 是 hard-coded／in-memory decision demo，不是帳本 |
| thesis invalid 就 `exit()` | 先產生 `ExitDecision`；local paper 自動 SELL 需另行 review／啟用 | decision、order、fill 是不同生命週期 |

## 4. Scope、non-goals 與 invariants

### 4.1 In scope

- Immutable Trade Thesis draft／activation contracts。
- 第一個 executable `ORB_BREAKOUT/v1` thesis definition。
- Expected Behavior、Invalid Condition、Time Decay pure evaluation。
- Structured exit evaluation、deterministic priority 與 idempotent exit decision。
- Fill-derived `trade_id` lifecycle 與 closed-trade outcome。
- Daily realized loss、consecutive-loss cooldown、guard projection。
- Local paper／backtest／Historical Tick Replay 的 thesis semantic parity。
- Dashboard thesis、condition、exit decision、guard status read model。
- Feature flags、migration、observability、rollback。

### 4.2 Out of scope

- Shioaji order/deal callback、券商帳務或 buying power API。
- 真錢、自動實盤、自動 Shioaji Simulation 下單。
- Short selling、當沖券、零股、partial-fill broker simulation。
- 同一 symbol 同時存在多個獨立 thesis／lot selection。
- Pyramiding／scale-in。v1 thesis-managed position 存在時，新 BUY fail closed。
- ML／LLM 生成或覆寫退出決策。
- 用 Dashboard JavaScript 計算 VWAP、volume expansion 或 loss streak。
- 宣稱 ORB、五分鐘、量能門檻已經有獲利證據；它們仍是 versioned hypothesis。

### 4.3 Invariants

1. 每個 thesis-managed opening fill 恰好對應一個 `trade_id` 與一個 active thesis。
2. Thesis immutable；後續最高價、警告狀態、deadline progress 存在 projection。
3. 只有 executable thesis definition 可以產生 Thesis Invalid exit；純顯示用 reasons 不執行。
4. domain logic 不讀 `datetime.now()`，也不直接 import Provider、Shioaji、FastAPI、DB。
5. missing、stale、out-of-order、session mismatch 資料不會被判為 VALID。
6. WARNING 不產生 exit；INVALID 一旦成立就 latch，直到 position fully closed。
7. 同一 market event／thesis 最多產生一個 exit decision。
8. 同時觸發多個 exit 時保留全部 reasons，但 primary reason 依固定 priority 決定。
9. Trading Guard 只阻擋 entry risk；SELL、cancel、recovery、reconciliation 不被心理風控擋住。
10. Loss streak 只在 position quantity 從正數降為零時更新；partial SELL 不算新一筆交易。
11. Enforcing guard 必須可從 durable Journal 重建；無 durable mode 時只能標示 preview。
12. HTTP polling 不是 monitor clock；browser 關閉也不影響 server-side thesis state。
13. 本 plan 不新增或呼叫任何 broker order API。
14. Historical Tick Replay 使用 immutable canonical events 與 ReplayClock；不得用 Kbar 或
    synthetic ticks 冒充逐筆資料。

## 5. Domain contracts

### 5.1 TradeThesisDraft 與 TradeThesis

建議新增 `trading/thesis.py`，而不是另開新的 top-level `domain/`：

```python
class ThesisType(StrEnum):
    ORB_BREAKOUT = "ORB_BREAKOUT"
    GAP_RVOL = "GAP_RVOL"


@dataclass(frozen=True)
class TradeThesisDraft:
    thesis_id: str
    schema_version: str
    session_id: str
    symbol: str
    side: Literal["LONG"]
    strategy_id: str
    strategy_version: str
    thesis_type: ThesisType
    thesis_version: str
    decision_id: str
    signal_at: datetime
    created_at: datetime
    entry_evidence: tuple[EntryEvidence, ...]
    expected_behavior: ExpectedBehaviorPolicy
    invalid_conditions: tuple[InvalidConditionSpec, ...]


@dataclass(frozen=True)
class TradeThesis:
    thesis_id: str
    trade_id: str
    draft: TradeThesisDraft
    opening_order_id: str
    opening_fill_id: str
    entry_reference_price: Decimal
    filled_at: datetime
    fill_time_source: FillTimeSource
```

規則：

- `thesis_id` 在 draft 時建立；retry 不可產生新 id。
- `trade_id` 在第一筆 opening fill 建立。
- `entry_reference_price` 必須使用第一筆建立 exposure 的 actual fill price，不使用 order
  limit 或 signal reference price；position average price 是另一個 projection 欄位。
- `filled_at` 是第一筆建立 exposure 的 authoritative fill time，也是 Thesis deadline 唯一
  起點。後續同一 opening order 的 partial fills 不重設 deadline；新的 scale-in order v1 禁止。
- `schema_version` 只表示 payload shape；`strategy_version` 表示 entry logic；
  `thesis_version` 表示 expected behavior、invalid conditions、deadline 與 exit mapping 的
  immutable logic bundle。三者不得互相代替。
- canonical definition identity 為 `thesis_type + thesis_version`，例如
  `ORB_BREAKOUT/v1`、`GAP_RVOL/v2`。
- entry evidence 保存 value、threshold、rule／strategy version、market event identity；
  Candidate matched rules 與 Buy Score breakdown 可以列入 supporting evidence。
- current Candidate rules 不會被自動解讀成 ORB invalidation。只有
  `thesis_type + thesis_version` 的 typed mapping 可以執行。
- v1 不支援 scale-in。active thesis 存在時，新 BUY 回傳
  `ACTIVE_THESIS_POSITION` entry block。

### 5.2 EntryEvidence

```python
@dataclass(frozen=True)
class EntryEvidence:
    evidence_id: str
    kind: str
    source_component: str
    source_version: str
    status: str
    observed: Mapping[str, Decimal | int | str | bool | None]
    threshold: Mapping[str, Decimal | int | str | bool | None]
    market_event_id: str
    observed_at: datetime
```

不可只保存 `"gap_up"`。Dashboard 可以由後端把 typed evidence 翻成繁中，但 Journal
必須保留 stable reason code 與原始數值。

### 5.3 ExpectedBehaviorPolicy

```python
@dataclass(frozen=True)
class ExpectedBehaviorPolicy:
    policy_id: str
    version: str
    observation_window: timedelta
    warning_after: timedelta | None
    completion_policy: Literal["ALL"]
    conditions: tuple[ExpectedConditionSpec, ...]
```

第一個 `ORB_BREAKOUT/v1` definition 的 condition specs：

| Condition | 明確語意 | v1 建議值 |
|---|---|---|
| `NEW_HIGH_EXTENSION` | deadline 前 `max_price_since_entry` 嚴格高於 reference level 加 buffer | reference 與 buffer 由 thesis definition 保存 |
| `POST_ENTRY_VOLUME_EXPANSION` | completed 1m post-entry volume ÷ frozen baseline >= ratio | baseline kind、樣本數、ratio 全部版本化 |
| `HOLD_ABOVE_VWAP` | completed 1m close 未連續超過允許根數落在 VWAP 下方 | v1 先以一根 completed bar 作 confirmation |

`volume_expand=True` 不足以實作。必須凍結：

- volume 單位。
- baseline 是 opening-range median、歷史同時段或其他來源。
- rolling window 與 minimum sample count。
- 比較符號 `>=` 或 `>`。
- missing baseline 時的 `INSUFFICIENT_DATA` 行為。

### 5.4 InvalidConditionSpec

第一個 `ORB_BREAKOUT/v1` definition：

| Condition | 觸發方式 | 結果 |
|---|---|---|
| `BREAKOUT_LEVEL_LOST` | completed 1m close `< breakout_level`；exactly equal 不觸發 | `INVALID` |
| `VWAP_CONFIRMATION_LOST` | completed 1m close `< vwap` 達 policy 指定 confirmation | `INVALID` |
| `SESSION_DATA_BLOCKED` | canonical health BLOCKED／session mismatch | `INSUFFICIENT_DATA`，另交 operational risk 處理 |

Stop Loss 仍是獨立 Price Risk，不塞進 thesis invalid conditions。這樣研究「理由錯」與
資本保護「價格風險」可以分開統計。

### 5.5 ThesisMarketContext

```python
@dataclass(frozen=True)
class ThesisMarketContext:
    source_event_id: str
    session_id: str
    session_date: date
    symbol: str
    evaluated_at: datetime
    last_price: Decimal | None
    completed_bar: CompletedBar | None
    session_vwap: Decimal | None
    max_price_since_entry: Decimal | None
    post_entry_volume: Decimal | None
    volume_baseline: Decimal | None
    data_health: str
```

這個 context 由 canonical projection／Replay adapter 組合。`ThesisMonitor` 不自己維護
Shioaji subscriptions，也不建立第三個 quote queue。

### 5.6 ThesisEvaluation

```python
class ThesisStatus(StrEnum):
    VALID = "VALID"
    WARNING = "WARNING"
    INVALID = "INVALID"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"


@dataclass(frozen=True)
class ThesisEvaluation:
    thesis_id: str
    status: ThesisStatus
    evaluated_at: datetime
    source_event_id: str
    reason_codes: tuple[str, ...]
    conditions: tuple[ConditionEvaluation, ...]
    observed: Mapping[str, object]
    thresholds: Mapping[str, object]
    data_health: str
```

Status aggregation：

1. invalid condition 成立 → `INVALID`。
2. required input 不可用／不可信 → `INSUFFICIENT_DATA`。
3. deadline 到達且 required expected behavior 未全部成立 → `INVALID`，reason=
   `EXPECTED_BEHAVIOR_EXPIRED`。
4. warning boundary 到達但 deadline 未到、condition 尚未完成 → `WARNING`。
5. 其他情況 → `VALID`，但每個 condition 仍可顯示 `PASS`／`PENDING`。

### 5.7 ThesisStateProjection

Mutable state 不回寫 TradeThesis：

```python
@dataclass(frozen=True)
class ThesisStateProjection:
    thesis_id: str
    status: ThesisStatus
    highest_price_since_entry: Decimal
    last_evaluated_event_id: str
    last_evaluated_at: datetime
    warning_since: datetime | None
    invalidated_at: datetime | None
    invalid_reason_codes: tuple[str, ...]
    last_journal_sequence: int
```

Reducer 必須對 duplicate idempotent、對 sequence 倒退 fail closed、對 INVALID latch。

### 5.8 Canonical Timestamp Contract

四種時間／順序不可混用：

| 欄位 | 唯一語意 | 可用於 Thesis deadline |
|---|---|---|
| `event_at` | canonical market event time；由來源 exchange/provider timestamp 正規化 | 只在該 event 觸發 simulated fill 時成為 `filled_at` |
| `received_at` | callback／ingress receipt wall time；用於 latency、freshness、clock-skew audit | 否 |
| `filled_at` | authoritative execution event time；第一筆建立 exposure 的 fill time | **是，唯一來源** |
| Journal `sequence` | append/persistence order；不是市場或成交時間 | 否 |

本 plan 統一使用 `event_at`，不另外混入語意重疊的 `exchange_time` 欄位。來源 adapter
若原始欄位叫 `exchange_timestamp`，進 canonical envelope 時映射為 `event_at`，原始值可留
在 provenance，但 domain 不同時讀兩個名稱。

```python
class FillTimeSource(StrEnum):
    CANONICAL_MARKET_EVENT = "CANONICAL_MARKET_EVENT"
    SIMULATION_CLOCK = "SIMULATION_CLOCK"
    BROKER_EVENT = "BROKER_EVENT"  # future, not enabled by this plan
```

規則：

1. Historical Tick／quote-triggered local-paper fill：`filled_at = triggering_event.event_at`，
   保存 `source_event_id`，source=`CANONICAL_MARKET_EVENT`。
2. Replay control／synthetic deadline event不能製造成交；Replay fill 仍必須連到 eligible
   canonical event。`ReplayClock.now()` 只能反映目前 replay event time。
3. Legacy Mock／snapshot immediate fill 若沒有可信 market event identity，只能標為
   `SIMULATION_CLOCK` 並使用 injected Clock；不得標成 exchange time，也不能通過
   Historical Tick parity gate。
4. Future broker callback 只有在 broker fill timestamp contract 經獨立 review 後才能使用
   `BROKER_EVENT`；目前不實作。
5. 所有 timestamp timezone-aware；此專案 session boundary 以 `Asia/Taipei` 正規化。
6. `signal_at`、`submitted_at`、`received_at` 只作 provenance／latency，不啟動或重設 thesis。
7. Journal `occurred_at` 保存該 domain event 的時間；真正處理順序仍以 append `sequence`
   稽核，兩者不可互相覆蓋。
8. 任一 fill 缺 `filled_at` 或 time source 時，thesis activation fail closed；
   `CANONICAL_MARKET_EVENT` 另強制要求 `source_event_id`，`SIMULATION_CLOCK` 則要求可重播的
   simulation command／clock identity，不得以空 provenance fallback。

## 6. Thesis Builder

建議新增 `trading/thesis_builder.py`。

### 6.1 Strategy entry

Builder 輸入既有 `TradeDecision`／entry strategy evaluation：

- `strategy_id`、`version`、`decision_id`。
- observed／threshold evidence。
- exact market event／bar identity。
- thesis-definition registry mapping。

第一個 end-to-end mapping 使用 repo 已存在的 experimental
`opening_range_breakout_entry_v1`，因為它已保存完整 opening range、breakout price 與
completed 1m capability。不得從 generic Candidate `gap_up` 或 Buy Score `above_vwap`
倒推出未曾成立的 ORB evidence。

### 6.2 Manual local-paper BUY

在 `TRADE_THESIS_REQUIRED=false` 時維持目前 API 相容。

準備 enforcing mode 時：

- BUY request 必須帶 server-issued `decision_id`／`thesis_draft_id`，或提交完整且通過
  server-side thesis-definition validation 的 manual draft。
- 從 Candidate detail 開單時，server snapshot 產生 draft；browser 不自行組 threshold。
- 純手動 symbol 若沒有 executable thesis definition，API 回 `422 THESIS_REQUIRED`，而不是用
  自由文字假裝可以監控。
- SELL 不建立新的 thesis。

### 6.3 Draft lifecycle

```text
DRAFT_CREATED
    ├── opening order cancelled/rejected → DRAFT_TERMINATED
    └── first opening fill              → THESIS_ACTIVATED
```

Pending order 尚未 fill 時不能開始五分鐘 clock。

## 7. Thesis Monitor 與 Time Decay

建議新增 `trading/thesis_monitor.py` 與 `trading/time_exit.py`。

### 7.1 Evaluation sequence

每筆 accepted canonical event／completed replay bar：

1. 讀 active thesis projection。
2. 驗證 session、symbol、source event ordering、data health。
3. application layer 以 pure context reducer 更新 highest price／volume window／completed-bar
   evidence，組成新的 immutable `ThesisMarketContext`。
4. 先檢查 hard invalid conditions。
5. 再檢查 expected behavior deadline。
6. 輸出 structured evaluation。
7. 只有 status 或 reason set 改變時 append `thesis_state_changed.v1`；不為每個 Tick 寫一筆
   transition event。

### 7.2 五分鐘 boundary

- `deadline = filled_at + observation_window`。
- `evaluated_at < deadline`：未完成可為 VALID/PENDING 或 WARNING。
- `evaluated_at >= deadline`：只使用 deadline 前可觀測 evidence；未完成即 INVALID。
- realtime profile 可用 Tick／completed bar exact event time。
- bar-only backtest 若 deadline 落在 bar 內，採下一個 completed-bar boundary 的保守
  evaluation，並在 result 標示 `resolution=BAR_1M`；不得假裝有 tick-level 時序。
- wall clock 經過但沒有新 market event 時，由 injected scheduler 產生
  `THESIS_DEADLINE_REACHED` control event；browser polling 不得觸發 deadline。

### 7.3 Data unavailable

- 沒有 VWAP、volume baseline、required completed bar → `INSUFFICIENT_DATA`。
- `INSUFFICIENT_DATA` 不等同 thesis invalid，也不會靜默 HOLD。
- operational policy 可另外顯示「資料不足，停止新進場／需要人工處理既有部位」。
- 不在此 milestone 自動以 stale price 平倉。

### 7.4 Pure evaluation／no hidden mutation boundary

`ThesisMonitor` 的 public boundary 固定為 pure evaluation：

```python
class ThesisMonitor:
    def evaluate(
        self,
        thesis: TradeThesis,
        market: ThesisMarketContext,
    ) -> ThesisEvaluation:
        ...
```

- `TradeThesis` 與 `ThesisMarketContext` 都是 immutable input。
- `ThesisMonitor` constructor 只接受 immutable thesis-definition config；不接受 repository、
  Journal、Clock、PositionManager、SimulationService、RiskGate 或 callback。
- Monitor 不呼叫 `Position.add/remove`、不建立／取消 Order、不改 RiskState、不 append
  Journal、不更新 projection、不執行 network/filesystem I/O。
- Window state（highest price、volume baseline、completed bars）由 upstream canonical
  projection 放入 `ThesisMarketContext`；Monitor 不私藏 mutable per-symbol cache。
- Application layer 收到 `ThesisEvaluation` 後，才交給獨立 pure reducer 產生新的
  `ThesisStateProjection`，再由 Journal/application service 持久化。
- 測試使用 frozen dataclasses、dependency/import boundary 與 mutation spies，證明相同 input
  會得到相同 output，且 Position／Order／Risk／Journal 都沒有變化。

## 8. Unified Exit Decision

建議新增 `trading/exit_decision.py`。

### 8.1 Structured contract

```python
class ExitCategory(StrEnum):
    EMERGENCY_RISK = "EMERGENCY_RISK"
    THESIS_INVALID = "THESIS_INVALID"
    TIME_EXPIRED = "TIME_EXPIRED"
    TAKE_PROFIT = "TAKE_PROFIT"


class ExitReason(StrEnum):
    STOP_LOSS = "STOP_LOSS"
    ATR_STOP = "ATR_STOP"
    END_OF_DAY = "END_OF_DAY"
    THESIS_INVALID = "THESIS_INVALID"
    TIME_DECAY = "TIME_DECAY"
    TAKE_PROFIT = "TAKE_PROFIT"
    RISK_GATE = "RISK_GATE"
    MANUAL = "MANUAL"


@dataclass(frozen=True)
class ExitEvaluation:
    rule_id: str
    rule_version: str
    category: ExitCategory
    triggered: bool
    evaluated_at: datetime
    source_event_id: str
    reason_codes: tuple[ExitReason, ...]
    observed: Mapping[str, object]
    thresholds: Mapping[str, object]


@dataclass(frozen=True)
class ExitDecision:
    decision_id: str
    trade_id: str
    thesis_id: str
    action: Literal["HOLD", "EXIT"]
    primary_reason: ExitReason | None
    triggered_reasons: tuple[ExitReason, ...]
    evaluations: tuple[ExitEvaluation, ...]
    decided_at: datetime
    source_event_id: str


class ExitRecommendationStatus(StrEnum):
    ACTIVE = "ACTIVE"
    RESOLVED_ON_CLOSE = "RESOLVED_ON_CLOSE"


@dataclass(frozen=True)
class ExitRecommendation:
    recommendation_id: str
    trade_id: str
    thesis_id: str
    status: ExitRecommendationStatus
    first_trigger_decision_id: str
    first_trigger_event_id: str
    latest_decision_id: str
    latest_evidence_event_id: str
    primary_reason: ExitReason
    triggered_reasons: tuple[ExitReason, ...]
    created_at: datetime
    updated_at: datetime
```

`ExitReason` 是 Journal／API／統計使用的 stable code；繁中說明與 observed detail 不屬於
enum identity。`RISK_GATE` 只保留給未來明確的 risk-policy flatten decision，不表示
「RiskGate 拒絕了一筆 entry」；v1 daily-loss/cooldown 只擋新 BUY，不會自行產生
`RISK_GATE` exit。

### 8.2 Priority

固定 priority table，不依 list 注入順序：

1. `EMERGENCY_RISK`：Stop Loss、ATR risk、session/EOD safety。
2. `THESIS_INVALID`：breakout level／VWAP thesis 已被否定。
3. `TIME_EXPIRED`：預期在期限內未發生。
4. `TAKE_PROFIT`。

同一 completed bar 同時觸及 stop 與 take profit 時使用保守 priority，primary 為 Stop
Loss；仍保留 Take Profit evaluation 供 audit。WARNING 不列入 exit reasons。

### 8.3 Idempotency

`ExitDecision` 是 pure、per-event evaluation，沒有 side effect；`ExitRecommendation` 是
position lifecycle 內唯一可供使用者或未來 execution 消費的 active object。兩者不可混為
同一 identity。

```text
decision_id = hash(session_id, trade_id, source_event_id,
                   exit_policy_version, evaluation_digest)

recommendation_id = hash(session_id, trade_id,
                         exit_policy_version, "liquidation-cycle-1")
```

規則：

1. 同一 source event retry 得到相同 `decision_id`。
2. 第一個 action=EXIT 的 decision 建立唯一 ACTIVE recommendation，保存 first trigger。
3. 後續 600→599→598 等相同 INVALID episode 不建立第二個 recommendation。
4. 後續若出現更高 priority reason（例如 THESIS_INVALID 後又 STOP_LOSS），在相同
   `recommendation_id` append `exit_recommendation_updated.v1`，更新 primary/all reasons。
5. reason／priority 未改變時，不因每個 Tick append update；latest market evidence 留在
   bounded projection/metrics，不製造 Journal spam。
6. Partial SELL 後 recommendation 維持 ACTIVE；final SELL 讓 trade CLOSED，並 append
   `exit_recommendation_resolved.v1`。
7. v1 每個 `trade_id` 只有一個 liquidation cycle；新 position 必須使用新 `trade_id`。
8. future SELL command idempotency key 只能由唯一 `recommendation_id` 衍生，不能由最新
   Tick／decision 重新產生。

因此相同 trade 的 active recommendation cardinality invariant 為：

```text
count(ACTIVE recommendation where trade_id = X) <= 1
```

若未來 recommendation 進入 execution，資料流固定為：

```text
ThesisMonitor → ExitDecision(reason=THESIS_INVALID)
              → ExitRecommendation(one active per trade)
              → SELL OrderCommand(recommendation_id, exit_reason)
              → RiskGate execution validation
              → execution adapter
```

RiskGate 不重新計算 thesis，也不能把 `THESIS_INVALID` 改回 VALID。它只驗證 command
quantity、position availability、market/book capability 與 idempotency；daily-loss、cooldown
等 entry-only guard 不得阻擋 SELL。

### 8.4 Legacy compatibility

- `position/exit_rules.py` 第一階段保留 `should_exit()`。
- 新增 adapter 把 boolean result 加上 observed／threshold，供新 engine 使用。
- `app.run_scan()` 的 hard-coded position 繼續走 legacy path，直到 local-paper projection
  取代 demo card；不得讓一次性 scan 持有長生命週期 thesis state。
- Backtest 使用 adapter 或新增 thesis strategy binding，但仍由現有
  `DecisionAggregator` 決定 primary strategy，避免兩個 priority engines 漂移。

## 9. Trade lifecycle and Journal events

### 9.1 為什麼需要 `trade_id`

「連續三筆虧損」的單位是完整 trade lifecycle，不是：

- 每一筆 SELL fill。
- 每一個 symbol 的累積損益。
- 每次 API request。
- 每次部位 mark-to-market 變動。

v1 lifecycle：第一筆 opening BUY fill 建立 `trade_id`；quantity 回到零時 closed。
Partial SELL 只累計 realized PnL，不先更新 streak。

在第一筆 fill 前，pre-exposure lifecycle 以 `thesis_id + entry_order_id` 關聯，`trade_id`
尚不存在；第一筆 non-zero opening fill 才原子建立 `trade_id` 並把既有 decision/order facts
連入同一 correlation chain。不得預先產生一個最後沒有成交的幽靈 trade。

Phase 0 不建立一個混合所有責任的 lifecycle enum，而是凍結三個相連的 state machine：

```python
class DecisionLifecycleState(StrEnum):
    SIGNAL_CREATED = "SIGNAL_CREATED"
    THESIS_DRAFTED = "THESIS_DRAFTED"
    THESIS_ACTIVE = "THESIS_ACTIVE"
    EXIT_RECOMMENDATION_ACTIVE = "EXIT_RECOMMENDATION_ACTIVE"
    COMPLETED = "COMPLETED"
    TERMINATED = "TERMINATED"


class OrderLifecycleState(StrEnum):
    CREATED = "CREATED"
    SUBMITTED = "SUBMITTED"
    PENDING = "PENDING"
    PARTIALLY_FILLED = "PARTIALLY_FILLED"
    FILLED = "FILLED"
    CANCELLED = "CANCELLED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"
    RECOVERY_REQUIRED = "RECOVERY_REQUIRED"


class TradeLifecycleState(StrEnum):
    PENDING_ENTRY = "PENDING_ENTRY"
    ACTIVE_POSITION = "ACTIVE_POSITION"
    EXIT_IN_PROGRESS = "EXIT_IN_PROGRESS"
    CLOSED = "CLOSED"
    ENTRY_TERMINATED = "ENTRY_TERMINATED"
```

Ownership：

| State machine | 回答問題 | 不負責 |
|---|---|---|
| Decision | signal／thesis／recommendation 現在在哪個階段 | 委託是否被 broker/simulator 接受 |
| Order | 每張 entry／exit order 的 submit、pending、partial fill、terminal state | position quantity 或 thesis validity |
| Trade | 是否已建立 exposure、是否正在退出、是否 fully closed | order transport detail 或 market hypothesis |

Correlation chain：

```text
signal_id / decision_id
        ↓
thesis_id
        ↓
entry_order_id
        ↓
opening fill_id(s)
        ↓
trade_id
        ↓
recommendation_id
        ↓ future only
exit_order_id(s) → exit fill_id(s) → ExitLeg(s)
```

主要 transition：

```text
Decision:
SIGNAL_CREATED → THESIS_DRAFTED
    ├── entry rejected/cancelled with no fill → TERMINATED
    └── first opening fill → THESIS_ACTIVE
THESIS_ACTIVE + first EXIT decision → EXIT_RECOMMENDATION_ACTIVE
final closing fill → COMPLETED

Order:
CREATED → SUBMITTED → PENDING
    ├── PARTIALLY_FILLED → PARTIALLY_FILLED / FILLED
    ├── CANCELLED / REJECTED / EXPIRED
    └── ambiguous side effect → RECOVERY_REQUIRED

Trade:
PENDING_ENTRY
    ├── first non-zero opening fill → ACTIVE_POSITION
    └── entry terminal with zero fill → ENTRY_TERMINATED
ACTIVE_POSITION
    ├── partial opening/exit fill with qty > 0 → ACTIVE_POSITION / EXIT_IN_PROGRESS
    └── final SELL fill with qty = 0 → CLOSED
```

Partial-fill contract：

- Order schema 從 v1 就允許 `PARTIALLY_FILLED`，即使 current local paper adapter 仍是
  all-or-none。
- 第一筆 non-zero opening fill 建立 exposure、`trade_id`、TradeThesis，並固定
  `filled_at`／entry reference price。
- 同一 opening order 的後續 partial fills 更新 position average price，但不重設 thesis
  clock；它們不算 scale-in。
- Active position 之後新建第二張 BUY order 才是 scale-in，v1 fail closed。
- Partial SELL 讓 trade 進 `EXIT_IN_PROGRESS` 或維持有 exposure；只有 quantity 歸零才
  `CLOSED` 並更新 loss streak。
- 本 plan 不啟用 future exit order transport，但先凍結 Order state 供 Replay／未來 Shioaji
  callback 使用。

### 9.2 Exit legs and trade-level analytics

同一 trade 可以有多個 exit reasons，不能只在 trade row 留一個字串：

```python
@dataclass(frozen=True)
class ExitLeg:
    fill_id: str
    order_id: str
    exit_recommendation_id: str | None
    reason: ExitReason
    quantity_shares: int
    fill_price: Decimal
    filled_at: datetime


@dataclass(frozen=True)
class TradeOutcome:
    trade_id: str
    exit_legs: tuple[ExitLeg, ...]
    initiating_exit_reason: ExitReason
    closing_exit_reason: ExitReason
    realized_pnl: Decimal
    pnl_basis: str
    closed_at: datetime
```

- `initiating_exit_reason` 是第一個實際降低部位的 SELL fill reason。
- `closing_exit_reason` 是讓 quantity 歸零的 final fill reason。
- 統計另以 `reason → quantity／realized PnL` breakdown 計算，不用多數決覆蓋原始 legs。
- Manual partial SELL 使用 `MANUAL`；由 recommendation 產生的 SELL 保存
  `exit_recommendation_id` 與其 enum reason。

### 9.3 Journal record kinds

沿用 `trading.journal.JournalRecord`，新增 typed payload builder／reader：

| Kind | 何時寫入 | 重要 identity |
|---|---|---|
| `trade_thesis_draft.v1` | entry decision／manual draft 通過 validation | thesis_id、thesis_type/version、decision_id |
| `trade_thesis_activated.v1` | opening fill | thesis_id、thesis_type/version、trade_id、fill_id、filled_at、fill_time_source |
| `thesis_state_changed.v1` | status/reasons transition | thesis_id、source_event_id |
| `exit_recommendation_created.v1` | first action=EXIT decision | recommendation_id、trade_id、first_trigger_event_id |
| `exit_recommendation_updated.v1` | primary/all reason transition | recommendation_id、decision_id、source_event_id |
| `exit_recommendation_resolved.v1` | final closing fill | recommendation_id、trade_id、closing_fill_id |
| `local_paper_fill.v2` | immediate 或 delayed fill | fill_id、order_id、trade_id、thesis_id、filled_at、fill_time_source、source_event_id、exit_reason |
| `trade_closed.v1` | position lifecycle fully closes | trade_id、exit-leg breakdown、gross/net basis、closed_at |
| `trading_guard_state_changed.v1` | block/release reason set 改變 | session_date、policy_version |
| `pending_entry_blocked.v1` | guard 在 pending BUY fill 前重新擋下 | order_id、guard reason |

PR-TM-002 只實作目前已凍結、可獨立重建的 fact kinds：`trade_thesis_draft.v1`、
`trade_thesis_activated.v1`、三種 exit recommendation lifecycle records 與
`trade_closed.v1`。`thesis_state_changed.v1`、fill v2、guard records 與任何 runtime event sink
仍屬後續行為 PR，不得由本 Journal integration 提前產生。

`ENTRY`、`EXIT` 不另做含糊 enum：

- ENTRY fact = opening fill／thesis activated。
- THESIS_VALIDATED／WARNING／INVALID = thesis state transition。
- EXIT recommendation fact = one `exit_recommendation_created.v1` plus zero or more reason-priority
  updates，最後由 closing fill resolve。
- EXIT fact = closing SELL fill + `trade_closed.v1`。

### 9.4 Fill event cutover

`local_paper_fill.v1` 已存在，不能原地更改 schema：

1. reader 暫時 dual-read v1／v2。
2. new writer 在 feature flag 下寫 v2。
3. delayed quote-triggered fill 與 immediate fill 必須共用一個 terminal event sink。
4. 同一 fill 的 retry 以 fill identity idempotent；不得因 command recorder 與 quote worker
   各寫一次而重複加倉。
5. parity test 證明 legacy simulation projection 與 Journal-derived projection 相同後才切換。

### 9.5 Backward compatibility and enum evolution

Trade Management Journal 採 fail-closed、append-only 相容政策：

1. 已發布的 `trade-management-v1` JSON shape、field name/type 與既有 enum wire value／語意
   永久不原地修改。
2. Reader 以 outer `schema_version` 選擇；v1 reader 必須長期保留。新 schema 以並存 reader
   加入，不把 v1 reader 改成猜測或 fallback。
3. 舊 Journal record 不覆寫、不就地 migration。需要新 projection shape 時，從原始 record
   重建新 projection；需要 materialized migration 時，寫入有 lineage/digest 的新 artifact。
4. v1 reader 對未知 schema、field、enum、serializer version 與 digest mismatch 全部 fail
   closed；不得把未知值默認成 `VALID`、`MANUAL` 或其他既有語意。
5. Enum 採 append-only evolution：允許新增新名稱／wire value，但只能在明確的新 schema 或
   consumer capability gate 後寫出。既有名稱不得 rename、reuse、改值或改變業務含義；停用值
   仍保留歷史讀取能力。
6. Deprecated field／enum 必須先有 reader retention 與 replay evidence；顯示文案可修改，
   wire identity、Journal fingerprint 與歷史統計分類不得跟著變。
7. Decimal wire value 一律是 plain JSON string：移除非必要小數尾零、`-0` 正規化為 `0`、
   禁止 exponent artifact。Writer 主動 canonicalize；reader 對非 canonical artifact fail closed，
   不做 silent repair。
8. `JournalRecord.payload_bytes` 是建構時產生的 authoritative immutable artifact；`payload`
   只提供 recursively immutable compatibility view。Fingerprint 與 persistence 只讀 frozen
   canonical snapshot，不重新序列化 caller-owned mutable object。

## 10. Trading Guard

建議新增 `trading/guard.py`，但 enforcement 仍由 `RiskGate` 與 local-paper fill gate 執行。

### 10.1 Policy

```python
@dataclass(frozen=True)
class TradingGuardPolicy:
    version: str
    max_daily_realized_loss: Decimal
    max_consecutive_losses: int
    cooldown: timedelta
    pnl_basis: Literal["GROSS_SIMULATED", "NET"]
    timezone: str = "Asia/Taipei"
```

初始 example config 可為：

```text
max_daily_realized_loss = 5000
max_consecutive_losses = 3
cooldown = 30 minutes
```

但正式預設值必須在 Phase 0 review 後凍結成 config version；不散落在 rule／UI。

### 10.2 Projection

```python
@dataclass(frozen=True)
class TradingGuardState:
    session_date: date
    consecutive_losses: int
    daily_realized_pnl: Decimal
    closed_trade_count: int
    cooldown_until: datetime | None
    blocked_reasons: tuple[str, ...]
    last_closed_trade_id: str | None
    policy_version: str
    last_journal_sequence: int
```

Reducer：

- closed trade PnL `< 0` → streak +1。
- closed trade PnL `>= 0` → streak reset 0；breakeven 不算 loss。
- streak 到 3 → `cooldown_until = closed_at + 30m`。
- `daily_realized_pnl <= -limit` → block 到下一個有效 trading session；不因 30 分鐘到期解除。
- session 切換時 streak／daily PnL／count 依 policy reset；舊 session event 不得污染新 session。
- duplicate `trade_closed` 不得再加一次。

### 10.3 Enforcement points

需要兩次 guard check：

1. BUY command submission 前：既有 `RiskGate.evaluate()`。
2. pending BUY 實際 fill 前：防止 order 在提交後、三連敗或 daily loss 啟動後才成交。

Guard activation：

- 阻擋 manual 與 future strategy BUY。
- 不阻擋 SELL、cancel、query、recovery、reconciliation。
- 既有 pending BUY 由同一 local-paper mutation boundary 原子性取消／quarantine，寫入
  `pending_entry_blocked.v1`。
- 不自動取消 pending SELL。
- `RiskReason` 增加 `CONSECUTIVE_LOSS_COOLDOWN`、`ACTIVE_THESIS_POSITION`；既有
  `DAILY_LOSS_LIMIT` 保留。

目前 `RiskGate` 的 data／daily blockers 要拆成：

- entry guards：daily loss、consecutive loss、strategy-origin entry disabled、duplicate entry。
- common order validation：price、quantity、notional、position availability。
- exit execution safety：仍驗證 quantity／book capability，但不可因「今天已虧損」拒絕 SELL。

### 10.4 PnL basis

local paper 目前不含 fee／tax，第一階段只能誠實標示 `GROSS_SIMULATED`。不得把 gross
`-5000` 描述成真實 net daily loss。若未來以 NET enforcement，必須先接 versioned cost
model，並用 closing-trade net PnL 更新 state。

### 10.5 Persistence gate

- In-memory Journal：guard 只能標為 process-session preview；Dashboard 顯示重啟會清空。
- `TRADING_GUARD_ENFORCING=true`：runtime 必須使用 durable Journal、完成 replay 與
  checkpoint validation；不得 silent fallback 到 in-memory。

## 11. Application integration

### 11.1 Local paper

在 `runtime/composition.py` wiring：

```text
canonical market context
        ↓
ThesisApplicationService
        ↓
ThesisStateProjection / ExitRecommendationProjection

local_paper_fill.v2
        ↓
TradeLifecycleProjection
        ↓
TradingGuardProjection
        ↓
RiskSnapshot / PendingEntryFillGate
```

新增 application service 只依賴 ports：Journal、ProjectionRepository、Clock、market
context reader。FastAPI route 不直接 new monitor／guard。

### 11.2 Backtest／Replay

1. ORB entry evaluation 建 `TradeThesisDraft`。
2. next eligible opening fill activate thesis。
3. completed bars 經同一 pure monitor adapter 評估。
4. Thesis exit 與現有 Stop Loss／Take Profit／Time Stop 聚合。
5. report 保存 thesis status timeline、primary exit reason、duration、gross/net PnL。
6. 同 dataset 重跑，thesis／exit decision digest 必須一致。

Backtest 不模擬心理 guard 的「更好績效」來替策略背書。Guard-enabled run 必須另存
policy version，並與 baseline 分開比較 trade count、blocked entries、drawdown。

### 11.3 Canonical market pipeline dependency

Realtime full ORB profile 需要：ordered Tick／BidAsk、completed 1m bar、VWAP、volume
baseline、DataHealth、deadline control event。若 P1 canonical market-event pipeline 尚未完成：

- domain／Journal／backtest phases 可先做。
- local paper 只能 preview 已有可靠 input 的 condition。
- 缺少 volume／VWAP 不可用 snapshot 猜值；回傳 `INSUFFICIENT_DATA`。
- 不建立第三個 queue、callback owner 或 recent-event store 作臨時捷徑。

### 11.4 Historical Tick Replay contract

Simulation validation 必須支援真正的 Historical Tick／BidAsk Replay，而不是把一分鐘
Kbar 拆成 synthetic ticks。Replay input 沿用 canonical `EventEnvelope`：

- `event_id`、`schema_version`、`session_id`、`session_date`。
- `source`、`source_mode`、`stream_kind`。
- `symbol`、`event_at`、`received_at`、`ingress_sequence`。
- `source_identity`、immutable payload、raw capture／manifest identity。

Replay dataset manifest 至少包含：

```text
dataset_id
schema_version
session_date / timezone
symbols / stream kinds
capture source and mode
first_event_at / last_event_at
event_count by stream
known gaps / reconnect epochs / data-health disposition
ordered source artifact SHA-256
```

Replay run identity 必須固定所有會影響輸出的輸入：

```python
@dataclass(frozen=True)
class ReplayRunIdentity:
    manifest_sha256: str
    canonical_event_schema_version: str
    strategy_id: str
    strategy_version: str
    thesis_type: ThesisType
    thesis_version: str
    exit_policy_version: str
    guard_policy_version: str
    fill_model_version: str
    code_identity: str
    serializer_version: str
```

Determinism contract：

```text
same ReplayRunIdentity + same ordered canonical events
    ⇒ same state transitions
    ⇒ same timestamps / IDs / ExitReasons
    ⇒ same canonical Journal sequence
    ⇒ same final digest
```

Replay rules：

1. 只讀 immutable artifact；不呼叫網路、Provider snapshot、Shioaji SDK 或 system clock。
2. `ReplayClock` 推進 market time並產生 deterministic deadline control event。
3. Tick 與 BidAsk 保留各自 source order；不依 timestamp 建立虛假的 cross-stream total order。
4. accepted events 走與 Shadow 相同的 projection → ThesisMonitor path。
5. 缺 Tick、BidAsk、volume、VWAP baseline 或 manifest gap 時產生
   `INSUFFICIENT_DATA`／DataHealth disposition，不補 synthetic values。
6. 同 manifest 重跑至少十次，thesis transition、exit recommendation、trade lifecycle、
   guard state 與 Journal digest 必須完全一致。
7. 一分鐘 Kbar backtest 是另一種 resolution profile；可以做研究比較，但不能宣稱與
   Historical Tick Replay event-for-event parity。
8. Replay path 禁止 runtime UUID、random seed、unordered set/dict iteration、ambient timezone、
   `datetime.now()` 或 thread scheduling 決定 business result；所有 business IDs 由 stable
   input identity hash 產生。
9. canonical output digest 只包含 domain/Journal contract fields；host path、PID、wall-clock
   duration 等 runtime metadata 不得污染 digest。
10. 同一 manifest 若得到不同 recommendation time（例如一次 09:15:02、一次
    09:15:03），Gate 立即失敗並保存 first divergence event/sequence。

Phase 5 前若沒有合格 Historical Tick artifact，Simulation gate 維持 blocked；不能只用
MockProvider happy path 宣告通過。

## 12. Dashboard/API plan（P2）

### 12.1 Projection schema

擴充 `/api/simulation/projection`：

```json
{
  "session": {
    "trading_guard": {
      "mode": "PREVIEW",
      "status": "COOLDOWN",
      "consecutive_losses": 3,
      "daily_realized_pnl": -3200,
      "pnl_basis": "GROSS_SIMULATED",
      "cooldown_until": "2026-08-20T10:15:00+08:00",
      "blocked_reasons": ["CONSECUTIVE_LOSS_COOLDOWN"]
    }
  },
  "positions": [
    {
      "symbol": "2330",
      "trade_id": "...",
      "thesis": {
        "thesis_type": "ORB_BREAKOUT",
        "thesis_version": "v1",
        "status": "WARNING",
        "entry_price": "600",
        "filled_at": "...",
        "reasons": [],
        "conditions": [],
        "exit_decision": "HOLD"
      }
    }
  ]
}
```

Money／threshold source of truth 用 Decimal string；browser 只格式化。

### 12.2 UI

修改：

- `dashboard/static/index.html`：order ticket 的 thesis definition／reason 區、guard banner。
- `dashboard/static/js/workspaces/simulation.js`：渲染 thesis、conditions、decision、guard；
  BUY 被 guard 擋住時 disabled 並顯示 server reason。
- `dashboard/static/js/workspaces/candidates.js`：Candidate 開單帶 server-issued draft identity。
- `dashboard/static/css/dashboard.css`：VALID／WARNING／INVALID／資料不足樣式。

繁中顯示例：

```text
2330 台積電
進場：600.00／09:31:00
交易假設：開盤區間突破 v1（實驗中）

✓ 突破價仍守住
✓ 維持 VWAP 上方
! 量能尚未擴張

狀態：警告
決策：續抱；10:36 前未創新高則建議退出
```

UI 不顯示「AI 決定」，也不把 WARNING 當 EXIT。`INSUFFICIENT_DATA` 顯示原因與
資料時間。

## 13. Implementation phases

### Phase 0 — Contract Freeze（P0）

目標：先凍結會決定所有下游模組的 identity、version、state machine 與 rule semantics。

工作：

1. 凍結 `TradeThesisDraft`、`TradeThesis`、`DecisionLifecycleState`、
   `OrderLifecycleState`、`TradeLifecycleState`、`ExitReason`、`ExitLeg`、`ThesisStatus`、
   `ExpectedBehaviorPolicy`、`InvalidConditionSpec` schema v1。
2. 明確區分 `schema_version`、`strategy_version`、`thesis_version`，定義 immutable
   `ORB_BREAKOUT/v1`。
3. 凍結 breakout level、new-high buffer、VWAP confirmation、volume baseline/ratio、
   warning/deadline boundary。
4. 凍結 canonical `event_at`、ingress `received_at`、authoritative `filled_at`、
   `FillTimeSource` 與 Journal `sequence` 的單一語意。
5. 凍結 exit priority、same-bar conservative rule、`INSUFFICIENT_DATA` semantics。
6. 分開 per-event `ExitDecision` 與 per-trade `ExitRecommendation`；凍結每個 `trade_id`
   同時最多一個 ACTIVE recommendation 的 invariant。
7. 凍結 `trade_id` lifecycle、partial SELL exit legs、breakeven、session reset、PnL basis。
8. 凍結 canonical event／Historical Tick manifest／`ReplayRunIdentity`／ReplayClock／output
   digest contract。
9. 凍結 `ThesisMonitor` pure boundary；Position、Order、RiskState、Journal 與 projection mutation
   只能在 monitor 之外發生。
10. 建立至少四個 immutable fixture：VALID、WARNING→INVALID、immediate hard INVALID、
    600→599→598 repeated INVALID recommendation idempotency。
11. 決定 feature flags 與初始全部-off defaults。

Gate G0：Section 20 全部 checkbox 有 contract／fixture／test evidence；沒有未定義的
`require_* = True` boolean、free-form exit reason、混用 version、wall-clock business output、
重複 active recommendation 或 monitor hidden mutation。`PR-TM-001` merge 前不得開始
`PR-TM-003 ThesisMonitor`。

### Phase 1 — Journal and Trade Lifecycle Integration（P0）

目標：先讓 entry、fill、partial exits、close 與 thesis activation 可以被完整記錄／重建。

工作：

1. 新增 Phase 0 domain dataclasses、validation、serializers／readers。
2. 新增 v2 fill record、dual reader、`trade_id` lifecycle reducer、exit-leg projection。
3. 補齊 immediate／delayed local-paper fill 的單一 terminal event sink。
4. 建立 thesis draft／activation／termination Journal events。
5. 新增 thesis／trade projections 與 checkpoint digest；此 phase 不執行 monitor rule。
6. Runtime feature flag off 時保持現有 API、UI、fill 行為。

Gate G1：Journal replay 可重建相同 thesis identity、position lifecycle、partial exit legs、
closed-trade outcome；legacy／v2 fill parity 通過且 delayed fill 不漏記。

### Phase 2 — Thesis Monitor, Status Only（P0）

目標：只回答 thesis 是 VALID／WARNING／INVALID／INSUFFICIENT_DATA，不產生 order 或
Exit Recommendation。

工作：

1. 新增 thesis-definition registry 與 ORB entry evidence mapping。
2. 實作 typed condition evaluators、status aggregation 與 INVALID latch。
3. 實作 deadline control event 與 injected System/Replay clock。
4. 對 duplicate、out-of-order、stale、session mismatch、missing inputs fail closed。
5. Journal 只寫 status/reason transition，不為每個 Tick 寫 transition event。
6. 在 pure fixtures 與 bar-resolution adapter 驗證，不接 local-paper auto action。

Gate G2：Thesis status boundary tests 全部通過；同 fixture 10 次結果一致；搜尋不到任何
從 monitor 直接呼叫 OrderApplicationService、SimulationService 或 broker adapter 的路徑。

### Phase 3 — Exit Recommendation（P0）

目標：把 structured thesis status 與現有 price/time exits 聚合成唯一、可稽核、
decision-only recommendation。

工作：

1. 實作 `ExitDecisionEngine`、stable `ExitReason`、priority 與 legacy Stop/Take adapters。
2. WARNING／INSUFFICIENT_DATA 不自動轉成 EXIT；INVALID／TIME_DECAY 依 frozen policy 決定。
3. ORB backtest activation／monitor／recommendation end-to-end。
4. 保存 thesis timeline、all triggered reasons、primary reason 與 decision id。
5. Local-paper projection 顯示 recommendation；不產生 SELL command。
6. 確認 browser polling 不驅動 monitor 或 deadline。

Gate G3：VALID→WARNING→INVALID→EXIT recommendation 可重播；同一 `trade_id` 同時最多一個
ACTIVE recommendation；Journal、code search 與 handler spy 證明沒有 order side effect。

### Phase 4 — RiskGate and Trading Guard Integration（P1）

目標：closed-trade outcome 更新 account/session guard；阻擋新 BUY，但保留所有風險降低
SELL 能力。

工作：

1. 實作 `TradingGuardProjection` 與 policy v1。
2. 擴充 RiskSnapshot／RiskGate reason 與 entry-only branch。
3. pending BUY fill 前重新檢查 guard，原子取消／quarantine。
4. 加入 daily loss、three-loss cooldown、session reset、durable restart replay。
5. 定義 future exit command 如何攜帶 `recommendation_id`／`ExitReason` 經 RiskGate validation；
   此 phase 仍不啟用自動 SELL。
6. `PREVIEW` 先觀察 transition；durable Journal gate 通過才可 `ENFORCING`。

Gate G4：loss/loss/loss 觸發 30 分鐘、win/breakeven reset、daily loss 持續到下一
session、restart 不繞過、SELL/cancel 不被擋、pending BUY 不偷成交。

### Phase 5 — Simulation and Historical Tick Replay Validation（P0/P2）

目標：用 immutable Historical Tick／BidAsk、local paper 與使用者可見 projection 驗證
完整生命週期；不是績效 promotion gate。

工作：

1. Historical Tick manifest 經 canonical Replay pipeline 驅動 ThesisMonitor／Recommendation。
2. 同 manifest 至少重跑十次，比對 thesis transition、exit decision、trade lifecycle、
   guard、Journal digests。
3. 驗證 partial SELL 不同 `ExitReason`、delayed fill、pending BUY race、disconnect、stale、
   queue overflow、deadline scheduler 與 shutdown drain。
4. 對照一分鐘 Kbar profile，明確標示 resolution difference，不製造 synthetic ticks。
5. `/api/simulation/projection` 加入 thesis／exit／guard read model。
6. P2 Dashboard 加入 thesis definition/version、condition、deadline、exit-leg reasons、guard
   banner；前端不重算規則。
7. 完成 API contract、frontend module、accessibility、MockProvider 與 browser smoke tests。
8. README 說明 decision-only、Historical Tick source、restart/persistence、非真錢邊界。

Gate G5：合格 Historical Tick artifact 與完整 local-paper lifecycle 通過；UI reload、drawer、
candidate prefill、blocked BUY、allowed SELL、warning/invalid/insufficient-data interactions
全部通過。只有 MockProvider happy path 不足以通過 G5。

### Phase 6 — Controlled Shadow Rollout（P1）

目標：在 production-like realtime data 上做 decision-only Shadow 觀察。此處 rollout 不表示
Production Trading，也不開啟 Shioaji order、auto SELL 或 real money。

工作：

1. metrics／structured logs／Journal review report。
2. 量測 condition availability、warning/invalid frequency、time-to-invalid、exit reason／
   exit-leg distribution。
3. 驗證 reconnect、queue overflow、stale、shutdown drain、live-to-replay parity。
4. review ORB thesis thresholds；若調整，新增 `thesis_version`，不覆寫 v1。
5. 至少累積預先定義的 Shadow sample／session 數，再 review false-invalid 與人工 disposition。
6. 任何 local-paper auto-SELL、Shioaji Simulation 或 production execution 都需新的明確
   scope、風險 review 與 authorization；本 phase 不開啟。

Gate G6：Shadow evidence review 完成，沒有 silent missing data、duplicate decision 或
guard bypass；仍不代表策略績效通過，也不授權 execution rollout。

## 14. File-level change map

### New

```text
config/trade_management.py
trading/thesis.py
trading/thesis_builder.py
trading/thesis_monitor.py
trading/time_exit.py
trading/exit_decision.py
trading/exit_recommendation.py
trading/trade_lifecycle.py
trading/guard.py
trading/trade_events.py
backtest/thesis_adapter.py
tests/fixtures/trade_management/*.json
tests/test_trade_thesis.py
tests/test_thesis_builder.py
tests/test_thesis_monitor.py
tests/test_thesis_monitor_purity.py
tests/test_trade_management_timestamps.py
tests/test_time_decay_exit.py
tests/test_exit_decision.py
tests/test_exit_recommendation_idempotency.py
tests/test_trade_lifecycle.py
tests/test_trading_guard.py
tests/test_trade_management_replay.py
tests/test_trade_management_tick_replay.py
tests/test_trade_management_dashboard.py
```

### Modify

```text
trading/risk.py                         # entry-only guard reasons/snapshot
trading/application.py                  # thesis/guard evidence at command boundary
trading/local_paper.py                  # v1/v2 fill reader, trade linkage projection
simulation/models.py                    # optional draft/trade/thesis identity
simulation/service.py                   # terminal event sink, pre-fill guard check
simulation/application.py               # draft validation and command provenance
simulation/application_adapter.py       # carry approved identity without new business logic
runtime/composition.py                  # one service/projection wiring point
market_data/replay.py                   # canonical Historical Tick replay path
backtest/domain.py                      # thesis/exit evidence in result contracts
backtest/engine.py                      # activate/evaluate thesis in existing event loop
backtest/strategies.py                  # registry binding, no duplicate formulas
strategy_catalog/service.py             # experimental thesis exit metadata
dashboard/server.py                     # request/response projection only
dashboard/static/index.html             # thesis/guard layout
dashboard/static/js/workspaces/candidates.js
dashboard/static/js/workspaces/simulation.js
dashboard/static/css/dashboard.css
README.md
```

### Keep unchanged initially

```text
candidate/engine.py
scoring/engine.py
market_data/provider.py
position/manager.py
```

`position/exit_rules.py` 只做 compatibility adapter 所需的最小修改；不把 thesis／Journal
塞進 rule。

## 15. Test plan

### 15.1 Thesis model／builder

- naive datetime、空 version、非正 price、symbol mismatch fail closed。
- same decision retry 產生同 thesis id。
- cancelled/rejected opening order 不啟用 thesis。
- fill price/time 覆蓋 order limit/submission time。
- schema／strategy／thesis version 分開保存；unknown thesis version fail closed。
- Candidate／score reasons 可保存，但沒有 thesis-definition mapping 時不可執行 invalidation。
- active thesis position 的第二次 BUY 被擋。
- Historical Tick fill 使用 triggering event `event_at`；submission／receipt time 不得啟動 thesis。
- 同 opening order 後續 partial fills 不重設 `filled_at`／deadline。
- 缺 `filled_at`／`FillTimeSource`／conditional provenance 時 activation fail closed。

### 15.2 Thesis Monitor

- 價格跌破 breakout：`INVALID`。
- 價格剛好等於 breakout：依 `<` contract 不 invalid。
- 五分鐘前創新高＋量能擴張＋守 VWAP：`VALID`。
- warning boundary 未創高／量未增：`WARNING`。
- exactly deadline 未滿足：`INVALID EXPECTED_BEHAVIOR_EXPIRED`。
- VWAP／volume baseline missing：`INSUFFICIENT_DATA`。
- stale／out-of-order／session mismatch：fail closed，不更新 highest price。
- INVALID 後反彈：仍 INVALID latch。
- duplicate event：projection 與 Journal sequence 不變。
- 相同 frozen thesis/context 重跑得到 byte-equivalent evaluation。
- mutation spies 證明 Position、Order、RiskState、Journal 與 projection 在 evaluate 前後不變。
- monitor import/dependency boundary 不可取得 repository、callback、network 或 filesystem。

### 15.3 Exit decision

- Stop only、thesis only、time only、take profit only。
- Stop + thesis + take 同時成立：primary Stop，全部 reasons 保留。
- WARNING 不 EXIT。
- 同 market event retry 不新增 decision。
- exit decision 與 closing fill 分開；未 fill 時 trade 仍 open。
- enum wire value 穩定；繁中文案修改不改 Journal fingerprint。
- partial SELL 可保存 THESIS_INVALID／TAKE_PROFIT／TIME_DECAY 等不同 exit legs。
- 600→599→598 repeated INVALID 產生三個可稽核 decision，但只建立一個 ACTIVE
  recommendation。
- 後續 Stop Loss 只更新同一 recommendation 的 primary/all reasons；quantity 歸零才 resolve。
- future SELL command key fixture 只由 `recommendation_id` 衍生。

### 15.4 Trade lifecycle／Trading Guard

- loss／loss／loss → cooldown block。
- loss／win → streak 0。
- loss／breakeven → streak 0。
- partial SELL loss 不先增加 streak；fully close 才更新一次。
- duplicate close event 不重複計數。
- daily PnL exactly `-5000` 命中 `<=` limit。
- cooldown exactly `until` 時解除；daily loss 不解除。
- Asia/Taipei session 切換 reset；舊 session late event rejected。
- process restart 由 durable Journal 重建相同 state。
- guard block BUY，但 SELL／cancel／recovery 仍 allowed。
- guard 啟動前已存在的 pending BUY 不會在下一個 quote 偷成交。

### 15.5 Historical Tick Replay／Backtest

- canonical Historical Tick manifest 同跑 10 次 thesis／decision／trade/guard digest 相同。
- 相同 ReplayRunIdentity 精確產生相同 09:15:02 recommendation time、stable IDs、
  ExitReasons、Journal sequence 與 canonical digest。
- 故意改變一個 ordered event 時，divergence report 指向第一個不同 event／sequence。
- Replay 不呼叫 network、Provider snapshot、Shioaji SDK 或 system clock。
- Tick／BidAsk source order 被保留，不建立假的 cross-stream timestamp total order。
- manifest gap／缺 stream／缺 volume evidence 產生 `INSUFFICIENT_DATA`，不補 synthetic tick。
- completed-bar deadline resolution 有明確 evidence。
- 無 same-bar look-ahead。
- thesis exit 加入後 baseline run 不在 flag off 時改變。
- bar backtest 與 Historical Tick Replay 清楚標示 resolution，只有相同 input resolution
  才要求 event-for-event parity。

### 15.6 API／frontend

- Feature flag off 保持現有 request schema 與 projection。
- Thesis-required BUY 缺 draft → 422 stable reason。
- Guarded BUY → 409／risk-block response；SELL success path 不變。
- Decimal string、aware timestamps、reason codes contract test。
- JS syntax/module ownership check。
- Browser smoke：candidate prefill、warning、invalid、insufficient data、cooldown、reload。
- `PROVIDER=mock` 測試不初始化 Shioaji native SDK。

### 15.7 Suggested verification commands

```text
.venv/bin/python -m pytest tests/test_trade_thesis.py \
  tests/test_trade_management_timestamps.py tests/test_thesis_monitor.py \
  tests/test_thesis_monitor_purity.py tests/test_exit_decision.py \
  tests/test_exit_recommendation_idempotency.py tests/test_trade_lifecycle.py \
  tests/test_trading_guard.py tests/test_trade_management_tick_replay.py -q

.venv/bin/python -m pytest tests/ -q
.venv/bin/python -m compileall -q trading simulation backtest dashboard tests
.venv/bin/python scripts/check_dashboard_js.py
git diff --check
```

## 16. Observability

至少提供：

- active theses count by thesis type/version/status。
- condition input availability／insufficient-data count。
- VALID→WARNING→INVALID transition count。
- active／created／updated／resolved recommendation count by primary/all reasons。
- evaluation lag、deadline scheduler lag。
- duplicate/out-of-order rejected count。
- closed trade outcomes、consecutive loss、daily PnL basis。
- guard activation/release、blocked BUY、pending BUY cancelled count。
- replay projection digest／checkpoint sequence。

Log／Journal 不記 credential、CA、account secret；reason code stable，顯示文案可翻譯。

## 17. Rollout and rollback

### Feature flags

```text
TRADE_THESIS_CAPTURE_ENABLED=false
THESIS_MONITOR_ENABLED=false
THESIS_EXIT_DECISION_ENABLED=false
TRADING_GUARD_PREVIEW_ENABLED=false
TRADING_GUARD_ENFORCING=false
TRADE_THESIS_REQUIRED=false
TRADE_MANAGEMENT_SHADOW_ENABLED=false
```

開啟順序不可跳級：capture → monitor preview → exit decision preview → guard preview →
durable guard enforcing。

### Rollback

- 關閉 monitor／guard flags，保留 Journal records，不刪資料。
- API dual-read 舊／新 projection；writer 回到 v1 前先確認沒有 v2-only active lifecycle。
- Dashboard 無 thesis 欄位時回到現有 position/order rendering。
- projection 可由 Journal 重建；digest mismatch 時 fail closed 並停止新 BUY。
- rollback 不得清除 cooldown 或 daily-loss evidence。

## 18. Definition of Done

本 milestone 只有在以下全部成立才算完成：

1. 每個 thesis-managed opening fill 可回溯到 decision、entry evidence、strategy version、
   thesis type/version、actual fill、active thesis。
2. Thesis Monitor 不依賴 wall clock、browser polling、Shioaji SDK 或 latest-only snapshot。
   Evaluate 前後的 Position、Order、RiskState、Journal 與 projection 亦完全不變。
3. ORB VALID／WARNING／INVALID／INSUFFICIENT_DATA fixtures 可在 unit、backtest、Historical
   Tick Replay 的對應 resolution profile 得到 deterministic 結論。
4. Exit priority deterministic；同 source event decision idempotent，且每個 trade 同時最多一個
   ACTIVE exit recommendation。
5. `event_at`、`received_at`、`filled_at` 與 Journal `sequence` 沒有替代或 fallback；Thesis
   deadline 只由 first exposure fill 的 authoritative `filled_at` 計算。
6. Delayed local-paper fills 與 immediate fills 都有 idempotent Journal evidence。
7. `trade_id` fully-close semantics 正確，partial SELL／duplicate 不會污染 loss streak。
8. 每個 partial SELL exit leg 都保存 stable `ExitReason`、quantity、fill 與 recommendation
   provenance。
9. 三連敗 cooldown、daily loss、pending BUY fill gate、SELL bypass 全部通過。
10. Enforcing guard 沒有 durable Journal 時 fail closed，不假裝 restart-safe。
11. 相同 `ReplayRunIdentity` 與 ordered Historical Tick events 重跑十次，timestamp、IDs、
    reasons、Journal sequence 與 digest 完全一致；缺口不被 synthetic data 掩蓋。
12. Dashboard 顯示繁中 reason、deadline、data status、PnL basis；前端不重算規則。
13. Feature flags 關閉時現有 Candidate、Dashboard、local paper、backtest regression 全部通過。
14. README 明確說明 local paper／decision-only／非 Shioaji 下單／非真錢。
15. 沒有新增 broker order、CA、real-money mode 或隱性自動 SELL。

## 19. 建議開工順序

最小、可 review 的 PR 切法：

1. **PR-TM-001 — Phase 0 contracts and fixtures**：version taxonomy、三個 state machines、
   timestamp source、enum／ExitLeg、recommendation idempotency、Replay identity/digest、pure
   monitor boundary與 immutable fixtures；無 runtime wiring。
2. **PR-TM-002 — Journal Integration**：strict v1 readers、typed Journal records、deterministic
   identity/digest、checkpoint 與 replay reconstruction；無 fill sink 或 runtime wiring。
3. **PR-TM-003 — Thesis Monitor status only**：pure evaluator、typed status evidence；無 persistence、projection 或 recommendation。
4. **PR-TM-004 — Exit Recommendation**：pure Thesis reason mapping、decision、one active
   recommendation；無 adapter、persistence 或 auto SELL。
5. **PR-TM-005 — RiskGate Exit Eligibility**：pure recommendation eligibility、entry-only RiskGate
   branch correction；無 command、persistence 或 execution。
6. **PR-TM-006 — Simulation/Tick Replay validation**：canonical Historical Tick artifacts、
   ThesisEvaluation／ExitRecommendation／ExecutionEligibility chain、deterministic digests；無
   Journal write、Shadow 或 execution。
7. **PR-TM-007 — Shadow Decision Pipeline**：live canonical event consumer、immutable Shadow
   Decision Record、per-event RiskSnapshot 與 live-to-replay parity；無 Journal write 或 execution。
8. **PR-TM-008 — Durable Shadow Evidence**：既有 Journal、strict evidence facts、restart replay、
   checkpoint 與 retain-all policy；無 trade authority。
9. **PR-TM-009 — Live Runtime Composition／Shadow Operation**：正式 canonical market pipeline、
   decision-only Shadow、durable evidence 與 finalize checkpoint；無 execution。
10. **PR-TM-010 — Shadow Observability／Production Readiness Gate**：health、backpressure、
    evidence completeness、parity rate 與 deterministic readiness report；仍無 execution。
11. **PR-TM-011 — Extended Shadow Validation／Operational Readiness**：live source identity、完整
    session／跨日 evidence、checkpoint recovery、failure drills 與 deterministic validation report；
    測試證據不可冒充 real-market evidence，仍無 execution。
12. **PR-TM-012 — Real Shadow Evidence Collection**：A 先建立 local-paper fill → authoritative
    TradeThesis activation 與 provenance；B 再執行完整 real-market session、durable evidence、
    replay/readiness report。Production Shadow Gate 未有真實證據前保持 NOT PASSED。
13. **PR-TM-013 — Durable guard enforcement**：persistence、restart recovery、checkpoint gate。
14. **PR-TM-014 — Dashboard**：繁中 UI、browser smoke、README。
15. **PR-TM-015 — Controlled Shadow operations**：production-like multi-session runner、metrics
    exporter／alerts 與正式 evidence collection；仍無 execution。

每個 PR 都必須能獨立 rollback，且不得把 unrelated canonical market pipeline／
institutional-data worktree changes一起提交。

## 20. Phase 0／PR-TM-001 merge checklist

Review disposition：**PR-TM-001 APPROVED／CONTRACT FREEZE PASSED**。

本 PR 只凍結 domain／identity／serialization contracts，沒有 runtime wiring。下列十項是
`PR-TM-001` merge gate；其後的 Journal、Monitor、Guard 與 execution checks 是
`PR-TM-002+` downstream gates，不得為了讓本 PR 看似完成而提前實作或勾選。

### PR-TM-001 Definition of Done

- [x] 所有 v1 wire enums 已凍結，並有 exact-value tests。
- [x] Decision／Order／Trade lifecycle state 與 transition tables 已凍結。
- [x] Timestamp role、`Asia/Taipei` timezone、microsecond precision、source 與 source identity
  已凍結；沒有 domain `datetime.now()`。
- [x] `trade_id` 由 session + first non-zero opening fill identity 決定，retry 相同、不同 fill
  不同。
- [x] Partial exit `ExitLeg`／`TradeOutcome` model 已凍結並保存每腿 reason、quantity、price、
  fill timestamp 與 recommendation provenance。
- [x] Per-event `ExitDecision` 與 per-trade `ExitRecommendation` identities 已分開；
  600→599→598 只得到一個 recommendation identity。
- [x] `ReplayRunIdentity`、required output digests 與 first-divergence metadata 已凍結。
- [x] `TradeThesis`、`ExitRecommendation`、`TradeOutcome`、Replay 與 lifecycle canonical JSON
  format 已由 golden fixtures 凍結。
- [x] Existing tests unaffected：full suite `550 passed, 1 skipped`。
- [x] No trading behavior changed：沒有 ThesisMonitor、exit calculation、RiskGate／Journal／Replay
  engine change、runtime wiring、broker、SELL 或 real-money capability。

Evidence：

```text
tests/test_trade_management_contracts.py
tests/test_trade_management_serialization.py
tests/fixtures/trade_management/v1/*.json

.venv/bin/python -m pytest tests/test_trade_management_contracts.py \
  tests/test_trade_management_serialization.py -q
# 22 passed

.venv/bin/python -m pytest tests/ -q
# 550 passed, 1 skipped
```

### Downstream gates（PR-TM-002+；不屬於本 PR）

### Identity and versioning

- [x] `schema_version`、`strategy_version`、`thesis_version` 的責任邊界已核准。
- [x] `ThesisType` v1 只開 `ORB_BREAKOUT`；`GAP_RVOL` 延後加入。
- [x] `ORB_BREAKOUT/v1` immutable；調整規則只能新增 version。
- [ ] thesis／trade／decision／fill IDs 的 deterministic/idempotent identity 已核准。

### Lifecycle

- [x] Thesis clock 從 opening fill `filled_at` 開始，不從 signal/submission 開始。
- [x] Decision、Order、Trade 三個 state machine 與 correlation IDs 已凍結，不使用混合大 enum。
- [x] Order lifecycle 包含 SUBMITTED／PENDING／PARTIALLY_FILLED／FILLED 與所有 terminal states。
- [ ] 第一筆 opening partial fill 建立 exposure/thesis；後續同 order fills 不重設 clock；
  active position 新 BUY（scale-in）v1 禁止。
- [ ] partial SELL 保持同一 `trade_id`，final SELL 才轉 `CLOSED` 並更新 loss streak。
- [x] `ENTRY_TERMINATED`、`ACTIVE_POSITION`、`EXIT_IN_PROGRESS`、`CLOSED` transition 已核准。

### Canonical timestamps

- [ ] `event_at`、`received_at`、`filled_at`、Journal `sequence` 的唯一語意已凍結。
- [x] Thesis start 只讀 first exposure fill 的 `filled_at`，其他 timestamp 不得 fallback。
- [x] 每筆 fill contract 保存 timestamp source 與 required source identity／provenance。
- [ ] timezone normalization、missing timestamp、clock-skew disposition tests 已完成。

### Thesis status and data

- [ ] `VALID`／`WARNING`／`INVALID`／`INSUFFICIENT_DATA` aggregation priority 已核准。
- [x] breakout exact-equality、VWAP completed-bar confirmation、new-high buffer 已定義。
- [x] volume baseline kind、window、minimum samples、ratio 與 volume unit 已定義。
- [ ] 五分鐘 deadline 的 inclusive boundary與 bar/tick resolution behavior 已核准。

### Exit reasons and priority

- [x] `ExitReason` v1 values 已核准；繁中文案不影響 enum identity。
- [ ] `RISK_GATE` 只保留給 future flatten policy，不用於 entry rejection。
- [x] Stop／ATR／EOD → Thesis Invalid → Time Decay → Take Profit category priority 已核准。
- [x] partial exit legs 的 initiating／closing／breakdown analytics 已核准。

### Recommendation idempotency

- [x] Per-event `ExitDecision` 與 per-trade active `ExitRecommendation` identity 已分開。
- [x] 同一 `trade_id` 同時最多一個 ACTIVE recommendation，有 database/Journal uniqueness
  或等價 fail-closed invariant。
- [x] 600→599→598 repeated INVALID fixture 只建立一次 recommendation identity。
- [x] 更高 priority reason 保持同一 recommendation identity；final close metadata 才 resolve。
- [ ] Future SELL idempotency 只由 `recommendation_id` 衍生，不由最新 Tick 衍生。

### Journal and Replay

- [ ] immediate 與 delayed fill 共用 terminal event sink 的 ownership 已核准。
- [ ] `local_paper_fill.v1` dual-read、v2 write cutover／rollback 已核准。
- [ ] Historical Tick manifest、SHA-256、ReplayClock、source ordering／gap behavior 已核准。
- [ ] 缺資料回 `INSUFFICIENT_DATA`，不得產生 synthetic tick／volume／VWAP。
- [x] `ReplayRunIdentity` 凍結 manifest/config/policy/fill-model/code/serializer versions。
- [ ] Replay 禁止 runtime UUID、wall clock、ambient timezone、unordered iteration 與 thread race
  影響 business output。
- [ ] 同 manifest 10 次產生相同 timestamp、IDs、ExitReasons、Journal sequence 與 digest；
  divergence report 能定位 first differing event。

### No hidden mutation

- [ ] `ThesisMonitor.evaluate(TradeThesis, ThesisMarketContext) -> ThesisEvaluation` signature 凍結。
- [ ] Monitor 只接受 immutable input/config，不注入 Position、Order、Risk、Journal、repository、
  callback、network 或 filesystem capability。
- [ ] Position／Order／RiskState／Journal mutation spies 在 evaluate 前後完全相同。
- [x] Projection reducer 與 Journal persistence 位於 application layer，不藏在 monitor。

### Guard and execution boundary

- [ ] daily loss PnL basis、threshold、three-loss definition、30-minute boundary 已核准。
- [ ] BUY submit 與 pending fill 前都檢查 guard；SELL/cancel/recovery 不被 entry guard 阻擋。
- [ ] enforcing mode 需要 durable Journal，沒有 silent in-memory fallback。
- [ ] Phase 0-6 全程維持 decision-only／local paper；沒有 broker、auto SELL 或 real-money 授權。

### Phase 0 completion summary

- [x] schema／strategy／thesis version definitions frozen。
- [x] Decision／Order／Trade lifecycle states frozen。
- [x] `ExitReason`／`ExitLeg` schemas frozen。
- [x] Canonical timestamp source and Thesis start contract frozen。
- [x] Recommendation idempotency identity rule frozen。
- [x] Replay determinism identity and digest requirement frozen。
- [x] ThesisMonitor／RiskGate／application mutation boundaries frozen；PR-TM-003 dependency／output
  authority tests 證明 pure boundary。
- [x] No production order capability confirmed by code/import/capability review。

## 21. PR-TM-002 Journal Integration merge checklist

Review disposition：**PR-TM-002 APPROVED TO MERGE**。

本 PR 只把 PR-TM-001 frozen contracts 接到既有 `trading.journal`，保存 canonical fact 並由
append sequence 重建相同 projection。沒有 ThesisMonitor、exit calculation、RiskGate
decision、fill sink、SELL、broker 或 market-data Replay engine change。

### P1 blocker resolution

#### Decimal contract

- [x] Decimal canonical encoding 已凍結：`100`／`100.0`／`100.00` → `"100"`，
  `100.50` → `"100.5"`，`-0.00` → `"0"`。
- [x] Writer 永不輸出 exponent；reader 拒絕 trailing-zero、negative-zero、exponent 與 JSON
  number artifact，不做 silent normalization。
- [x] `EvidenceValue(kind=DECIMAL)` 亦必須使用相同 canonical notation，不能以 string field
  繞過規則。
- [x] Golden Decimal fixture 與等價 input identity test 證明 JSON、record ID、fact digest、
  fingerprint 各只有一個結果。

#### Journal immutability

- [x] `JournalRecord` 建構時立即產生 canonical UTF-8 `payload_bytes` snapshot；caller 後續修改
  原始 dict 不影響 record。
- [x] Public `payload` 是 recursively immutable mapping／tuple view，直接與 nested mutation
  都被拒絕。
- [x] In-memory／PostgreSQL adapter 共用 `payload_json`／`payload_bytes` authority，不新增資料庫
  schema 或第二套 truth source。
- [x] Append 後 mutation regression 與 checkpoint replay test 證明 rejected mutation 不改變
  stored history、fingerprint 或 projection digest。

### Compatibility policy

- [x] `trade-management-v1` reader 對 schema、field、enum、timestamp、decimal notation 與
  serializer version 採 strict fail-closed。
- [x] 舊 schema reader 並存；migration 不覆寫 immutable Journal record。
- [x] Enum 只允許 append-only evolution；existing name／value／meaning 不得 rename、reuse 或
  reinterpret。

### Journal and reconstruction

- [x] Thesis draft／activation、recommendation created／updated／resolved、trade closed 六種
  fact records 有 deterministic record ID、idempotency key、canonical JSON 與 SHA-256 digest。
- [x] Reader 驗證 kind、contract type、session、occurred_at、serializer、payload digest 與完整
  Journal fingerprint。
- [x] Projection 依 append `sequence` 重建 draft、active thesis、one recommendation per trade
  與 outcome；unrelated Journal kinds 不改 domain state但仍推進 sequence。
- [x] Activation-before-draft、duplicate fact、recommendation identity mutation、reason removal、
  close-before-open、unknown recommendation、sequence rollback 與 digest corruption fail closed。
- [x] Checkpoint writer/recovery 可驗證中途 digest，restart 重跑十次得到相同 final digest。
- [x] Existing `trading.journal`、local-paper projection、order application contract未修改。
- [x] No trading behavior changed；fill v2／delayed fill sink／runtime lifecycle wiring明確延後。

Evidence：

```text
tests/test_trade_management_serialization.py
tests/test_trade_management_journal.py

.venv/bin/python -m pytest tests/test_trade_management_contracts.py \
  tests/test_trade_management_serialization.py \
  tests/test_trade_management_journal.py -q
# 57 passed

.venv/bin/python -m pytest tests/ -q
# 625 passed, 1 skipped
```

## 22. PR-TM-003 ThesisMonitor status-only merge checklist

Review disposition：**PR-TM-003 APPROVED**。

本 PR 只實作：

```text
TradeThesis + immutable ThesisMarketContext
                    |
                    v
              ThesisMonitor
                    |
                    v
             ThesisEvaluation
```

不建立 `ExitRecommendation`，不 append Journal，不修改 Position／Order／RiskState，不接
Clock／scheduler／Replay engine／broker／local-paper runtime。

### Immutable input and output contract

- [x] `ThesisMarketContext` 綁定 thesis／trade／session／symbol／source event identity，且只保存
  upstream 已彙整的 highest price、volume、completed-bar 與 data-health evidence；Monitor 沒有
  mutable window cache。
- [x] `ThesisConditionEvaluation` 保存 typed condition kind、outcome、canonical observed／threshold
  evidence；`ThesisEvaluation` 保存 deterministic `evaluation_id`／`input_digest`、status、reason
  codes 與 evaluated event。
- [x] Context／condition／evaluation 全部 frozen；相同 input 重跑十次得到相同 output、input
  digest 與 evaluation ID。

### Status semantics

- [x] New-high 使用 strict `>`；volume ratio 使用 `observed_shares >= baseline * ratio` 且 sample
  count 達門檻；VWAP hold 使用 completed-bar count。
- [x] hard `BREAKOUT_LEVEL_LOST`／`VWAP_CONFIRMATION_LOST` 優先於 expected behavior time status。
- [x] `warning_at = filled_at + warning_after`；`deadline = filled_at + observation_window`；exact
  warning boundary 進 WARNING，exact deadline 未完成進 INVALID，signal／submit time 不參與。
- [x] explicit prior INVALID status latch；Monitor 不自行保存 prior state。
- [x] missing／stale／out-of-order／session mismatch／blocked health／required field missing／before-fill
  observation 全部回 `INSUFFICIENT_DATA`，不偽裝 VALID 或自動轉成 EXIT。

### Authority and deferred integration

- [x] AST dependency test 與 output capability test 證明沒有 Journal、RiskGate、Position、Order、
  ExitRecommendation、SimulationService、broker 或 wall-clock authority。
- [x] 本 PR 沒有改既有 Journal、RiskGate、Position、simulation、market Replay 或 broker module。
- [ ] Upstream `ThesisMarketContext` reducer／registry mapping、deadline control-event scheduler、
  `thesis_state_changed.v1` transition persistence、bar-resolution adapter 與 runtime wiring 延後到
  Phase 2 follow-up；不得把本 PR 誤標為 runtime monitor rollout 完成。

Evidence：

```text
.venv/bin/pytest -q tests/test_thesis_monitor.py
# 27 passed

.venv/bin/pytest -q tests/test_thesis_monitor.py \
  tests/test_trade_management_contracts.py \
  tests/test_trade_management_serialization.py \
  tests/test_trade_management_journal.py
# 84 passed

.venv/bin/pytest -q tests
# 657 passed, 1 skipped
```

## 23. PR-TM-004 Exit Recommendation merge checklist

Review disposition：**PR-TM-004 APPROVED**。

本 PR 只實作：

```text
ThesisEvaluation + immutable ExitPositionContext
                         |
                         v
             ExitRecommendationEngine
                         |
                         v
       ExitDecision + optional ExitRecommendation
```

`ExitDecision.action=EXIT` 是 decision evidence，不是 command。此模組不能建立 Order、SELL、
broker request，也不 append Journal、不呼叫 RiskGate、不讀寫 Position。

### Status and reason mapping

- [x] PR-TM-003 typed `ThesisReasonCode` 直接映射 frozen `ExitReason`；沒有 free-form reason：
  breakout／VWAP hard invalid → `THESIS_INVALID`，expected behavior deadline → `TIME_DECAY`。
- [x] `VALID`／`WARNING`／`INSUFFICIENT_DATA` → HOLD decision 且 recommendation 為 null；只有
  `INVALID` → EXIT decision 與 ACTIVE recommendation。
- [x] INVALID latch 若已有 active recommendation，保留原 actionable reasons；若 persistence
  gap 導致沒有 recommendation，fail-safe 建立 `THESIS_INVALID` recommendation。
- [x] v1 priority 固定 `THESIS_INVALID > TIME_DECAY`；不依 input/list/set iteration order。

### Identity, lifecycle, and no-op updates

- [x] `ExitPositionContext` 綁定 open trade／thesis／session identity、positive remaining shares、
  `ACTIVE_POSITION` lifecycle、caller-injected canonical EXIT_DECISION time 與 optional current
  ACTIVE recommendation。
- [x] Decision digest 綁定 engine／policy version、完整 Thesis status/reasons/input digest、source
  event、open-position facts與 injected decision time；不依賴 current recommendation snapshot。
- [x] 同一 event retry 得到同一 decision ID；每個 trade／policy 只有一個 deterministic active
  recommendation ID，first-trigger provenance 永遠保留。
- [x] 新 reason 只做 monotonic union；`THESIS_INVALID` 可提高既有 `TIME_DECAY` primary priority。
- [x] reason／priority 沒有 material change 時回傳 byte-identical active recommendation 與
  `recommendation_changed=false`；未來 persistence layer 不應 append no-op update。
- [x] Context、engine、result、decision、recommendation 全部 immutable；相同 input 十次輸出一致。

### Authority and deferred integration

- [x] AST dependency/output capability tests 證明沒有 Journal、RiskGate、legacy Position、Order、
  SELL、SimulationService、broker、Clock、filesystem/network 或 UI authority。
- [x] 本 PR 沒有修改既有 Journal、RiskGate、Position、simulation、market Replay、backtest、
  broker、dashboard 或 runtime module。
- [ ] Stop Loss／ATR／Take Profit adapters、full category priority aggregation、Journal persistence、
  backtest/local-paper read model、RiskGate validation、warning escalation scheduler 與 execution
  全部延後；不得把本 PR 誤標為可執行退出。

Evidence：

```text
.venv/bin/pytest -q tests/test_exit_recommendation_engine.py
# 13 passed

.venv/bin/pytest -q tests/test_exit_recommendation_engine.py \
  tests/test_thesis_monitor.py \
  tests/test_trade_management_contracts.py \
  tests/test_trade_management_serialization.py \
  tests/test_trade_management_journal.py
# 97 passed

.venv/bin/pytest -q tests
# 677 passed, 1 skipped
```

## 24. PR-TM-005 RiskGate Exit Eligibility merge checklist

Review disposition：**APPROVED**。

本 PR 只實作：

```text
ACTIVE ExitRecommendation + immutable ExitEligibilityContext/RiskSnapshot
                                  |
                                  v
                              RiskGate
                                  |
                                  v
                       ExecutionEligibility
```

`ELIGIBLE` 只代表「現有 evidence 允許未來 application layer 形成 risk-reducing command」；
本 PR 不建立 `OrderCommand`、不 append Journal、不呼叫 handler、不執行 SELL。

### Eligibility contract

- [x] `ExitEligibilityContext` 綁定 snapshot／session／trade／thesis identity、immutable
  `RiskSnapshot` 與 caller-injected aware evaluation time。
- [x] 只接受 ACTIVE recommendation；resolved recommendation、identity mismatch、evaluation time
  早於 recommendation update 全部 fail closed。
- [x] `ELIGIBLE` 回傳 `current_position_shares - pending_sell_shares` 的正數可用數量；不選價格、
  不建立 command ID／idempotency key。
- [x] data unhealthy、market closed、instrument untradable、same-side pending duplicate、required
  book missing/stale → `BLOCKED`；無剩餘 position → `INELIGIBLE/INSUFFICIENT_POSITION`。
- [x] cash、pending BUY、daily realized loss 與 entry notional limits 不影響 exit eligibility。

### Existing RiskGate direction correction

- [x] `STRATEGY_ORIGIN_DISABLED`、`DAILY_LOSS_LIMIT`、`ORDER_NOTIONAL_LIMIT`、cash 與 position
  notional checks 只套用 BUY。
- [x] automated／large-notional SELL 只要 quantity 不超過未保留 position 且 operational checks
  通過，既有 command RiskGate 會 APPROVE；entry rules 不再阻擋 risk reduction。
- [x] data health、market、instrument、book、duplicate pending、invalid quantity/price 與 SELL
  position availability checks 保留。
- [x] Existing OrderApplicationService/RiskGate regression 全部通過；沒有接入 recommendation
  eligibility，也沒有新增 command routing。

### Determinism, authority, and deferred work

- [x] Eligibility artifact 保存 `RISK_GATE_VERSION`、policy version、deterministic eligibility ID 與
  input digest；digest 綁定 recommendation、完整 policy values、canonical Decimal snapshot、
  snapshot ID 與 evaluation time。
- [x] Decimal scale variants收斂到相同 identity；相同 input 十次輸出一致，所有 context/output
  frozen。
- [x] Dependency/capability tests 證明 risk module 沒有 Journal、application、Position、simulation、
  market-data、dashboard、broker、filesystem/network 或 handler invocation。
- [ ] Consecutive-loss/cooldown projection、session reset、pending BUY pre-fill quarantine、durable
  recovery、eligibility persistence、command factory/idempotency、Simulation Replay/Shadow 與任何
  execution 全部延後。

Evidence：

```text
.venv/bin/pytest -q tests/test_exit_execution_eligibility.py \
  tests/test_risk_gate.py
# 23 passed

.venv/bin/pytest -q tests/test_exit_execution_eligibility.py \
  tests/test_risk_gate.py \
  tests/test_order_application.py \
  tests/test_risk_context.py \
  tests/test_exit_recommendation_engine.py \
  tests/test_thesis_monitor.py \
  tests/test_trade_management_contracts.py \
  tests/test_trade_management_serialization.py \
  tests/test_trade_management_journal.py
# 132 passed

.venv/bin/pytest -q tests
# 728 passed, 2 skipped
```

## 25. PR-TM-006 Simulation／Historical Tick Replay Validation merge checklist

Review disposition：**APPROVED**。

本 PR 僅驗證 decision chain：

```text
immutable market-event-v1 Historical Tick
                  |
                  v
        pure minute evidence reducer
                  |
                  v
 ThesisEvaluation -> ExitRecommendation -> ExecutionEligibility
                  |
                  v
     ReplayVerification / deterministic digest
```

### Input and reduction contract

- [x] 直接接受既有 immutable `market-event-v1` `EventEnvelope/TickEvent`；不新增第二套 market
  event schema，也不修改 `market_data/replay.py`／exact replay engine。
- [x] manifest digest 綁定 exact canonical event artifacts 與 replay order；session、symbol、
  schema、duplicate ID、out-of-order watermark 或 manifest mismatch 全部 fail closed。
- [x] 明確拒絕 synthetic tick；本 PR 的測試資料標示為 `HISTORICAL_CAPTURE`，不從一分鐘
  OHLC 製造 tick path。
- [x] Thesis clock 仍從 `filled_at` 開始；fill 前事件不進入 post-entry reducer。
- [x] minute reducer 只在下一分鐘第一筆 Tick 到來時結算前一分鐘，依實際 Tick close、
  `average_price`、逐筆 lot volume 與 caller-frozen shares-per-lot／volume baseline 建立
  `ThesisMarketContext`。

### Decision chain and determinism

- [x] 每一 post-fill Tick 依序呼叫既有 pure `ThesisMonitor`、`ExitRecommendationEngine`，
  有 ACTIVE recommendation 時才呼叫既有 pure RiskGate exit eligibility。
- [x] hard invalid 映射 `THESIS_INVALID`；未觸發 hard invalid 且 deadline 到期映射
  `TIME_DECAY`；Eligibility 保留原 policy semantics。
- [x] `ReplayRunIdentity` 必須與 strategy／thesis／event schema／RiskPolicy version 完全相符；
  不以新 policy 靜默重算舊 identity。
- [x] 同一 immutable input 重跑十次得到相同 decision digest、final-state digest 與
  `ReplayOutput.digest`；市場證據改變會改變 verified output。
- [x] `ReplayOutput.journal_digest` 明確使用 empty-Journal digest，因本 PR 不 append Journal；
  replay evidence 不冒充 authoritative Journal record。

### Authority and deferred work

- [x] Replay input、step、result 全部 frozen；runner 不讀 filesystem/network、不用 wall clock、
  不修改 Position／Journal／market replay runtime。
- [x] 沒有 `OrderCommand`、OrderApplicationService、SELL、broker、Shioaji、Shadow、Dashboard 或
  production runtime wiring。
- [ ] durable guard persistence/restart、Journal persistence of evaluation/recommendation、partial
  SELL、pending BUY race、disconnect/queue/shutdown lifecycle、Dashboard 與 Shadow 全部延後。

Evidence：

```text
.venv/bin/pytest -q tests/test_trade_management_replay.py
# 6 passed

.venv/bin/pytest -q tests/test_trade_management_replay.py \
  tests/test_thesis_monitor.py \
  tests/test_exit_recommendation_engine.py \
  tests/test_exit_execution_eligibility.py \
  tests/test_trade_management_contracts.py \
  tests/test_market_data_events.py \
  tests/test_market_event_contract_freeze.py
# 98 passed

.venv/bin/pytest -q tests
# 734 passed, 2 skipped
```

## 26. PR-TM-007 Shadow Decision Pipeline merge checklist

Review disposition：**APPROVED**。

本 PR 的 authority boundary：

```text
post-ingest live canonical EventEnvelope + per-event RiskSnapshot
                              |
                              v
                shared Trade Management kernel
                              |
                              v
             immutable Shadow Decision Record
                              |
                  session finalize only
                              v
       exact manifest + Historical Replay parity report
```

### Live consumer and shared semantics

- [x] Shadow 是 post-ingest canonical `EventEnvelope` consumer；不修改 Shioaji callback、subscription、
  bounded queue、canonical ingestion 或既有 Momentum Shadow runtime。
- [x] PR-TM-006 的 event transition 已抽成 incremental `TradeManagementDecisionKernel`；batch
  Replay 與 live Shadow 共用同一 Thesis／Recommendation／RiskGate path，沒有複製判斷規則。
- [x] `ShadowDecisionConfig` 綁定 thesis/strategy/exit/risk/fill/code versions 與完整 RiskPolicy
  values、volume baseline、shares-per-lot、remaining quantity。
- [x] 每筆 event caller-inject immutable `RiskSnapshot`；Shadow record 綁定 event artifact digest、
  risk snapshot digest、config digest 與 cumulative decision-chain digest。
- [x] fill 前 event 可進 finalized market manifest，但不產生 post-entry Shadow Decision Record；
  Thesis clock 仍只從 `filled_at` 開始。

### Idempotency, fail-closed, and parity

- [x] exact duplicate event＋risk evidence 回傳同一 record 且不改變 state；同 event ID 的 artifact
  或 risk evidence 不同則 `duplicate event conflict`。
- [x] out-of-order watermark、session/symbol mismatch、non-Tick 與 synthetic Tick 在 state mutation
  前 fail closed。
- [x] live session 尚未 finalize 前不偽造 manifest；`finalize()` 對實際 consumed canonical events
  計算 manifest，才建立 frozen `ReplayRunIdentity`。
- [x] finalize 以完整 per-event RiskSnapshot sequence 執行 Historical Replay，比對每個 immutable
  step 與 cumulative decision digest，產生 `MATCHED`／`DIVERGED` parity artifact。
- [x] finalize 後拒絕新 event，避免已驗證 artifact 被延伸；Shadow snapshot/session/record/parity
  contracts 全部 immutable。

### Authority and deferred work

- [x] Shadow record 是 in-memory observation evidence，不是 authoritative Trade Management Journal
  fact；本 PR 沒有 Journal append、repository、checkpoint 或 restart recovery。
- [x] 沒有 `OrderCommand`、OrderApplicationService、Position mutation、SELL、broker、Shioaji order、
  filesystem/network、wall clock、Dashboard 或 real-money authority。
- [ ] durable Shadow evidence persistence、coverage metrics、multi-session operations、guard restart、
  Dashboard、alert/runbook 與任何 execution 全部延後。

Evidence：

```text
.venv/bin/pytest -q tests/test_trade_management_shadow.py
# 6 passed

.venv/bin/pytest -q tests/test_trade_management_shadow.py \
  tests/test_trade_management_replay.py \
  tests/test_thesis_monitor.py \
  tests/test_exit_recommendation_engine.py \
  tests/test_exit_execution_eligibility.py \
  tests/test_trade_management_contracts.py \
  tests/test_market_data_events.py \
  tests/test_market_event_contract_freeze.py \
  tests/test_momentum_shadow_runtime.py
# 116 passed

.venv/bin/pytest -q tests
# 749 passed, 2 skipped
```

## 27. PR-TM-008 Durable Decision Journal／Shadow Evidence merge checklist

Review disposition：**APPROVED**。

本 PR 只把 Shadow observation 變成可 restart/replay/audit 的 immutable evidence：

```text
Shadow Decision Record / finalized parity
                  |
                  v
 strict shadow-evidence-v1 serializer
                  |
                  v
       existing JournalRepository
                  |
                  v
 ShadowEvidenceProjection + checkpoint
```

### Journal and artifact contract

- [x] 沿用既有 `JournalRecord` canonical bytes、fingerprint、append sequence、idempotency 與
  `ProjectionCheckpoint`；沒有第二套 database/event store，也不修改 PostgreSQL schema。
- [x] fact kind 僅有 `shadow_decision_recorded.v1` 與 `shadow_session_finalized.v1`；unknown
  `shadow_*` kind、unknown/missing nested fields、duplicate JSON key、非 canonical Decimal、enum、
  timestamp 或 digest mismatch 全部 fail closed。
- [x] deterministic record ID／idempotency scope 綁定 session、kind 與 immutable Shadow record／
  manifest identity；完整 retry 回傳 idempotent，partial append 後可安全 resume。
- [x] Journal payload 保存 canonical `evidence_json` 與 digest、serializer version、retention mode／
  version；generic Journal 再把整個 payload 固化成 immutable bytes。

### Evidence completeness and audit

- [x] Decision evidence保存 event ID/artifact digest、完整 immutable RiskSnapshot values＋digest、
  aggregated Thesis market context、evaluation status/reasons/input digest、exit decision、
  recommendation、eligibility 與 cumulative decision-chain digest。
- [x] Reader 重新計算 RiskSnapshot digest；即使攻擊者同步更新 outer evidence digest，也不能在
  原 digest 下改寫歷史 risk values。
- [x] Market event 本體仍由 canonical Market Event Journal 擁有；Shadow evidence 只用 source
  event ID＋serialized artifact digest 關聯，不重複建立市場 source of truth。
- [x] Finalization evidence 保存 manifest、record count、config/run identity、shadow decision
  digest、replay decision digest、ReplayOutput digest 與 parity；`MATCHED` 必須兩個 decision
  digest 相同。

### Projection, recovery, and retention

- [x] Projection 只重建 Shadow evidence；不 import／呼叫 `TradeManagementProjection`，不建立或
  更新 Thesis／Recommendation／Trade lifecycle authority。
- [x] decision step 必須 contiguous、identity/config/time monotonic；finalization 必須精確匹配
  record count、最後 chain digest 與 final time；finalize 後禁止新增 decision evidence。
- [x] recovery 預設要求 checkpoint，驗證 checkpoint sequence 當下 projection digest；missing、
  absent sequence、corrupted digest 全部 fail closed，重跑十次結果 deterministic。
- [x] retention v1 固定 `RETAIN_ALL` 且 `compaction_allowed=false`；本 PR 沒有 prune/delete API。
  未來壓縮必須新增 policy/schema 與 verification-preserving summary artifact。

### Authority and deferred work

- [x] 沒有 runtime composition、Shioaji callback/order、OrderCommand、Position mutation、SELL、
  broker、Dashboard、filesystem/network 或 real-money authority。
- [ ] live writer scheduling/backpressure、PostgreSQL production smoke、multi-session coverage metric、
  divergence taxonomy、durable guard、Dashboard 與 controlled long-running Shadow 全部延後。

Evidence：

```text
.venv/bin/pytest -q tests/test_shadow_evidence_journal.py
# 9 passed

.venv/bin/pytest -q tests/test_shadow_evidence_journal.py \
  tests/test_trade_management_shadow.py \
  tests/test_trade_management_replay.py \
  tests/test_trade_management_journal.py \
  tests/test_journal.py \
  tests/test_postgres_journal.py \
  tests/test_thesis_monitor.py \
  tests/test_exit_recommendation_engine.py \
  tests/test_exit_execution_eligibility.py \
  tests/test_trade_management_contracts.py
# 119 passed, 1 skipped

.venv/bin/pytest -q tests
# 768 passed, 2 skipped
```

## 28. PR-TM-009 Live Runtime Composition／Shadow Operation merge checklist

Review disposition：**APPROVED**。

本 PR 把正式 canonical market pipeline 的 applied event 接到既有 decision-only Shadow 與
durable evidence，但沒有增加交易權限：

```text
Live MarketMessageFactory
          |
          v
CanonicalMarketDataPipeline
  record -> ingest -> disposition
          |
   projection_applied only
          v
LiveTradeManagementShadowOperation
          |
          +--> per-event RiskSnapshot
          +--> shared Shadow decision kernel
          +--> immediate decision evidence append
          |
          v
finalize parity -> checkpoint -> restart projection verification
```

### Runtime composition contract

- [x] 使用 wrapper composition，不修改 Shioaji callback、subscription、bounded ingress queue、
  canonical recorder／ingestor 或 dashboard/local-paper `RuntimeComposition` authority。
- [x] 每次只 dequeue 一筆 canonical message，market ingress/disposition 完成後才進 Shadow；
  duplicate、out-of-order、session mismatch、invalid 與 recorder failure 不進 decision chain。
- [x] 每個 projection-applied event 呼叫 injected `RiskSnapshotProvider`，保留當下 immutable
  RiskSnapshot；不讀 later/current global risk state。
- [x] Replay 與 live operation 繼續共用 `ShadowDecisionPipeline`／
  `TradeManagementDecisionKernel`，沒有第二套 Thesis、Recommendation 或 RiskGate 規則。
- [x] Journal session 必須明示 `TRADE_MANAGEMENT_SHADOW`、`execution_enabled=false`、
  `evidence_only=true` 與 operation version；不符合即拒絕啟動。

### Durability and finalization

- [x] 每筆 Shadow Decision Record 產生後立即透過既有
  `journal_record_for_shadow_decision()` append；不等待 session 結束才一次保存。
- [x] writer append 失敗時 pending evidence 保留，下一次 processing 必須先成功 retry，才會
  dequeue 後續 market message；避免 decision evidence 缺口被靜默略過。
- [x] Finalize 可安全 retry：只建立一次 immutable Shadow session，idempotently append parity
  evidence，寫入既有 checkpoint，再以 checkpoint-required recovery 重建 projection。
- [x] finalization 回傳前比較 write-time 與 restart projection digest；不一致即 fail closed。
- [x] finalized operation 拒絕新 market/lifecycle admission 與 processing；重複 finalize 回傳同一
  immutable結果，不新增 Journal history。

### Authority and deferred work

- [x] 新 runtime module 沒有 `OrderCommand`、OrderApplicationService、Position、SELL、Broker、
  Shioaji、SimulationService、filesystem/network 或 real-money capability。
- [x] 本 PR 沒有自動啟動 Shioaji、沒有改 subscription ownership，也沒有把 eligibility 形成
  execution command；它只提供正式 canonical post-ingest operation seam。
- [ ] 實際 production-like multi-session runner、PostgreSQL smoke、metrics/alerts、operation runbook、
  evidence query model、durable guard、Dashboard 與任何 execution discussion 全部延後。

Evidence：

```text
.venv/bin/pytest -q tests/test_trade_management_shadow_operation.py
# 6 passed

.venv/bin/pytest -q tests/test_trade_management_shadow_operation.py \
  tests/test_shadow_evidence_journal.py \
  tests/test_trade_management_shadow.py \
  tests/test_trade_management_replay.py \
  tests/test_trade_management_journal.py \
  tests/test_thesis_monitor.py \
  tests/test_exit_recommendation_engine.py \
  tests/test_exit_execution_eligibility.py \
  tests/test_trade_management_contracts.py \
  tests/test_canonical_market_pipeline.py \
  tests/test_market_event_journal.py \
  tests/test_market_event_contract_freeze.py \
  tests/test_runtime_composition.py \
  tests/test_risk_gate.py
# 157 passed

.venv/bin/pytest -q tests
# 774 passed, 2 skipped
```

## 29. PR-TM-010 Shadow Observability／Production Readiness Gate merge checklist

Review disposition：**IMPLEMENTED／READY FOR REVIEW**。

本 PR 只把 Live Shadow operation 與 finalized evidence 轉成 immutable operational metrics 與
deterministic readiness classification：

```text
LiveTradeManagementShadowOperation snapshot
  + canonical event backlog
  + durable evidence backlog / writer recovery
  + finalized replay parity
                  |
                  v
       ShadowOperationMetrics
                  |
        multi-session pure reducer
                  v
       ShadowReadinessReport
       READY / NOT_READY only
       execution_enabled = false
```

### Operation health and backpressure

- [x] `ShadowOperationHealth` 凍結為 `RUNNING／DEGRADED／BLOCKED／RECOVERING／FINALIZED`；
  observability 不修改 market `DataHealth` 或 decision state。
- [x] 每個 operation snapshot 保存 admitted/processed、applied/rejected、decision/durable/pending/
  lost evidence、writer failure/recovery 與 observation duration；所有時間由 caller 注入。
- [x] canonical backlog 明確保存 `pending_market_event_count` 與 oldest pending event age；存在未
  drain canonical message 時禁止 finalize。
- [x] evidence backlog 明確保存 pending count 與 oldest pending evidence age；writer/finalization/
  checkpoint 失敗進 `BLOCKED`，retry 期間為 `RECOVERING`，成功後保存 recovery duration。
- [x] operation metrics 使用 versioned immutable dataclass 與 deterministic digest；negative、NaN、
  infinity、不一致 counts、naive timestamp 與不合法 parity metadata 全部拒絕。

### Evidence completeness, parity, and readiness

- [x] finalized metric 必須保存 finalization persistence、`MATCHED／DIVERGED` 與 first divergent
  sequence；`MATCHED` 不可帶 divergence，`DIVERGED` 必須帶 positive sequence。
- [x] `ShadowReadinessPolicy` 綁定最少 finalized sessions、總 observation seconds、總 decision
  records、最低 parity rate、writer failure 上限與 recovery time 上限。
- [x] evaluator 依 session ID 排序並拒絕 duplicate session；相同 session evidence 與 policy 不受
  input tuple order 影響，產生相同 input digest/report ID。
- [x] typed NOT_READY reasons 覆蓋未 finalize、session/time/decision evidence 不足、event backlog、
  evidence 不完整、parity divergence/rate、writer failure 與 recovery time 超限。
- [x] report 保存 matched/diverged counts、divergent session IDs、parity rate、durable/pending/lost
  evidence 與 completeness；`READY` 無 failure reasons。

### Authority and deferred work

- [x] `ShadowReadinessReport.execution_enabled` 永遠為 `false`；constructor 拒絕改為 true。
- [x] observability module 不 import／呼叫 ThesisMonitor、RiskGate、OrderCommand、
  OrderApplicationService、Position、SELL、Broker、Shioaji 或 SimulationService。
- [x] metrics/readiness 不改 Shadow decision、Journal fact schema、canonical market disposition、
  RiskGate、feature flag、runtime admission 或任何 trading authority。
- [ ] 真實一日／多日 Shadow 證據收集、PostgreSQL production smoke、metrics exporter、alerts、
  runtime source/provider/connection identity、runbook 與 execution discussion 全部延後。

Evidence：

```text
.venv/bin/pytest -q tests/test_trade_management_shadow_observability.py \
  tests/test_trade_management_shadow_operation.py
# 13 passed

.venv/bin/pytest -q tests/test_trade_management_shadow_observability.py \
  tests/test_trade_management_shadow_operation.py \
  tests/test_shadow_evidence_journal.py \
  tests/test_trade_management_shadow.py \
  tests/test_trade_management_replay.py \
  tests/test_trade_management_journal.py \
  tests/test_thesis_monitor.py \
  tests/test_exit_recommendation_engine.py \
  tests/test_exit_execution_eligibility.py \
  tests/test_trade_management_contracts.py \
  tests/test_canonical_market_pipeline.py \
  tests/test_market_event_journal.py \
  tests/test_market_event_contract_freeze.py \
  tests/test_runtime_composition.py \
  tests/test_risk_gate.py
# 164 passed

.venv/bin/pytest -q tests
# 791 passed, 2 skipped
```

## 30. PR-TM-011 Extended Shadow Validation／Operational Readiness merge checklist

Review disposition：**IMPLEMENTED／FRAMEWORK READY FOR REVIEW；REAL-MARKET EVIDENCE PENDING**。

本 PR 把 PR-TM-010 readiness evidence 與 session source／coverage／checkpoint recovery、受控 failure
drills 組合成 deterministic validation report。它不執行 live session，也不把 unit-test fixture
宣稱為 production evidence：

```text
ShadowOperationMetrics
  + provider / version / connection identity
  + market date / coverage
  + durable vs recovered projection digest
  + Journal recovery drill
  + replay divergence drill
                  |
                  v
      ShadowValidationEvaluator
                  |
                  v
      PASSED / FAILED evidence only
      execution_enabled = false
```

### Session and source evidence

- [x] `ShadowSessionSource` 明確區分 `LIVE_MARKET／TEST_FIXTURE／HISTORICAL_REPLAY`，並綁定
  provider、provider version 與 connection session ID。
- [x] `ShadowValidationSession` 綁定 market date、timezone-aware coverage、PR-TM-010 metrics、durable
  projection digest 與 checkpoint-recovered projection digest。
- [x] validation policy 可要求最少 complete sessions、不同 market dates、每 session 最少 coverage
  seconds 與 live-market source；不完整或非 live session 不可拿來湊足跨日門檻。
- [x] unit-test fixture 即使其他 threshold 全部通過，只要標記非 live source 就產生 typed failure；
  tests 不生成或保存任何 production-ready 宣告。

### Failure drills and deterministic gate

- [x] operational drill 分為 `JOURNAL_RECOVERY` 與 `PARITY_DIVERGENCE`；保存 detection、fail-closed、
  recovery/investigation、first divergent sequence 與 evidence digest。
- [x] required drill 缺少或任一同類 drill 失敗時，typed reason 明確為 missing/failed；另一筆成功
  drill 不可掩蓋失敗。
- [x] evaluator 內部以相同 session metrics 重建 PR-TM-010 readiness report；base readiness 失敗
  保持 authoritative，不由 extended gate 覆蓋。
- [x] session、drill 先依 stable ID 排序並拒絕 duplicate identity；policy、readiness、session、drill
  全部參與 input digest，相同 evidence 不受 tuple order 影響。
- [x] `ShadowValidationReport.execution_enabled` 永遠為 `false`；`PASSED` 只表示可進下一次架構
  討論，不授予 command/order authority。

### Operations and deferred production evidence

- [x] 新 runbook 說明正常 session、BLOCKED recovery、Journal failure drill、divergence investigation、
  immutable evidence 與 gate interpretation。
- [x] validation module 不 import Journal repository、RiskGate、ThesisMonitor、OrderCommand、broker、
  Shioaji SDK、Position 或 SimulationService，也不改 live operation／decision kernel。
- [ ] 尚未收集真實一日／多日 Shioaji Shadow evidence，尚未執行 PostgreSQL production smoke；
  metrics exporter、alerts、production runner 與 execution discussion 仍延後。

Evidence：

```text
.venv/bin/pytest -q tests/test_trade_management_shadow_validation.py
# 8 passed

.venv/bin/pytest -q tests/test_trade_management_shadow_validation.py \
  tests/test_trade_management_shadow_observability.py \
  tests/test_trade_management_shadow_operation.py \
  tests/test_shadow_evidence_journal.py \
  tests/test_trade_management_shadow.py \
  tests/test_trade_management_replay.py \
  tests/test_trade_management_journal.py \
  tests/test_thesis_monitor.py \
  tests/test_exit_recommendation_engine.py \
  tests/test_exit_execution_eligibility.py \
  tests/test_trade_management_contracts.py \
  tests/test_canonical_market_pipeline.py \
  tests/test_market_event_journal.py \
  tests/test_market_event_contract_freeze.py \
  tests/test_runtime_composition.py \
  tests/test_risk_gate.py
# 172 passed

.venv/bin/pytest -q tests
# 805 passed, 2 skipped
```

## 31. PR-TM-012A Paper Fill → authoritative TradeThesis merge checklist

Review disposition：**APPROVED；PRODUCTION SHADOW GATE NOT PASSED**。

本 checkpoint 只建立交易生命週期起點，不接 live stream：

```text
TradeThesisDraft
  + deterministic paper-thesis idempotency key
  + Journaled local-paper BUY fill
  + paper/provider/no-execution provenance
                  |
                  v
       PaperFillThesisBuilder
                  |
                  v
     immutable TradeThesis activation
     thesis clock = fill occurred_at
```

### Fill evidence and correlation

- [x] 新 local-paper order/fill payload 保存 `fill_source=paper_simulation`、stable provider identity
  與 `execution_authority=false`；ShioajiProvider identity 保存 SDK version 與 simulation mode，但不
  洩漏 credential。
- [x] 舊 `local_paper_fill.v1` 仍可由既有 accounting projection 回放；缺 provenance 的舊紀錄不
  可啟動 authoritative TradeThesis。
- [x] `paper_thesis_entry_idempotency_key(draft)` 由 immutable thesis ID 產生並在 command-first
  Journal flow 保存；fill 的 persisted command key 必須完全相符。
- [x] builder 只接受同 session、同 symbol、draft 後發生、canonical identity 的 non-zero BUY fill；
  SELL、錯誤 key、錯誤來源、`execution_authority=true` 全部 fail closed。
- [x] opening fill ID 使用 immutable fill Journal record ID；trade ID、activation ID、input digest
  deterministic，Thesis `filled_at` 使用 `SIMULATION_CLOCK` 並正規化為 `Asia/Taipei`。

### Authority boundary

- [x] builder 是 pure transform，不 submit order、不 append Journal、不呼叫 RiskGate／strategy、
  不修改 Position、不依賴 Shioaji SDK／Broker／SimulationService，也不啟動 stream。
- [x] activation provenance 與 activation constructor 都拒絕 `execution_authority=true`。
- [ ] PostgreSQL DSN、live capture runner、2026-08-21 full-session evidence、multi-day evidence、
  recovery drill 與 Production Shadow Gate pass 仍屬 PR-TM-012B。

Evidence：

```text
.venv/bin/pytest -q tests/test_paper_fill_thesis_builder.py
# 10 passed

.venv/bin/pytest -q tests/test_paper_fill_thesis_builder.py \
  tests/test_local_paper_command_service.py \
  tests/test_local_paper_projection.py \
  tests/test_order_application.py \
  tests/test_command_recovery.py \
  tests/test_simulation_service.py \
  tests/test_realtime_quote_stream.py \
  tests/test_shioaji_provider.py \
  tests/test_trade_management_contracts.py \
  tests/test_trade_management_journal.py \
  tests/test_trade_management_shadow.py \
  tests/test_trade_management_shadow_operation.py \
  tests/test_trade_management_shadow_observability.py \
  tests/test_trade_management_shadow_validation.py
# 112 passed

.venv/bin/pytest -q tests
# 821 passed, 2 skipped
```

## 32. PR-TM-012B Live Capture Evidence Collection checkpoint

Review disposition：**INFRASTRUCTURE IN PROGRESS；PRODUCTION SHADOW GATE NOT PASSED**。

目前只完成 storage bootstrap 與 data-only callback adapter：

```text
PaperFillThesisActivation (already authoritative)
  + provider / SDK / simulation / connection identity
  + paired Tick and BidAsk subscription ACK
                  |
                  v
       LiveShadowCaptureRunner
                  |
                  v
       existing Live Shadow Operation
                  |
                  v
       PostgreSQL Shadow evidence Journal
```

### Completed infrastructure

- [x] `PostgreSQL_DSN` 只由環境讀取且不寫入 log/artifact；專用 PostgreSQL 17 schema 在 migration
  前確認為空，`001_journal.sql` 已由正式 migration runner 登記。
- [x] authoritative tables 為 `journal_sessions`、`journal_records`、`projection_checkpoints`；schema
  bootstrap 後三者仍為零筆，不以測試資料污染第一個正式 session。
- [x] runner 只接受既有 `PaperFillThesisActivation`，拒絕 session、symbol、provider 或 market
  window mismatch；Journal metadata 保存 provider、SDK version、simulation、connection session、
  activation identity 與 `execution_enabled=false`。
- [x] paired ACK 前 event 不進 decision chain但保留 count；ACK 後 market event 由 canonical ingress
  重新編號，lifecycle incident 送入同一 operation，finalize 仍由既有 durable evidence/checkpoint
  recovery contract 負責。
- [x] runner module 不 import `PaperFillThesisBuilder`、`TradeThesis`、SimulationService、Shioaji SDK、
  OrderCommand 或 Broker，也沒有 SELL／Position mutation 能力。

### Still required

- [x] live `EntryDecision -> TradeThesisDraft` authority 已由 PR-TM-012B1 凍結；不得以
  caller-authored JSON、test fixture 或 runner 內建策略語意繞過此 contract。
- [ ] 建立 operational composition entry point，注入 live strategy draft、local-paper fill activation、
  canonical pipeline、RiskSnapshot provider 與 PostgreSQL repository；runner 本身不得代建 Thesis。
- [ ] 完整交易日 canonical market capture、post-fill Shadow interval、durable finalization、checkpoint
  restart recovery、Replay parity MATCHED 與 deterministic readiness report。
- [ ] 多日 evidence 與受控 recovery drill；完成前 Production Shadow Gate 保持 `NOT_PASSED`。

Evidence：

```text
.venv/bin/pytest -q tests/test_trade_management_live_capture.py
# 7 passed

# Combined activation / Shadow / Journal / validation regressions
# 46 passed

.venv/bin/pytest -q tests
# 837 passed, 2 skipped, 1 unrelated missing institutional digest artifact
```

## 33. PR-TM-012B1 Live EntryDecision → TradeThesisDraft merge checklist

Review disposition：**IMPLEMENTED／READY FOR REVIEW；PRODUCTION SHADOW GATE NOT PASSED**。

```text
Candidate / BuyScore evidence
          |
          v
LiveEntryDecisionBuilder
          |
          v
LiveEntryDecision (intent only)
          +
LiveThesisDraftPolicy
          |
          v
LiveTradeThesisDraftBuilder
          |
          v
TradeThesisDraft (no fill / no position)
```

### Contract and identity

- [x] `LiveEntryDecision` 保存 builder version、session/symbol/side、strategy/version、signal/decision
  timestamp、canonical Decimal score、sorted matched rules、market-context SHA-256 與完整 typed
  entry evidence。
- [x] input digest 綁定上述所有內容；decision ID 由 input digest deterministic 產生，任何 score、
  rule、evidence、timestamp、strategy 或 context 變更都必須建立不同 decision。
- [x] canonical writer/strict reader 拒絕 unknown field/enum、duplicate JSON key、non-canonical
  Decimal、version/identity mismatch；canonical serialization digest 已 frozen。

### Draft policy and authority

- [x] `LiveThesisDraftPolicy` 綁定 strategy/version、thesis type/version、side、expected behavior 與
  invalid conditions；wrapper policy ID 必須等於會持久化的 expected-behavior policy ID。
- [x] Draft builder 只建立既有 TradeThesisDraft；thesis ID 綁定 session、EntryDecision ID、thesis
  type/version，沒有 opening fill/order/trade/position 欄位。
- [x] CandidateEngine／BuyScoreEngine 未修改；builder 不 import Candidate、BuyScore、Journal、
  PaperFillThesisBuilder、TradeThesis、RiskGate、OrderCommand、SimulationService、Shadow、Shioaji
  或 Broker，也沒有 SELL／Position mutation。

Evidence：

```text
.venv/bin/pytest -q tests/test_live_entry_thesis_draft.py
# 8 passed

# Combined Trade Management lifecycle contracts
# 94 passed

.venv/bin/pytest -q
# 860 passed, 2 skipped
```

## 34. PR-TM-012B2 Operational Composition / Fill Observation merge checklist

Review disposition：**APPROVED；PRODUCTION SHADOW GATE NOT PASSED**。

```text
LiveEntryDecision
        |
        v
TradeThesisDraft                     existing local-paper Journal
        |                                        |
        +--------------- observe ----------------+
                            |
                            v
                 PaperFillThesisBuilder
                            |
                            v
                      TradeThesis
                            |
                            v
                 existing Shadow operation
                            |
                            v
                 PostgreSQL evidence Journal
```

### Evidence and observation

- [x] BuyScore total 與 sorted per-rule score/max-score 轉成 immutable typed `EntryEvidence`；adapter
  不判斷 matched rules、不套 threshold、不建立 EntryDecision，也不修改 Candidate/BuyScore engine。
- [x] fill observer 只讀既有 Journal，以 `paper_thesis_entry_idempotency_key(draft)` 找 correlated
  `local_paper_fill.v1`；零筆時等待、超過一筆時 conflict，兩者皆不建立或修改 fill。
- [x] observer 重用 PR-TM-012A `PaperFillThesisBuilder`，保留 fill source、provider identity、
  `execution_authority=false`、record fingerprint 與 deterministic activation identity。
- [x] 同一 immutable Journal 重新建構後，fill sequence、record fingerprint、activation ID 與 digest
  一致；source Journal 在 observation 前後完全不變。

### Operational composition and authority

- [x] composer 重用 PR-TM-012B1 Draft builder、PR-TM-012A activation、既有 live Shadow operation
  與 capture runner；activated Thesis 是 Shadow config 的唯一 Thesis。
- [x] fill observation Journal 與 Shadow evidence Journal 必須是分離 authority，避免 local-paper
  session history 與 `TRADE_MANAGEMENT_SHADOW` evidence lifecycle 混成第二個 truth source。
- [x] applied canonical event 可經組裝後的 runner 產生 durable Shadow decision record；共享
  `JournalRepository` port 可由既有 PostgreSQL adapter 實作，composition core 不讀 DSN、不依賴
  psycopg 或 Shioaji SDK。
- [x] product module 不 import/call OrderCommand、OrderApplicationService、LocalPaperCommandService、
  SimulationService、RiskGate、ShioajiProvider、submit_order、matching、Position 或 Broker。
- [ ] 真實完整交易日、多日 evidence、checkpoint interruption drill、Replay parity 與 readiness
  report 尚未收集；完成前 Production Shadow Gate 維持 `NOT_PASSED`。

Evidence：

```text
.venv/bin/pytest -q tests/test_trade_management_operational_composition.py
# 7 passed

# Composition / activation / capture / Shadow operation / PostgreSQL adapter
# 38 passed, 1 skipped (explicit TEST_POSTGRES_DSN not supplied)

.venv/bin/pytest -q
# 874 passed, 2 skipped
```

## 35. PR-TM-012C First Real Shadow Evidence Session gate

Review disposition：**PENDING OPERATIONAL EVIDENCE；PRODUCTION SHADOW GATE NOT PASSED**。

本階段不新增 domain decision 或 execution capability，只收集真實市場營運證據：

```text
complete real market session
          |
          v
canonical applied events
          |
          v
observed paper fill -> TradeThesis activation
          |
          v
Shadow decisions -> PostgreSQL evidence
          |
          v
checkpoint recovery drill
          |
          v
durable replay parity MATCHED
          |
          v
deterministic readiness report
```

### Evidence gate

- [ ] provider／SDK／simulation／connection session／code／strategy／thesis／risk policy／schema
  identity 在 session 開始前 frozen 並寫入 manifest。
- [ ] 完整交易時段 canonical event capture；不得以 partial、synthetic 或 post-close input 代替。
- [ ] authoritative local-paper BUY fill 被 observation path 啟動，沒有 fill generation 或 order
  submission capability。
- [ ] Shadow decision evidence durable 寫入專用 PostgreSQL Journal，event/fact count 與 sequence
  completeness 可稽核。
- [ ] 受控 writer interruption、pending evidence backpressure、restart 與 checkpoint digest recovery
  全部留下 artifact。
- [ ] durable evidence replay parity 為 `MATCHED`，readiness report 在相同 evidence/validator version
  下 deterministic。
- [ ] multi-day minimum window 完成前不得標記 `EVIDENCE PASSED`，也不得討論啟用 execution。

### PR-TM-012C0 pre-market readiness evidence

- [x] frozen manifest 綁定 2026-08-21 09:00-13:30 Asia/Taipei、reviewed calendar digest、symbol、
  provider/SDK/simulation/connection、code、Journal migration/schema 與所有 decision policy version。
- [x] Shioaji data-only login/logout 成功，identity=`shioaji:1.7.2:simulation=true`，
  `subscribe_trade=false`。
- [x] PostgreSQL 17 read-only preflight 成功；migration=`001_journal.sql`，四個 schema table 完全
  相符，三個 formal evidence table 均為零筆，artifact 不包含 DSN。
- [x] replay／composition／Journal recovery／parity／readiness rehearsal 27 tests 通過；來源明確標記
  `TEST_FIXTURE_AND_HISTORICAL_REPLAY`、`qualifying_real_session=false`。
- [x] deterministic report digest：
  `4e233ae941f9bef4d51752fb0ea6f33917fb25e31409c4ddf114bfdc89eda973`。
- [ ] 上述 C0 READY 不是 real-session evidence；完整市場時段與 C1 gate 仍待 2026-08-21 收集。
