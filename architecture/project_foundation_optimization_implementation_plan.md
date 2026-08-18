# Project Foundation Optimization Implementation Plan

- 狀態：Proposed，等待 review；尚未實作
- 日期：2026-08-18（Asia/Taipei）
- 目標：建立可排序、可稽核、可重播、可 fail-closed 的市場資料與紙上模擬地基，供既有 Candidate／BuyScore、Momentum、Dashboard 與未來 Simulation 共用
- 執行邊界：Market data、Research、Replay、Shadow、LOCAL_PAPER_SIMULATION
- 明確排除：Shioaji 下單 API、CA 啟用、authenticated broker Simulation、LiveBroker、真錢交易

## 1. 結論

下一階段不應先增加更多 Dashboard 指標，而應先建立一條共用且可驗證的事件路徑：

```text
Shioaji / Mock / Dataset adapters
              │
              ↓
 Normalize + bounded ingress queue
              │
              ↓
 Ordered ingestion + DataHealth
              │
              ├──────────────→ append-only Journal
              │                         │
              ↓                         ↓
 Latest/recent projections       deterministic Replay
              │                         │
              └──────────┬──────────────┘
                         ↓
          Candidate / BuyScore / Momentum / Exit
                         ↓
                     RiskGate
                         ↓
             LOCAL_PAPER_SIMULATION only
                         ↓
             Dashboard query projections
```

這份 plan 採「incremental modular monolith」：保留單一 repository 與單一部署單元，新增明確 ports、application services 與 infrastructure adapters。第一輪不拆微服務、不引入 Kafka，也不重寫現有 Dashboard。

## 2. 與既有計畫的關係

本 plan 不取代下列文件，而是提供兩者共用的 foundation：

| 計畫 | 保留的 ownership | 本 plan 提供的共用能力 |
|---|---|---|
| `limit_up_momentum_implementation_plan.md` | Scanner、CandidatePool、subscription allocation、FeatureEngine、Momentum signals、episodes、research promotion | ordered ingestion、DataHealth、Journal、Replay clock、projection contract、CI |
| `execution_layer_v1_implementation_plan.md` | TradeIntent、Order/Broker lifecycle、Portfolio reconciliation、未來 authenticated Simulation gates | Journal port、RiskGate 基礎、command application boundary、deterministic Replay |
| 現有 Dashboard／local paper | Candidate/Kbar UI、手動本機紙上委託、持倉投影 | 穩定 projection schema、restart recovery、health/readiness、模組化前端 |

優先權規則：

1. Market-data contracts、DataHealth、Clock、Journal 與 Replay 只能有一套。
2. Momentum 不建立第二個 queue、recent store、health state 或 replay runner。
3. 未來任何 manual／strategy command 都經同一 `OrderApplicationService` 與 RiskGate；HTTP route 或 strategy 不可直接操作 simulator/broker。
4. 本 plan 完成不代表 Momentum threshold validated，也不授權任何券商委託。

## 3. 現況與已確認缺口

### 可沿用

- `market_data/events.py` 已有 timezone-aware、`Decimal`、明確 lots 的 `TickEvent`／`BidAskEvent`／`InstrumentReference`。
- `market_data/quote_qualification.py` 與 capture CLI 已能產生 fail-closed parity evidence。
- `candidate/`、`scoring/`、`position/` 的規則對內部模型運算，適合在 Replay 重用。
- `SimulationService` 已把 SDK callback 與 state mutation 分開，並有 idempotency key、bid/ask fill 與 graceful shutdown。
- Dashboard 的 snapshot、history 與 local simulation projection 已有清楚 API/UI 邊界。

### 必須補強

- `MarketDataStore.update()` 仍是 last-call-wins，沒有 session、timestamp、duplicate、out-of-order 判定。
- `RealtimeQuoteUpdate` 是相容性 DTO，與 normalized `TickEvent`／`BidAskEvent` 尚未合流。
- callback queue 未形成全 runtime 共用的 bounded ingress/DataHealth contract。
- local paper orders、cash、positions、idempotency keys 只存在 process memory，restart 後消失。
- legacy `StockData`、Kbar、position/simulation 金額仍使用 `float`，volume 單位在部分路徑仍不夠明確。
- 沒有共用 ReplayClock、dataset manifest、journal-derived projection 或 deterministic digest gate。
- 沒有可被 manual 與 future strategy commands 共用的完整 RiskGate。
- Quote vs Tick+BidAsk 的 production criteria、reconnect、長樣本與多-symbol qualification 尚未通過。
- Dashboard 主頁的 CSS/HTML/JavaScript 集中於單一檔案，功能持續增加後會降低可測試性。
- `pyproject.toml` 宣告 pytest dev extra，但目前系統 Python 尚未安裝；repo 也沒有可見的 default CI workflow。

## 4. Scope、不變條件與非目標

### In scope

- Canonical event identity、schema version、event/received time 與 source stream semantics。
- Bounded ingestion queue、per-stream monotonic update、duplicate handling、stale/gap/overflow health。
- PostgreSQL authoritative Journal/projection（待 D1 review），以及 in-memory test adapter。
- Immutable source/research capture manifest、SHA256、replay dataset reader。
- SystemClock／ReplayClock、fast Replay 與 paced Replay。
- Candidate／BuyScore／Exit/local paper 的 deterministic projection parity。
- RiskGate 基礎與 manual local-paper command 的統一路徑。
- Quote parity evidence completion、market-data Shadow、operational observability。
- Dashboard projection schema、frontend modules、polling/SSE transport boundary。
- Default CI、PostgreSQL integration test、credentialed test isolation。

### 不變條件

1. `python app.py` 與既有 Dashboard snapshot/history 在 feature flags 關閉時維持目前行為。
2. HTTP refresh 不得成為行情 runtime clock，也不得因 browser polling 呼叫 Shioaji snapshot/account API。
3. Tick 與 BidAsk 是不同 source streams，不假設同 timestamp 可形成全域 total order。
4. 舊資料、duplicate、gap、overflow、session mismatch 或 stale 不得被靜默接受。
5. DataHealth 非 healthy 時不產生新的 entry opportunity；仍允許退出建議、查詢與 recovery。
6. 所有研究設定、schema、dataset、feature、signal、risk 與 fill model 均有 version。
7. UI 只顯示後端 projection，不在 JavaScript 重算策略、風險或損益 source of truth。
8. 不新增任何 live-money mode、broker credentials、CA 或 Shioaji order callback。

### Out of scope

- 微服務拆分、Kafka/Pulsar、Kubernetes、跨區 HA。
- 全市場 Tick/BidAsk 訂閱。
- 未經證據 review 的 Momentum threshold 調參。
- Authenticated Shioaji Simulation 與券商 reconciliation。
- 真錢交易、LiveBroker、production account。
- ML signal、漲停機率或績效保證。

## 5. Target boundaries and dependency rules

### 5.1 Bounded contexts

| Context | 責任 | 不可依賴 |
|---|---|---|
| Market Data | normalize、order、health、latest/recent projections | Dashboard、strategy UI、broker models |
| Discovery | Scanner/AUTO/MANUAL/POSITION → CandidatePool | Shioaji SDK concrete types、HTTP |
| Decision | Candidate、BuyScore、Exit、Momentum evidence | Journal adapter、FastAPI、PostgreSQL client |
| Risk/Commands | validate command、DataHealth、portfolio/cash/exposure、idempotency | Browser DOM、Shioaji SDK |
| Simulation/Execution | local fill/order/portfolio projections | Candidate rules internals、HTTP request objects |
| Presentation | FastAPI DTO、Dashboard rendering、transport | provider SDK、risk calculations、strategy formulas |
| Infrastructure | Shioaji、PostgreSQL、filesystem、clock adapters | 反向被 domain import |

### 5.2 Dependency rules

- Domain models與ports不得 import FastAPI、Shioaji、psycopg 或 filesystem implementation。
- Application services依賴 ports；composition root注入 concrete adapters。
- HTTP route只負責 parse、呼叫 application service、map response/error。
- Shioaji callback只做 defensive mapping與non-blocking enqueue，不更新策略或持倉。
- PostgreSQL/Filesystem adapter不得決定 signal/risk business rule。
- Compatibility facade可以暫時產生既有 `StockData`／`RealtimeQuoteUpdate`，但 canonical source逐步改為 normalized events。

## 6. Shared contracts

### 6.1 EventEnvelope

沿用既有 `TickEvent`／`BidAskEvent` payload，外層統一保存：

- `event_id`
- `schema_version`
- `session_id`／`session_date`
- `source`、`source_mode`、`stream_kind`
- `symbol`
- `event_at`（Asia/Taipei aware）
- `received_at`（aware local receipt time）
- `ingress_sequence`（process-local ordering）
- `source_identity`／來源可用 sequence
- `payload`
- `raw_capture_id`／dataset manifest identity（若存在）

規則：

- source有stable id時直接使用；沒有時，live使用session/stream/ingress sequence，Replay使用manifest hash + row index。
- 不用完整內容 fingerprint 去重合法的相同價量成交。
- `event_at` 不能取代 `received_at`；negative source latency需記錄clock-skew狀態。
- event immutable；修正資料產生新的correction record，不UPDATE歷史事件內容。

### 6.2 Ingestion result

每次 ingest 回傳 typed result：

- `APPLIED`
- `DUPLICATE`
- `OUT_OF_ORDER_REJECTED`
- `SESSION_MISMATCH_REJECTED`
- `INVALID_REJECTED`
- `HEALTH_BLOCKED`

結果包含 `event_id`、symbol/stream、previous watermark、new watermark、reason code 與 health transition。這讓測試、metrics 與 Journal 使用同一語意。

### 6.3 DataHealth

第一版狀態：

```text
STARTING → HEALTHY → DEGRADED → BLOCKED
               ↑         │          │
               └─────────┴─ verified recovery / resync
```

至少追蹤：

- connection/subscription ack
- last event/received times per symbol and stream
- duplicate/out-of-order/session mismatch counts
- queue depth/high-water mark/overflow
- source clock skew
- stale age and missing required streams
- reconnect epoch and resync status

`BLOCKED` triggers：queue overflow、unresolved sequence gap、session mismatch、invalid instrument reference、required stream stale超限。Recovery必須有新epoch/resync evidence，不可只因收到下一筆資料自動轉healthy。

### 6.4 Clock port

```text
Clock.now()
Clock.sleep_until(event_at)
Clock.session_date()
```

- `SystemClock` 供 realtime Shadow/local paper。
- `ReplayClock` 供 fast/1x/倍率 replay。
- Domain logic不得直接呼叫 `datetime.now()`。
- Backtest與paced Replay只切換clock speed，不切換策略、risk或projection code。

### 6.5 Journal port

```text
append(record) -> AppendResult
append_many(records) -> AppendBatchResult
load_session(session_id, after_sequence=None)
checkpoint_projection(name, session_id, sequence, digest)
```

append必須支援idempotent unique key；Journal append與projection checkpoint需有明確transaction boundary。任何未journal的side effect都不可發生。

### 6.6 Risk decision

輸入：

- command/intent identity and origin
- DataHealth snapshot
- instrument reference and market status
- latest book/trade freshness and spread
- cash、portfolio、pending orders、session PnL
- position/notional/daily-loss/re-entry policies

輸出：`APPROVED`／`REJECTED`／`BLOCKED`、version、reason codes、approved share quantity、normalized limit price、evaluated-at與input identities。

## 7. Persistence proposal

### 7.1 Authoritative source

本 plan 預設 PostgreSQL 是 persistent mode 的唯一 authoritative operational Journal/projection store：

- in-memory repository只用於unit tests與explicit ephemeral mode。
- SQLite WAL可保留為local development adapter，但啟用PostgreSQL後不得雙寫成第二個primary。
- raw capture JSON/JSONL/Parquet可作immutable source evidence；不能取代order/portfolio Journal。

此選擇需在Phase 0 Gate G0 review確認。若確定永遠single-process/local-only，可在implementation前把authoritative adapter改為SQLite WAL；port與schema語意不變。

### 7.2 Initial schema families

- `sessions`：mode、provider/SDK version、timezone、config versions、started/ended/recovery status。
- `market_events`：envelope columns + JSONB payload + source/capture identity。
- `health_events`：state transition、reason、watermarks、queue/reconnect evidence。
- `decision_records`：Candidate/score/signal/exit input identity與versioned result。
- `command_records`：manual/strategy origin、idempotency key、risk result。
- `order_events`：local-paper order lifecycle；未來可延伸normalized broker events。
- `projection_checkpoints`：projection name、last journal sequence、digest、schema version。

Constraints/indexes：

- unique `(session_id, event_id)`。
- unique `(command_scope, idempotency_key)`。
- monotonic journal sequence。
- indexes on `(session_id, symbol, stream_kind, event_at)` and projection checkpoint。
- append-only tables禁止application UPDATE/DELETE；correction使用新record。

### 7.3 Restart contract

1. 開新process時讀取latest valid checkpoint。
2. 從checkpoint sequence後重播Journal。
3. 計算projection digest並與checkpoint驗證。
4. mismatch時標記`RECOVERY_REQUIRED`，禁止新entry/order。
5. local-paper orders/cash/positions/idempotency恢復完成後才開啟mutation route。

## 8. Implementation phases

### Phase 0 — Baseline, decisions, and CI bootstrap

目標：在改runtime前建立可重現baseline與review決策。

工作：

1. 凍結目前snapshot/history/local-paper API fixtures與100-test historical baseline。
2. 建立fresh environment bootstrap：`python -m venv`、`pip install -e '.[dev]'`、full pytest。
3. 新增default CI draft：Python 3.11/3.12、MockProvider、compileall、pytest、JS parse、`git diff --check`。
4. 確認D1 storage、D2 pilot symbols、D3 event retention、D4 stale thresholds、D5 SDK pin、D6 localhost/deployment boundary。
5. 凍結EventEnvelope、DataHealth reasons、Clock與Journal port schema version。
6. 為所有新runtime flag設定default off。

Gate G0：

- clean checkout能安裝dev dependencies並執行完整tests。
- current APIs/golden fixtures已保存。
- D1-D6 review完成；無未決的authoritative storage或time/unit語意。
- CI不載入Shioaji credentials、不執行network/broker tests。

### Phase 1 — Composition root and ports without behavior change

目標：先建立可替換邊界，不搬移business logic。

工作：

1. 建立`runtime/composition.py`，集中provider、clock、journal、health、simulation與dashboard service wiring。
2. 建立`MarketEventSource`、`JournalRepository`、`ProjectionRepository`、`Clock`、`OrderCommandHandler` ports。
3. FastAPI dependencies改由composition root提供；保留既有routes與payload。
4. 建立in-memory adapters，讓全部application use cases無需DB/network即可測試。
5. `run_scan()`維持one-shot snapshot use case，不塞入stream loop。

Gate G1：

- snapshot/history/simulation API golden fixtures無差異。
- domain/application modules無FastAPI/Shioaji/psycopg imports。
- MockProvider與in-memory repositories可完整啟動Dashboard tests。
- feature flags off時行為與目前版本一致。

### Phase 2 — Ordered ingestion, model normalization, and DataHealth

目標：建立canonical live/replay ingest path。

工作：

1. Shioaji/Mock/Replay adapters輸出EventEnvelope + normalized payload。
2. callback進入bounded queue；記錄depth/high-water/overflow，不做strategy或fill。
3. consumer按`symbol + stream_kind + session`維持watermark；舊資料不可覆蓋新projection。
4. 將`RealtimeQuoteUpdate`保留為compatibility output，由canonical event投影產生。
5. 建立`LatestMarketProjection`、`RecentBarStore`、`OrderBookProjection`。
6. price/money/tick boundaries使用Decimal；quantity在domain內使用shares，source volume明確lots/shares。
7. DataHealth status/reasons加入local query projection，但暫不改任何entry行為。

Gate G2：

- 同一fixture的duplicate/out-of-order/session-reset/overflow結果固定。
- Tick與BidAsk各自monotonic，不建立假的跨stream total order。
- queue overflow測試必定使DataHealth `BLOCKED`，silent drop為0。
- canonical event與legacy DTO dual-read結果在fixture上相同。
- 既有Candidate/score/Kbar/local-paper tests全過。

### Phase 3 — PostgreSQL Journal and restart recovery

目標：讓event、health、decisions與local-paper state可稽核、可恢復。

工作：

1. 加入migration tool與forward-only SQL migrations。
2. 實作PostgreSQL Journal adapter與transactional append/idempotency。
3. ingest順序改為validate → append → apply projection → checkpoint。
4. 保存session/provider/SDK/config/schema metadata。
5. local-paper order/position/cash/idempotency改為journal-derived projection。
6. 建立restart/rebuild command，不從Dashboard route執行migration或full rebuild。
7. raw capture artifact保存manifest、SHA256、row count、min/max time與schema version。

Gate G3：

- duplicate append不產生第二筆logical event/command。
- transaction failure不更新projection checkpoint。
- restart後orders/cash/positions/idempotency與restart前digest相同。
- corrupted/missing checkpoint fail closed並可由Journal full replay復原。
- SQL migration從empty DB與前一版本都能成功，rollback策略已演練。

### Phase 4 — Deterministic Replay and shared projections

目標：讓相同dataset可以多次產生相同決策與投影。

工作：

1. 實作manifest-validated `ReplayEventSource`、SystemClock、ReplayClock。
2. fast Replay與paced Replay共用同一session/application kernel。
3. 先接completed BAR_1M；Tick/BidAsk replay在事件資料通過後加入。
4. Candidate、BuyScore、Exit、local-paper fill/projection輸出versioned digest。
5. 明確執行時序：bar close訊號不可在同一bar內成交。
6. 產生replay report：dataset/config/code identity、events、health、decisions、orders、fills、PnL digest。

Gate G4：

- 同dataset執行10次得到相同events/decisions/orders/positions/digest。
- fast與1x Replay結果一致，只允許wall-clock duration不同。
- naive timestamp、manifest mismatch、future data、out-of-order fixture皆fail closed。
- Replay不呼叫network、SystemClock或Shioaji SDK。

### Phase 5 — RiskGate and local-paper command migration

目標：在任何future strategy command前，先讓manual local-paper走完整安全路徑。

工作：

1. 建立`OrderApplicationService`與typed Manual/Strategy command origins。
2. 建立RiskGate v1：DataHealth/freshness、market/session status、cash、position/notional、pending duplicate、spread/book freshness、daily loss。
3. normalize limit price/tick與lots→shares conversion；不把broker enums放入domain。
4. command → risk → journal → local simulator；route不得直接呼叫`SimulationService.submit_order()`。
5. 把現有`SimulationService`逐步縮為LocalPaperBroker/Projection adapter，維持UI相容facade。
6. strategy origin仍disabled；只測試被RiskGate阻擋，不開自動下單。

Gate G5：

- 每個allowed/rejected/blocked command都能回溯input event與risk version/reasons。
- retry/double-click/restart不產生第二筆order。
- stale/disconnected/blocked DataHealth拒絕新BUY；query/cancel/recovery仍可執行。
- 金額、股數、張數、tick與PnL守恆測試通過。
- browser/manual與future strategy沒有第二條bypass path。

### Phase 6 — Provider qualification and live-data Shadow

目標：完成資料來源Gate，驗證live runtime但不產生broker side effects。

工作：

1. 凍結Quote parity production criteria，再做多-symbol、長時段、reconnect captures。
2. 驗證trade/book count、terminal cumulative values、p50/p95/p99 relative latency、gaps、book parity、derived digests。
3. 完成raw tick-side mapping與source clock calibration；未完成欄位保持UNVERIFIED。
4. 依Gate選定Quote或Tick+BidAsk fallback；capacity/headroom跟著已驗證mode設定。
5. 啟動live-data Shadow：只更新projection、signals、health與Journal，不建立order command。
6. shutdown順序：stop producer → drain queue → flush Journal/checkpoint → close session。

Gate G6：

- source mode有明確PASS或fallback決定，無optimistic default。
- Shadow期間silent drop=0、duplicate alert=0、overflow/gap均有health record。
- disconnect/reconnect/shutdown/restart tests通過。
- browser polling只讀local projection，不增加Shioaji request cadence。
- 全程`subscribe_trade=False`，無CA、order callback或order API。

### Phase 7 — Research evidence and hypothesis promotion

目標：把可重播runtime轉為可信research流程。

工作：

1. Momentum plan使用同一Journal/Replay/Clock/DataHealth，不建立平行pipeline。
2. 凍結dataset manifests、calendar、universe、labels、feature schema與hypothesis config。
3. 分開IS/Validation/OOS；先預註冊minimum recall、false alerts/day、lead time與coverage gates。
4. 報告missing coverage、discovery miss、capacity eviction、data incomplete與signal false。
5. threshold只以新version promotion，不覆寫`hypothesis_v0`。
6. 通過前僅顯示evidence/signal，RiskGate與entry保持BLOCKED。

Gate G7：

- Replay report可由manifest+config重現。
- 無look-ahead、survivorship、same-bar fill或post-close universe leakage。
- OOS/forward evidence review完成前不產生`validated_v1`。
- detector Gate不自動授權Simulation或broker order。

### Phase 8 — Dashboard modules, transport, and operator UX

目標：在projection contracts穩定後改善前端可維護性與資料健康可見性。

工作：

1. 保留Vanilla JS，先把單一`index.html`拆成state/api/candidate/chart/simulation/health modules；暫不引入SPA framework。
2. API responses加入`schema_version`、`session_id`、`as_of`、mode與DataHealth摘要。
3. Header顯示provider mode、stream age、queue/reconnect health、Journal/replay status。
4. Candidate/Kbar/positions/orders UI不自行重算risk、score或PnL source of truth。
5. 保留2秒local projection polling；需要更低延遲時增加SSE，polling保留fallback。
6. SSE/WebSocket transport只推projection event，不把瀏覽器變成provider cadence owner。
7. 新增accessible loading/error/stale/blocked/recovering states與browser tests。

Gate G8：

- 前端modules可獨立語法測試；主要interaction有browser/API contract coverage。
- polling與SSE對相同projection sequence不重播alert/order state。
- stale/blocked在一個UI refresh interval內可見。
- feature flag關閉後仍可使用目前Dashboard layout與API。

## 9. Testing strategy

| 層級 | 必要測試 |
|---|---|
| Domain unit | Event/time/unit invariants、DataHealth transitions、Risk reason codes、Decimal/tick/quantity boundaries |
| Ingestion | duplicate、out-of-order、cross-stream、session reset、stale、queue overflow、reconnect epoch |
| Persistence | migration、unique/idempotency、transaction rollback、checkpoint、restart/full rebuild |
| Golden Replay | 同dataset 10次digest一致、fast/1x parity、no network/wall-clock |
| Decision parity | snapshot與event projection對Candidate/score/exit相容fixtures一致 |
| Local paper | command idempotency、cash/position conservation、bid/ask fill、cancel/restart |
| API contract | current routes backward compatibility、schema version、blocked/error mapping |
| Frontend | JS modules parse、period/hover/order/positions/health interactions |
| PostgreSQL integration | disposable DB migrations、append/replay/restart；default CI可執行 |
| Provider mapping | fake SDK default CI；credentialed market-hours tests另設manual/scheduled workflow |
| Safety audit | source scan確認無`place_order`、CA activation、trade callback或live mode wiring |

不得以「可以import」或「route回200」作為Gate完成證據；必須驗證state、digest、idempotency與recovery semantics。

## 10. Observability

### Market data

- events received/applied/duplicate/rejected by source/symbol/stream
- queue depth/high-water/overflow
- last event/received age、clock-skew counts
- subscription requested/acked/failed/evicted、capacity used/headroom
- DataHealth state/reason duration and transitions

### Journal/Replay

- append latency/failures/retries
- last durable sequence/checkpoint lag
- recovery/full replay count and duration
- projection digest mismatch
- replay event rate、determinism failures、dataset/config identities

### Commands/Risk/local paper

- command counts by origin/result/reason
- idempotent retries and duplicate suppression
- pending/fill/cancel/reject counts
- cash/position invariant failures
- blocked mutation requests while DataHealth unhealthy

### Dashboard

- projection schema/version mismatch
- polling/SSE reconnects and sequence gaps
- stale projection age
- UI/API error rates without logging credentials or full account identity

## 11. Migration strategy

1. Add ports/composition and CI with all newflags off。
2. Run canonical events in observe-only dual projection; current snapshot remains source for user-visible decisions。
3. Compare legacy/canonical digests and log differences; do not silently switch。
4. Enable Journal append for market/health first, then decision/local-paper records。
5. Rebuild projections in Shadow and compare with process-memory projections。
6. Move local-paper reads to Journal-derived projection only after restart/idempotency Gate passes。
7. Move commands behind Risk/ApplicationService while preserving current API facade。
8. Enable realtime Shadow only after provider qualification。
9. Refactor frontend modules last, against stable projection fixtures。

每一步都應有feature flag與one-way migration。舊資料不刪除、不原地轉寫；需要重算時建立新projection/schema version。

## 12. Rollback

- 所有新runtime、Journal persistence、Shadow、SSE與Risk enforcement都有獨立flag，default off。
- Gate失敗時停止新consumer/runner，保留append-only evidence，回到上一個verified projection。
- PostgreSQL migration採forward fix；不以破壞性down migration刪除Journal records。
- canonical event切換前保留legacy adapter；rollback只切read/projection owner，不雙寫兩個primary。
- UI modules/SSE可退回single-page + polling，不影響backend runtime。
- local-paper persistent mode失敗時可退回明確標示的ephemeral mode，但不得假裝已恢復orders/positions。
- 不存在LiveBroker或真錢mode，因此不需要真錢rollback流程。

## 13. Expected file map

```text
market_data/
  events.py                     # extend: EventEnvelope/schema identity
  health.py                     # new: DataHealth state/reasons/snapshot
  ports.py                      # new: event source/sink/projection ports
  ingestion.py                  # new: ordered consumer + ingest result
  recent_store.py               # new: latest/recent bar/book projections
  clock.py                      # new: Clock/SystemClock/ReplayClock contracts
  provider.py                   # compatibility facade; SDK details stay adapter-only
  shioaji_stream.py             # new: callback -> canonical events
  quote_qualification.py        # existing provider Gate

runtime/
  composition.py                # new: dependency wiring / composition root
  session.py                    # new: shared event-driven application kernel
  replay.py                     # new: fast/paced replay runner
  shadow.py                     # new: live-data no-order runner
  config.py                     # new: typed fail-closed modes/flags

trading/
  models.py                     # new: commands/intents/risk/order records
  journal.py                    # new: Journal domain port/record contracts
  risk.py                       # new: mode-independent RiskGate
  application.py                # new: one manual/future-strategy command path
  queries.py                    # new: session/order/portfolio read models

infrastructure/
  postgres/
    journal.py                  # new: PostgreSQL adapter
    projections.py              # new: checkpoint/read adapters
    migrations/                 # new: forward SQL migrations
  filesystem/
    captures.py                 # new: immutable manifests/artifacts

replay/
  dataset.py                    # new: manifest validation/event reader
  report.py                     # new: digest/evidence report

simulation/
  service.py                    # migrate: compatibility facade
  local_paper.py                # new: local fill adapter/application behavior

dashboard/
  server.py                     # thin route adapter + composition dependencies
  service.py                    # stable query projection composition
  static/
    index.html                  # shell/layout
    js/state.js
    js/api.js
    js/candidates.js
    js/chart.js
    js/simulation.js
    js/health.js

tests/
  fixtures/replay/
  test_market_ingestion.py
  test_data_health.py
  test_journal_postgres.py
  test_restart_recovery.py
  test_replay_determinism.py
  test_risk_gate.py
  test_order_application.py
  test_dashboard_contracts.py

.github/workflows/
  ci.yml                        # default no-credentials CI
  market_data_qualification.yml # manual/scheduled credentialed workflow
```

新增packages時同步更新`pyproject.toml` package discovery，並做wheel/install/import smoke，避免editable install可用但build artifact漏檔。

## 14. CI/CD plan

### Default pull-request CI

1. Python 3.11/3.12 matrix；先不把native Shioaji compatibility與domain tests綁在同一job。
2. `pip install -e '.[dev]'`。
3. `python -m compileall -q app.py dashboard market_data candidate scoring position simulation signals`。
4. `pytest tests/ -q`，之後加入coverage threshold。
5. Dashboard JavaScript module parse與API fixture checks。
6. PostgreSQL service job跑migration/integration/restart tests。
7. package build/install/import smoke。
8. secret scan與safety grep；MockProvider/default flags不得登入Shioaji。

### Credentialed market-data qualification

- manual或market-hours scheduled workflow。
- protected environment/secrets，不對fork PR開放。
- 只允許`subscribe_trade=False`與bounded symbol/duration。
- artifact移除credentials/account identity，保存SDK version、manifest、SHA256與cleanup結果。
- failure不自動切換production source mode，只產生review evidence。

### Deployment boundary

- 第一版仍是localhost/single-user local application。
- 若要remote/multi-user deployment，需另開review：authentication、authorization、TLS、CSRF、secret storage、PostgreSQL backup、process ownership與single Shioaji session。
- CI/CD成功不等於strategy或market-data Gate通過；Gate evidence需人工review。

## 15. Definition of Done

1. Market events具有明確identity、session、schema、timezone、source stream與unit語意。
2. Duplicate/out-of-order/gap/stale/overflow不會靜默改變projection；DataHealth可觀測且fail closed。
3. PostgreSQL Journal是persistent mode唯一authoritative write path；restart可重建相同projection digest。
4. 相同dataset執行10次、fast Replay與paced Replay產生相同decision/order/position digest。
5. Candidate/BuyScore/Exit與現有Dashboard API在compatibility flags下無回歸。
6. local-paper manual commands經同一ApplicationService、RiskGate、idempotency與Journal；strategy origin仍disabled。
7. Quote/Tick+BidAsk source mode由reviewed parity evidence決定，reconnect/shutdown/clock-skew有證據。
8. Momentum共用同一event/health/replay基礎；hypothesis未經G7不升級為validated。
9. Dashboard顯示mode、as-of與DataHealth，且browser不直接控制provider cadence。
10. Default CI可在無credentials環境完成full tests、PostgreSQL integration、JS/package/safety checks。
11. 任一新feature flag關閉時能回到上一個verified mode，且不刪除歷史evidence。
12. 專案仍沒有CA、Shioaji order API、LiveBroker或真錢交易路徑。

## 16. Review decisions required before implementation

| ID | 決策 | Plan預設 |
|---|---|---|
| D1 | Authoritative persistent Journal | PostgreSQL；in-memory僅tests，SQLite僅optional dev adapter |
| D2 | Pilot universe | 少量明確symbol；不做全市場streaming |
| D3 | Raw/Journals retention | 先保留完整pilot sessions，期限與archive policy待確認 |
| D4 | DataHealth thresholds | 以source/stream分別設定並versioned；不得使用單一全域秒數 |
| D5 | Shioaji SDK | 以已驗證版本建立compatibility matrix，再pin supported range |
| D6 | Web exposure | localhost、single-user |
| D7 | Decimal migration | canonical events/risk/journal先改；legacy UI/Kbar DTO compatibility逐步轉換 |
| D8 | SSE | polling保留；projection contracts穩定後才啟用 |
| D9 | CI Python versions | 3.11/3.12 default；3.13與Shioaji另設compatibility evidence |

Review同意D1-D9後才開始Phase 0實作；若任一決策改變，先更新此plan與acceptance criteria，不直接在code中猜測。
