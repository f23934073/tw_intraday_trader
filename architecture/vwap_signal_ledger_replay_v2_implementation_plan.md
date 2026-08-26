# R5 Contract Revision 2 — VWAP Signal-Ledger One-Lot Replay

## 1. Executive decision

R5 revision 1 已正式執行並以 fail-closed 結束：

```text
Baseline Run: run-91ad87981676414da87b928398fa43c9
Revision-1 Control Run: run-4de8112d3a154148a1af93fc86a26f83
R5 v1 verdict: INVALID / ACCEPTANCE REJECTED
R6: BLOCKED / NOT AUTHORIZED
```

Revision 1 的兩個根本問題不能靠放大資金或調整 `position_fraction` 修補：

1. `current_equity × position_fraction` 會隨前序損益、剩餘現金與持倉路徑改變
   shares，無法保證每個訊號都取得相同曝險。
2. 重新跑 portfolio engine 會先撮合 pending order、改變 position，再決定是否評估
   新 ENTRY。Admission 一改，後續 signal stream 本身也會改變，signal parity 因而
   具有 path dependence。

R5 contract revision 2 改採：

```text
immutable baseline ENTRY evidence
→ canonical Signal Ledger
→ deterministic entry/exit match plan
→ independent one-lot Replay Episodes
→ fail-closed postflight
→ signal-level research evidence
```

Contract identity 凍結為：

```text
control_contract_version = r5-signal-ledger-replay-v2
request_schema_version = r5-signal-ledger-replay-request-v2
preflight_schema_version = r5-signal-ledger-replay-preflight-v2
result_schema_version = r5-signal-ledger-replay-result-v2
postflight_schema_version = r5-signal-ledger-replay-postflight-v2
algorithm_identity = independent-one-lot-next-open-to-session-close-v2
```

本文件只授權設計 Review。未通過 G0 前，不得新增 migration、建立 preflight、
建立 replay、寫入 PostgreSQL 或開始 R6。

## 2. Research question and non-goals

Revision 2 只回答：

> 對 baseline 已經產生的完整 VWAP ENTRY signal population，在每筆訊號都以獨立
> 一張、固定 next-open entry 與 EOD exit 計算時，成本前與成本後是否存在正 edge？

Revision 2 不回答：

- 共享資金下可以同時持有多少部位。
- 真實 portfolio equity、CAGR、drawdown、Sharpe 或 buying power。
- 訊號互斥、部位合併、同 symbol owner 或 pending-order policy。
- 策略在另一條 state path 上是否還會產生相同 signals。
- Local Paper、broker 或 real-money 可執行性。
- Strategy Qualification；目前 Dataset 仍是 `research_eligible=false`。
- Baseline portfolio path 中從未被評估、因此也未寫入 order evidence 的反事實
  signals。Revision 2 的母體是 128,802 筆 **baseline-observed signals**，不是重新
  計算「完全無持倉限制時所有可能觸發」。

重疊 episodes 是允許的研究觀測，不是可同時執行的部位。任何 UI、API、報告與
database projection 都必須使用 `Research Replay`／`Modeled Episode`，不得稱為
下單、成交持倉或可部署 portfolio。

## 3. Frozen invariants

### 3.1 Removed path-dependent inputs

下列欄位不得存在於 revision-2 request、preflight、episode calculation 或 result：

```text
starting_cash
position_fraction
current_equity
available_cash
portfolio_positions
pending_orders
same_symbol_position_owner
allocation_rank
```

Strict schema 遇到上述欄位或其他 unknown field 一律拒絕。Revision 2 不提供
`C/f` 推導，也沒有 cash rejection 這個結果狀態。

### 3.2 No strategy re-evaluation

Revision 2 不得呼叫：

- `HistoricalBacktestEngine.run()`。
- `StrategyRegistry.evaluate()`。
- Atomic Strategy adapter／Feature Engine 計算新的 ENTRY 訊號。
- current Strategy Template Registry 來重建 signals。

Strategy、Feature、amount 與 implementation identities 只用於驗證 baseline lineage，
不是 revision-2 runtime input。Runtime 若出現 strategy evaluation count，postflight
必須失敗。

### 3.3 One signal, one independent episode

每筆 canonical signal 必須恰好產生一筆 modeled episode：

```text
signal_count
= matched_entry_count
= matched_exit_count
= episode_count
= modeled_entry_count
= modeled_exit_count
```

每筆 episode 固定 `shares = baseline.min_lot_shares`；本 baseline 為 1,000 股。
Episode 間不共享 state，排序、前序盈虧與重疊不得改變任何一筆 episode 的結果。

## 4. Canonical Signal Ledger

### 4.1 Authority

Ledger authority 是 baseline Run durable result chunks 中的全部 `side=ENTRY`
`TradeDecision`。完整 decisions list 已被 baseline `result_digest` 保護；建立 ledger
前必須重算既有 result digest。Orders/fills 不在該 digest，因此不是 signal authority。

建立 ledger 前必須重驗：

- baseline status 為 `COMPLETED`。
- `digest(config_json) == config_digest`。
- Run row Dataset identity 與 config snapshot 相同。
- baseline result digest 可從 summary、trades、equity、decisions 重建。
- 由 result-digest-bound ENTRY decisions 重建的 count、semantic multiplicity digest
  分別等於 128,802 與 v1 approved preflight 保存的 signal multiplicity digest。
- v1 terminal registration/postflight 為 `INVALID`，且 digest 可重建。

任何漂移都 fail closed，不可用目前 Registry 或重新跑策略來修補。

與 v1 preflight 比對時，必須從每個 authoritative decision 建立 exact v1-compatible
token：

```json
{
  "created_at": "<decision event_at canonical timestamp>",
  "primary_strategy_id": "<decision primary_strategy_id>",
  "symbol": "<decision symbol>",
  "triggered_strategy_ids": ["<ordered decision member IDs>"]
}
```

Grouped multiplicity digest 必須等於 v1 保存值；revision-2 semantic_key 額外包含
policy/horizon，兩者是不同且各自明名的 digest，不可互換。

Orders 只做 v2 inception derivation check：在建立第一份 v2 ledger 時，current ENTRY
orders 與 authoritative ENTRY decisions 必須依 `decision_id` 一對一雙向對應，且
`symbol`、`created_at == event_at`、normalized `execution_horizon`、
`primary_strategy_id`、`triggered_strategy_ids` 全部一致。每個 decision/order 恰好
一次；extra、missing、duplicate 或欄位差異都拒絕。

通過後保存 `v2_inception_order_derivation_rows_sha256` 與
`v2_inception_order_derivation_digest`。這是 **v2 inception seal**，不是歷史 v1
seal-time evidence，也不改變 decisions 的 authority。後續 read/execute/postflight
都重算 current order derivation 並與 inception seal 比對；漂移即 fail closed。

### 4.2 Canonical wire format

所有 revision-2 artifact 共用下列 exact format：

- Encoding：UTF-8、無 BOM；所有 string 必須已是 Unicode NFC。
- Canonical JSON：既有 `canonical_json()`，即 `ensure_ascii=false`、object keys
  lexicographic sort、separators `(',', ':')`、無額外 whitespace。
- JSONL：每列 `canonical_json(row) + '\n'`；禁止空白列，最後一列必須有 LF。
- SHA-256：對 exact UTF-8 bytes 計算 lowercase 64-hex。
- Timestamp：先轉 `Asia/Taipei`，再輸出 `YYYY-MM-DDTHH:MM:SS+08:00`；禁止
  microseconds、`Z` 或 offset alias。
- Date：`YYYY-MM-DD`。
- Integer：JSON integer，不接受 float、string 或 boolean；count/sequence 非負，
  sequence 從 1 開始。
- Boolean：JSON `true/false`。
- Decimal：JSON string；用 plain base-10，禁止 exponent、leading `+`、trailing
  zero、trailing dot 與 negative zero；zero 唯一表示為 `"0"`。
- Calculation context：precision `38`、rounding `ROUND_HALF_EVEN`。價格、金額與
  rate 保留 context 計算結果；兩個 return 欄位 quantize 至小數 18 位後再用上述
  Decimal string normalizer。不得使用 JSON number 或 binary float。
- Exact schema：每個 object 的 actual key set 必須等於本文件列出的 key set；
  missing/unknown key 都拒絕。
- `digest(body)`：除明示 self-digest 欄位外，對 exact body 呼叫既有 `digest()`。
  JSONL rows digest 一律對 bytes 計算，不先 parse/re-serialize。

Algorithm contract projection 固定為 exact object：

```json
{
  "calculation_precision": 38,
  "calculation_rounding": "ROUND_HALF_EVEN",
  "canonical_json": "BACKTEST_CANONICAL_JSON_V1",
  "contract_version": "r5-signal-ledger-replay-v2",
  "entry_semantics": "NEXT_OBSERVED_SYMBOL_KBAR_OPEN_STRICTLY_AFTER_SIGNAL_V1",
  "exit_semantics": "FIRST_LATER_OBSERVED_SYMBOL_SESSION_CLOSE_V1",
  "name": "independent-one-lot-next-open-to-session-close-v2",
  "return_scale": 18,
  "shares_semantics": "EXACT_BASELINE_MIN_LOT_SHARES_V1",
  "timezone": "Asia/Taipei"
}
```

`algorithm_contract_digest = digest(algorithm_contract_projection)`；實作另保存對
`backtest/research_replay/domain.py` exact source bytes 計算的
`algorithm_implementation_digest`。兩者都是所有 manifest 的必填欄位。

### 4.3 Exact inception order-derivation row

每列 key set 與型別固定為：

| Field | Type / invariant |
|---|---|
| `schema_version` | string literal `r5-order-derivation-row-v2` |
| `sequence` | integer `>= 1`，與 ledger sequence 相同 |
| `signal_id` | lowercase SHA-256 |
| `semantic_key` | lowercase SHA-256，等於 ledger semantic_key |
| `baseline_run_id` | non-empty string |
| `baseline_decision_id` | non-empty string，unique |
| `baseline_order_id` | non-empty string，unique |
| `symbol` | non-empty string |
| `signal_at` | canonical timestamp；等於 decision `event_at` 與 order `created_at` |
| `side` | string literal `ENTRY` |
| `execution_horizon` | string literal `INTRADAY_NEXT_BAR`；source missing/null 正規化為此值 |
| `primary_strategy_id` | non-empty string |
| `triggered_strategy_ids` | ordered JSON string array，至少一項 |

Rows 依 ledger sequence 排序。Derivation digest exact projection：

```json
{
  "row_count": 128802,
  "rows_sha256": "<exact JSONL bytes sha256>",
  "schema_version": "r5-order-derivation-projection-v2"
}
```

`v2_inception_order_derivation_digest = digest(projection)`。

### 4.4 Exact Signal Ledger row

每列 canonical JSONL key set 固定為：

```json
{
  "authoritative_decision_digest": "<sha256>",
  "baseline_decision_id": "decision-...",
  "baseline_run_id": "run-...",
  "execution_horizon": "INTRADAY_NEXT_BAR",
  "policy": "ANY",
  "primary_strategy_id": "above_vwap_entry_v1",
  "schema_version": "r5-signal-ledger-row-v2",
  "semantic_key": "<sha256>",
  "sequence": 1,
  "side": "ENTRY",
  "signal_id": "<sha256>",
  "signal_at": "2023-08-21T09:02:00+08:00",
  "signal_session_date": "2023-08-21",
  "symbol": "2330",
  "triggered_strategy_ids": ["above_vwap_entry_v1"]
}
```

Field types/invariants：所有 ID/symbol/policy 是 non-empty string；sequence 是 integer；
`side` 固定 `ENTRY`；`execution_horizon` 固定 `INTRADAY_NEXT_BAR`；timestamp/date 使用
4.2 format；`triggered_strategy_ids` 是至少一項的 ordered string array；三個 digest
欄位是 lowercase SHA-256。

Identity/digest rules：

- `signal_id = digest({"baseline_decision_id": baseline_decision_id,
  "baseline_run_id": baseline_run_id})`，unique；兩個 key/value 都是 exact ledger
  field strings。
- `authoritative_decision_digest = digest(exact source TradeDecision.to_dict())`。
- `semantic_key` exact projection 為：

```json
{
  "execution_horizon": "<ledger execution_horizon>",
  "policy": "<ledger policy>",
  "primary_strategy_id": "<ledger primary_strategy_id>",
  "signal_at": "<ledger signal_at>",
  "symbol": "<ledger symbol>",
  "triggered_strategy_ids": ["<ordered ledger IDs>"]
}
```

  對此 object 呼叫 `digest()`；不含 status/order/fill。
- Canonical order 為 `(signal_at, symbol, baseline_decision_id)`；sequence 從 1 連續。
- `triggered_strategy_ids` 保留 baseline canonical order，不做 set conversion。
- 空白列、unknown field、non-canonical JSON、duplicate signal/decision/sequence 一律拒絕。

### 4.5 Exact Signal Ledger manifest

Manifest key set 固定如下；除 count/revision 是 integer 外，所有欄位是 string，
所有 `*_digest`/`*_sha256` 是 lowercase SHA-256：

```text
schema_version = r5-signal-ledger-manifest-v2
control_contract_version = r5-signal-ledger-replay-v2
baseline_run_id
baseline_config_digest
baseline_result_digest
baseline_entry_decision_count
baseline_entry_decision_projection_digest
v1_preflight_digest
v1_signal_multiplicity_digest
v1_invalid_postflight_digest
atomic_strategy_run_snapshot_digest
dataset_id
dataset_digest
dataset_manifest_digest
dataset_bars_sha256
dataset_binding_revision
dataset_amount_contract_digest
algorithm_contract_digest
algorithm_implementation_digest
order_derivation_row_schema_version = r5-order-derivation-row-v2
v2_inception_order_derivation_count
v2_inception_order_derivation_rows_sha256
v2_inception_order_derivation_digest
ledger_row_schema_version = r5-signal-ledger-row-v2
ledger_signal_count
ledger_rows_sha256
ledger_semantic_multiplicity_digest
ledger_manifest_digest
```

`baseline_entry_decision_projection_digest` exact projection：

```json
{
  "entries": [
    {
      "authoritative_decision_digest": "<sha256>",
      "baseline_decision_id": "decision-..."
    }
  ],
  "schema_version": "r5-entry-decision-projection-v2"
}
```

Entries 依 durable result decisions 的 stored order 過濾 `side=ENTRY`，不得重排。
每個 `authoritative_decision_digest` 對 exact source `TradeDecision` object 計算，
因此所有 evaluations/optional horizon 仍受 digest 保護，但 projection schema 本身
維持封閉。

`ledger_semantic_multiplicity_digest` projection exact key set 為
`schema_version="r5-signal-multiplicity-v2"` 與 `tokens`；`tokens` 是
semantic_key → integer count object，key 依 semantic_key 排序，再對整個 object
呼叫 `digest()`。

`ledger_manifest_digest = digest(manifest body excluding ledger_manifest_digest)`。Manifest
raw bytes 必須精確等於 `canonical_json(verified_manifest) + '\n'`。

Locator path、inode、建立 host 與 operation timestamp 只能進 operation audit，不進
immutable identity。同一 semantic source 在不同 clean root 建立，必須得到相同
ledger digests。

## 5. Deterministic match plan

### 5.1 Entry match

對每筆 signal：

```text
entry_bar = first observed Kbar
            where bar.symbol == signal.symbol
              and bar.timestamp > signal.signal_at
```

Entry 可跨 session，與 frozen `NEXT_OBSERVED_SYMBOL_KBAR_V1` 一致。不得加入
same-session filter。Raw entry price 是 `entry_bar.open`。

### 5.2 Exit match

Revision 2 對 `end_of_day_exit_v1` 凍結成不依賴 portfolio state 的明確語意：

```text
exit_bar = first observed same-symbol Kbar after entry_bar
           that is the last observed Kbar for that symbol/session
```

約束：

- `exit_bar.timestamp > entry_bar.timestamp`，不得在 entry event 同時出場。
- 若 entry bar 不是該 session 最後一根，使用該 session 的最後一根 close。
- 若 entry bar 已是該 session 最後一根，使用下一個 observed session 的最後一根
  close。
- Raw exit price 是 `exit_bar.close`。
- Dataset 結束前缺 entry 或 exit，整份 replay `INVALID`；不得丟掉該 signal。

這是 revision-2 research execution identity，不宣稱重現 engine 內部的 position/event
index state。它保留 next-open entry 與 EOD exit 的經濟語意，同時移除 portfolio path。

### 5.3 Match-plan row

每列 exact key set：

| Field | Type / invariant |
|---|---|
| `schema_version` | string literal `r5-match-plan-row-v2` |
| `sequence` | integer，等於 ledger sequence |
| `match_id` | lowercase SHA-256，unique |
| `signal_id` | lowercase SHA-256 |
| `semantic_key` | lowercase SHA-256 |
| `symbol` | non-empty string，等於 ledger symbol |
| `signal_at` | canonical timestamp，等於 ledger signal_at |
| `signal_session_date` | canonical date |
| `entry_bar_at` | canonical timestamp；嚴格晚於 signal_at |
| `entry_session_date` | canonical date |
| `entry_raw_open` | positive canonical Decimal string |
| `entry_bar_digest` | exact source bar JSON bytes 的 lowercase SHA-256 |
| `exit_bar_at` | canonical timestamp；嚴格晚於 entry_bar_at |
| `exit_session_date` | canonical date |
| `exit_raw_close` | positive canonical Decimal string |
| `exit_bar_digest` | exact source bar JSON bytes 的 lowercase SHA-256 |
| `holding_minutes` | integer `>= 0`，由 timestamps floor 至分鐘 |
| `cross_session_entry` | boolean |
| `entry_on_session_close` | boolean |
| `cross_session_exit` | boolean |

`match_id` exact projection：

```json
{
  "algorithm_contract_digest": "<manifest algorithm_contract_digest>",
  "entry_bar_digest": "<row entry_bar_digest>",
  "exit_bar_digest": "<row exit_bar_digest>",
  "signal_id": "<row signal_id>"
}
```

對此 object 呼叫 `digest()`。Source bar digest 對 immutable `bars.jsonl` 該列去除
最後 LF 後的 exact UTF-8 bytes 計算，不由 parsed float 重建。

### 5.4 Exact preflight/match-plan manifest

Manifest key set：

```text
schema_version = r5-match-plan-manifest-v2
control_contract_version = r5-signal-ledger-replay-v2
baseline_run_id
ledger_manifest_digest
ledger_rows_sha256
dataset_id
dataset_digest
dataset_manifest_digest
dataset_bars_sha256
dataset_binding_revision
algorithm_contract_digest
algorithm_implementation_digest
match_row_schema_version = r5-match-plan-row-v2
signal_count
matched_entry_count
matched_exit_count
missing_entry_count
missing_exit_count
duplicate_match_count
match_rows_sha256
match_signal_multiplicity_digest
match_plan_manifest_digest
```

`dataset_binding_revision` 與所有 counts 是 JSON integer；其餘是 string；所有 digest
欄位是 lowercase SHA-256。`match_signal_multiplicity_digest` 對 exact
`(sequence, signal_id, semantic_key)` parity tokens 的 grouped counts 計算，必須使用
8.1 的 exact `r5-layer-parity-projection-v2` schema；禁止另建省略 `sequence` 的
two-field projection。
`match_plan_manifest_digest = digest(manifest body excluding self)`；raw manifest bytes
必須等於 canonical JSON 加 LF。Request `preflight_digest` 就是此 digest，不另定義
含糊的 `match_plan_digest`。

Materializer 必須以 ordered immutable Dataset、bounded-memory per-symbol state 與
external merge／canonical sequence publication 實作。不得將 28,325,340 根 Kbar
一次載入 RAM，不得呼叫 FinMind、Shioaji 或其他 Provider。

## 6. Independent one-lot episode calculation

所有金額使用 `Decimal`，不得使用 binary float。沿用 baseline exact cost identity：

```text
shares = min_lot_shares
slippage = slippage_bps / 10000

entry_fill_price = raw_entry_open × (1 + slippage)
exit_fill_price  = raw_exit_close × (1 - slippage)

entry_gross = entry_fill_price × shares
exit_gross  = exit_fill_price × shares

entry_commission = entry_gross × commission_rate
exit_commission  = exit_gross × commission_rate
sell_tax         = exit_gross × sell_tax_rate

pre_slippage_price_pnl = (raw_exit_close - raw_entry_open) × shares
post_slippage_gross_pnl = (exit_fill_price - entry_fill_price) × shares
explicit_costs = entry_commission + exit_commission + sell_tax
net_pnl = post_slippage_gross_pnl - explicit_costs

pre_slippage_return = (raw_exit_close / raw_entry_open) - 1
net_return_on_raw_entry_notional = net_pnl / (raw_entry_open × shares)
```

公式、Decimal context、canonical formatting 或 rounding 任何變更都需要新
contract version。

### 6.1 Exact Modeled Entry row

Key set：

```text
schema_version = r5-modeled-entry-row-v2
sequence                           # integer, equals ledger sequence
modeled_entry_id                   # sha256, unique
episode_id                         # sha256
match_id                           # sha256
signal_id                          # sha256
semantic_key                       # sha256
symbol                             # non-empty string
filled_at                          # canonical timestamp
session_date                       # canonical date
source = NEXT_OBSERVED_SYMBOL_KBAR_OPEN
raw_price                          # positive Decimal string
fill_price                         # positive Decimal string
shares                             # integer == min_lot_shares
gross                              # Decimal string
commission                         # Decimal string >= 0
tax = 0                            # canonical Decimal string
total_cost                         # Decimal string == commission + tax
```

`episode_id` projection exact keys/values 是
`{"algorithm_contract_digest":"<result field>","signal_id":"<row field>"}`；
`modeled_entry_id` projection 是
`{"episode_id":"<derived episode_id>","side":"ENTRY"}`。兩者各自呼叫 `digest()`。

### 6.2 Exact Modeled Exit row

Key set 與 Entry row 相同，但 schema/source/ID 為：

```text
schema_version = r5-modeled-exit-row-v2
modeled_exit_id                    # replaces modeled_entry_id
source = FIRST_LATER_SYMBOL_SESSION_CLOSE
tax                               # Decimal string >= 0
```

不存在 `modeled_entry_id`；其餘欄位名稱與型別完全相同，不得另加欄位。
`modeled_exit_id` projection 是
`{"episode_id":"<derived episode_id>","side":"EXIT"}`，並呼叫 `digest()`。Exit `filled_at` 必須等於
match-plan exit timestamp；raw price/fill price/gross/commission/tax/total_cost 必須由
第 6 節公式重建。

### 6.3 Exact Replay Episode row

每列 key set：

```text
schema_version = r5-replay-episode-row-v2
sequence                           # integer, equals ledger sequence
episode_id                         # sha256, unique
signal_id                          # sha256
semantic_key                       # sha256
match_id                           # sha256
modeled_entry_id                   # sha256
modeled_exit_id                    # sha256
symbol                             # non-empty string
signal_at                          # canonical timestamp
signal_session_date                # canonical date
entry_at                           # canonical timestamp
entry_session_date                 # canonical date
exit_at                            # canonical timestamp
exit_session_date                  # canonical date
holding_minutes                    # integer >= 0
shares                             # integer == min_lot_shares
raw_entry_open                     # positive Decimal string
raw_exit_close                     # positive Decimal string
pre_slippage_price_pnl             # Decimal string
post_slippage_gross_pnl            # Decimal string
explicit_costs                     # Decimal string >= 0
net_pnl                            # Decimal string
pre_slippage_return                # Decimal string, scale <= 18
net_return_on_raw_entry_notional   # Decimal string, scale <= 18
outcome                            # WIN, LOSS, or TIE by net_pnl
```

Episode rows 依 sequence 排序。每個 input/intermediate amount 必須能由 exact match、
modeled Entry/Exit rows 和第 6 節公式重建；episode 自身不重複保存 commission/tax
明細，避免兩份 authority。

### 6.4 Exact result summary and manifest

Summary exact key set：

```text
schema_version = r5-replay-summary-v2
episode_count                      # integer
win_count                          # integer
loss_count                         # integer
tie_count                          # integer
sum_pre_slippage_price_pnl         # Decimal string
sum_post_slippage_gross_pnl        # Decimal string
sum_explicit_costs                 # Decimal string
sum_net_pnl                        # Decimal string
mean_pre_slippage_return           # Decimal string, scale <= 18
mean_net_return                    # Decimal string, scale <= 18
median_pre_slippage_return         # Decimal string, scale <= 18
median_net_return                  # Decimal string, scale <= 18
profit_factor_state                # FINITE, POSITIVE_INFINITY, or UNDEFINED
profit_factor                      # Decimal string scale <= 18, or JSON null
```

Profit Factor 使用 episode `net_pnl` 的 exact Decimal 值，固定算法如下：

- `gains = sum(net_pnl where net_pnl > 0)`；沒有正值時為 Decimal zero。
- `losses_abs = abs(sum(net_pnl where net_pnl < 0))`；沒有負值時為 Decimal zero。
- `losses_abs > 0` 時，state 是 `FINITE`。在 precision `38`、
  `ROUND_HALF_EVEN` context 中計算 `raw = gains / losses_abs`，再以
  `Decimal("0.000000000000000001")` 和 `ROUND_HALF_EVEN` quantize 至小數 18 位，
  最後經 4.2 的 Decimal string normalizer 輸出；因此 `gains = 0` 時唯一輸出
  `"0"`，trailing zeros 不保存。
- `losses_abs = 0` 且 `gains > 0` 時，state 是 `POSITIVE_INFINITY`，value 是 JSON
  `null`，不得執行除法。
- `losses_abs = 0` 且 `gains = 0` 時，state 是 `UNDEFINED`，value 是 JSON `null`。
- quotient 或 quantize 若產生 non-finite、precision overflow 或無法符合 scale
  `<= 18`，整份 replay fail closed，不得改用 float、提高 precision 或截斷。

`summary_digest = digest(summary)`。

Mean 是 exact Decimal sum 除以 episode_count，再 quantize 至 18 位。Median 先依
Decimal numeric value stable sort；奇數取中央值，偶數取兩個中央值算術平均，再
quantize 至 18 位。Episode count 為 0 時 result 不可建立，不使用 null fallback。

Result manifest exact key set：

```text
schema_version = r5-signal-ledger-replay-result-v2
control_contract_version = r5-signal-ledger-replay-v2
replay_id
baseline_run_id
registration_revision             # integer
ledger_manifest_digest
match_plan_manifest_digest
algorithm_contract_digest
algorithm_implementation_digest
cost_identity_digest
episode_row_schema_version = r5-replay-episode-row-v2
modeled_entry_row_schema_version = r5-modeled-entry-row-v2
modeled_exit_row_schema_version = r5-modeled-exit-row-v2
episode_count                      # integer
modeled_entry_count                # integer
modeled_exit_count                 # integer
episode_rows_sha256
modeled_entry_rows_sha256
modeled_exit_rows_sha256
episode_signal_multiplicity_digest
modeled_entry_signal_multiplicity_digest
modeled_exit_signal_multiplicity_digest
summary                            # exact r5-replay-summary-v2 object
summary_digest
result_projection_digest
result_manifest_digest
```

除明示 integer/summary 外，其餘欄位是 string；digest/SHA fields 為 lowercase
SHA-256。`cost_identity_digest` exact projection 是：

```json
{
  "commission_rate": "<canonical Decimal>",
  "min_lot_shares": 1000,
  "sell_tax_rate": "<canonical Decimal>",
  "slippage_bps": "<canonical Decimal>"
}
```

Shares 取 baseline exact integer，不把 literal `1000` 當通用常數。
`result_projection_digest` exact projection 是：

```json
{
  "episode_rows_sha256": "<manifest value>",
  "modeled_entry_rows_sha256": "<manifest value>",
  "modeled_exit_rows_sha256": "<manifest value>",
  "summary_digest": "<manifest value>"
}
```

各自對 exact object 呼叫 `digest()`。
`result_manifest_digest = digest(manifest body excluding self)`；raw bytes 必須等於
canonical JSON 加 LF。

## 7. Result semantics and publication boundary

### 7.1 Allowed evidence

通過 postflight 後可公開：

- episode count、win/loss/tie count。
- pre-slippage、post-slippage、explicit costs、net P&L 合計。
- exact summary 定義的 mean、median normalized episode returns。
- profit factor，以 episode net P&L gains/losses 計算。
- symbol、signal session、entry time、year 與 cross-session cuts；這些是從 accepted
  episode rows 重建的 report projection，不進 core result manifest identity。
- baseline-observed signal coverage limitation 與 exploratory Dataset limitations。

### 7.2 Prohibited metrics and labels

不得產生或顯示：

```text
portfolio equity curve
portfolio drawdown
CAGR
buying power
cash balance
concurrent position count as executable capacity
deployable Sharpe
```

若提供依 sequence 累加的 net P&L，只能標為
`arithmetic cumulative episode P&L (non-deployable)`，不得稱為 equity。

### 7.3 Fail-closed publication

Registration 未 `ACCEPTED` 前：

- API/list/detail/export/report 只回 status、identity 與 diagnostic counts。
- episode economics、aggregate metrics 與 cuts 一律回
  `409 R5_V2_POSTFLIGHT_NOT_ACCEPTED`。
- Compare、Qualification、Strategy lifecycle、R6 resolver 不得讀取 replay result。

## 8. Postflight acceptance contract

### 8.1 Layer parity projection

每一層都必須投影 exact parity token：

```json
{
  "semantic_key": "<sha256>",
  "sequence": 1,
  "signal_id": "<sha256>"
}
```

只有在 baseline `result_digest` 與 4.5 的 durable-stored-order decision projection
都已驗證後，才可將 verified authoritative decisions 依
`(event_at, symbol, decision_id)` 配置 derived parity sequence，再用與 ledger 相同公式
重建 signal_id/semantic_key。這個 derived sort 不得回寫、替代或重新解讀 authority
projection；raw authoritative rows 若被重排，必須先在 identity verification fail
closed。其他層直接取 exact row 欄位。

Layer multiplicity projection exact schema：

```json
{
  "schema_version": "r5-layer-parity-projection-v2",
  "tokens": {"<canonical parity token JSON>": 1}
}
```

`tokens` 是 canonical token string → JSON integer count，key 依 canonical JSON sort。
Layer multiplicity digest 是 projection digest。相鄰層必須同時驗證 `left EXCEPT ALL
right` 與 `right EXCEPT ALL left`；difference count 是所有正 multiplicity 差的總和，
不能使用會消除 duplicates 的普通 `EXCEPT`。

Ledger、Match Plan、Result manifest 與 Postflight 中每個命名為
`*_signal_multiplicity_digest` 的欄位，都必須對上述 exact three-field token 與
`r5-layer-parity-projection-v2` schema 計算；同名欄位不得代表 two-field token、不同
排序或不同 projection。另名的 `ledger_semantic_multiplicity_digest` 是 4.5 明定的
semantic-only inception diagnostic，不得拿來替代 layer parity。

必驗 boundaries：

```text
authoritative ENTRY decisions ↔ Signal Ledger
v2 inception order derivation ↔ Signal Ledger
Signal Ledger ↔ Match Plan
Match Plan ↔ Replay Episodes
Replay Episodes ↔ Modeled Entries
Replay Episodes ↔ Modeled Exits
```

### 8.2 Exact postflight conditions and diagnostics

Conditions object exact key set；所有 value 除 schema version 外都是 JSON boolean：

```text
schema_version = r5-replay-postflight-conditions-v2
baseline_identity_valid
v1_invalid_lineage_valid
order_inception_seal_valid
ledger_artifact_valid
match_plan_artifact_valid
result_artifact_valid
decision_ledger_bidirectional_parity
order_ledger_bidirectional_parity
ledger_match_bidirectional_parity
match_episode_bidirectional_parity
episode_modeled_entry_bidirectional_parity
episode_modeled_exit_bidirectional_parity
all_layer_counts_equal
frozen_signal_count_matches
no_missing_entry_or_exit
no_duplicate_rows
duplicate_match_count_zero
all_shares_exact_min_lot
all_formulas_rebuild
no_strategy_evaluation
no_provider_or_broker_calls
```

`frozen_signal_count_matches=true` 僅在 authoritative ENTRY decision count 為
128,802、v1-compatible multiplicity digest 等於 sealed v1 preflight、且 ledger count
同為 128,802 時成立；不能只比較其中任一 count。

Diagnostics object exact key set。所有 `*_count` 是 JSON integer；所有
`*_multiplicity_digest` 是 lowercase SHA-256：

```text
schema_version = r5-replay-postflight-diagnostics-v2
authoritative_entry_decision_count
order_derivation_count
ledger_signal_count
match_count
episode_count
modeled_entry_count
modeled_exit_count
missing_entry_count
missing_exit_count
duplicate_decision_count
duplicate_order_derivation_count
duplicate_ledger_count
duplicate_match_count
duplicate_episode_count
duplicate_modeled_entry_count
duplicate_modeled_exit_count
decision_minus_ledger_count
ledger_minus_decision_count
order_minus_ledger_count
ledger_minus_order_count
ledger_minus_match_count
match_minus_ledger_count
match_minus_episode_count
episode_minus_match_count
episode_minus_modeled_entry_count
modeled_entry_minus_episode_count
episode_minus_modeled_exit_count
modeled_exit_minus_episode_count
share_mismatch_count
formula_mismatch_count
strategy_evaluation_count
provider_call_count
broker_call_count
decision_signal_multiplicity_digest
order_signal_multiplicity_digest
ledger_signal_multiplicity_digest
match_signal_multiplicity_digest
episode_signal_multiplicity_digest
modeled_entry_signal_multiplicity_digest
modeled_exit_signal_multiplicity_digest
```

每個 `duplicate_*_count` 是該 layer primary ID grouped count 的
`sum(max(count - 1, 0))`；match primary ID 是 `match_id`。Exact row verifier另要求每層
sequence 與 signal_id unique；任一違規使 `no_duplicate_rows=false`。因此
`duplicate_match_count=0` 是明示 acceptance condition，不被總數相等取代。

Primary ID mapping 固定為：decision=`baseline_decision_id`、order derivation=
`baseline_order_id`、ledger=`signal_id`、match=`match_id`、episode=`episode_id`、
modeled entry=`modeled_entry_id`、modeled exit=`modeled_exit_id`。

### 8.3 Exact postflight object and verdict

Postflight exact key set：

```text
schema_version = r5-signal-ledger-replay-postflight-v2
control_contract_version = r5-signal-ledger-replay-v2
replay_id
baseline_run_id
registration_revision             # integer
baseline_result_digest
ledger_manifest_digest
match_plan_manifest_digest
result_manifest_digest
identity_validation_digest
conditions                        # exact 8.2 conditions object
diagnostics                       # exact 8.2 diagnostics object
verdict                           # ACCEPTED or INVALID
postflight_digest
```

`identity_validation_digest` exact projection 是：

```json
{
  "baseline_result_digest": "<postflight value>",
  "ledger_manifest_digest": "<postflight value>",
  "match_plan_manifest_digest": "<postflight value>",
  "registration_revision": 1,
  "replay_id": "<postflight value>",
  "result_manifest_digest": "<postflight value>"
}
```

Revision 取 actual integer field，不是通用 hardcode。對 exact object 呼叫 `digest()`。
`verdict=ACCEPTED` iff every condition boolean is true；否則 `INVALID`。
`postflight_digest = digest(body excluding self)`。

Server 在 result publication 前，從當前 result-digest-bound decisions、v2 inception
order seal、canonical artifacts 與 result chunks 重建全部 fields。任一失敗時不發布
economics；不得跳過 episode、替換 signal、改 shares/exit 或用新 key重跑相同 contract。

人工 SQL 必須在 `REPEATABLE READ READ ONLY` snapshot 中，以 `EXCEPT ALL`／grouped
multiplicity 重驗，失敗時非 0 exit。SQL 是第二層稽核，不能取代 server barrier。

## 9. Aggregate, ports, and dependency boundaries

Revision 2 建立獨立 bounded context：

```text
backtest/research_replay/
├── domain.py                 # SignalLedgerRow, MatchPlanRow, ReplayEpisode
├── ports.py                  # baseline, Dataset, artifact, repository ports
├── application.py            # preflight/create/execute/read use cases
├── artifact_store.py         # canonical local JSONL manifests
└── postgres_repository.py    # head/registration/operation/result adapter
```

Dependency rule：

```text
domain <- ports <- application <- adapters/composition
```

Domain 不 import PostgreSQL、FastAPI、Dashboard、Dataset path 或 Strategy Registry。

必要 ports：

- `BaselineSignalEvidencePort`：提供 result-digest-bound ENTRY decisions，並在 v2
  inception/read 時提供 current order projection做一對一 derivation verification。
- `OrderedDatasetPort`：提供 immutable ordered Kbar stream 與 manifest identity。
- `ReplayArtifactStorePort`：原子發布／重驗 canonical artifacts。
- `SignalReplayRepositoryPort`：durable idempotency、head、registration、status、chunks。
- `ExternalCallAuditPort`：證明 provider/broker call count 為零。

刻意**不提供** Strategy Evaluation Port、Order Adapter 或 Broker Port。

## 10. Persistence and mutation contract

Revision 2 不建立一般 `backtest_runs` row；它使用 `replay_id`，避免被既有 Run
compare／Qualification／worker 當成 portfolio backtest。

實作時新增下一個可用的 numbered PostgreSQL migration；候選名稱為：

```text
backtest/migrations/015_r5_signal_ledger_replays.sql
```

開始實作前須重新檢查 migration number，不能覆蓋 concurrent work。

至少需要：

```text
backtest.r5_signal_ledger_replay_heads
backtest.r5_signal_ledger_replay_registrations
backtest.r5_signal_ledger_replay_operations
backtest.r5_signal_ledger_replay_results
backtest.r5_signal_ledger_replay_result_chunks
```

Authoritative identity：

```text
head key = (baseline_run_id, control_contract_version)
registration key = (baseline_run_id, control_contract_version, revision)
unique replay = (baseline_run_id, control_contract_version, revision)
operation scope = (baseline_run_id, control_contract_version, idempotency_key)
```

`r5-signal-ledger-replay-v2` 初次建立使用 expected revision `0`，成功後封存
registration revision `1`。這裡的 registration revision 與 contract version v2 是
不同欄位。

Mutation request 只允許：

```json
{
  "request_schema_version": "r5-signal-ledger-replay-request-v2",
  "control_contract_version": "r5-signal-ledger-replay-v2",
  "preflight_digest": "<lowercase sha256>",
  "expected_registration_revision": 0,
  "actor_id": "local-researcher",
  "change_note": "..."
}
```

HTTP 使用 `Idempotency-Key` header；body 不接受 size/cash/cost/strategy/Dataset
override。Unknown field `422`。

Repository transaction：

1. 依 operation scope/key 查 replay；同 key 不同 digest conflict。
2. 鎖定 `(baseline_run_id, contract_version)` head。
3. 在同一 transaction snapshot 內鎖定並重驗 baseline、result-digest-bound ENTRY
   decisions、current decision↔order derivation、v1 invalid registration/postflight、
   Dataset 與 preflight；將重算的 v2 inception order rows SHA/digest 保存到
   registration，不接受 artifact 自行申報值。
4. 相同 target/digest 的不同 key 回傳 authoritative replay，不增加 revision。
5. 不同 digest 或 stale expected revision fail closed。
6. registration、operation result、replay identity 與 head revision 同 transaction。
7. Result publication、postflight、result manifest/chunks 與 terminal status 同一
   PostgreSQL transaction；artifact 在 transaction 前完成 immutable atomic publish，
   DB 只引用已驗證 digest。

Statuses：

```text
SEALED → RUNNING → POSTFLIGHT → ACCEPTED
                         └────→ INVALID
RUNNING → CANCELLING → CANCELLED
RUNNING → FAILED
```

Terminal revision 不可 retry/clone。Response-loss replay 回原 operation result；失敗
後修改演算法需要新 contract version與獨立 Review。

## 11. API and UI scope

候選 API：

```text
POST /api/research/r5/baselines/{baseline_run_id}/signal-ledger-replays
GET  /api/research/r5/signal-ledger-replays/{replay_id}
GET  /api/research/r5/signal-ledger-replays/{replay_id}/evidence
```

第一個 implementation slice 可以只提供 CLI/application use case，不需要 Dashboard
入口。若加入 Web，必須沿用 loopback Host、full Origin、CSRF、strict schema、actor
audit 與 durable idempotency boundary。

UI 必須醒目顯示：

```text
Independent one-lot research replay
Not a portfolio backtest
Not buying-power feasible evidence
Dataset research_eligible=false
Local Paper / Broker prohibited
```

## 12. Acceptance and adversarial test matrix

### 12.1 Pure domain

- Golden one-lot entry/exit/cost calculation。
- Signal at ordinary intraday bar → same-session close。
- Signal at session final bar → next-session open entry → later session close exit。
- Entry Kbar itself is session close → never exit on same Kbar。
- Cross-session next-observed entry parity。
- Missing entry, missing exit, zero/negative prices, invalid Decimal fail closed。
- Two overlapping same-symbol signals both produce independent episodes。
- Reordering authoritative durable ENTRY decisions changes the stored-order projection／
  baseline result identity and 必須 fail closed；authority reader 不得先排序來掩蓋
  durable-order drift。
- 只重排尚未發布的 derived/external-sort chunks，在依 frozen canonical sequence
  完成 publication 後，必須重建相同 ledger、match-plan 與 result digests。
- Any current-equity/cash/position field is rejected by exact schema。
- ENTRY decision horizon/policy/member drift changes ledger identity；order status/reason
  does not define signal identity。
- Existing result digest tamper prevents decision authority construction。

### 12.2 Artifact integrity and boundedness

- Every ledger/order-derivation/match/episode/modeled-entry/modeled-exit/manifest/postflight
  object rejects missing or unknown fields。
- Blank line、duplicate sequence、non-NFC string、timestamp alias、Decimal exponent/
  trailing-zero/binary number rejected。
- Locator/root change does not change identity；payload byte change does。
- Interrupted publication leaves no partial final pair。
- Multi-year stream memory bounded by symbol/current matches and external-sort chunks。
- Clean-root rebuild produces identical ledger、match-plan、result digests。
- Same total count but one substituted `(sequence, signal_id, semantic_key)` fails at each
  decision↔ledger、order↔ledger、ledger↔match、match↔episode、episode↔entry and
  episode↔exit boundary。
- Duplicate `match_id` with recomputed local artifact digests still yields
  `duplicate_match_count > 0` and postflight INVALID。

### 12.3 Application and PostgreSQL

- Same-key/same-digest replay；same-key/different-digest conflict。
- Different-key concurrent creation yields one registration/replay。
- Stale revision conflict；same-target no-op does not increment revision。
- v1 terminal invalid evidence missing/tampered blocks v2 creation。
- Baseline decision/result/config/Dataset drift blocks creation/execution/read。
- At v2 inception, missing/extra/duplicate order or any decision↔order field mismatch blocks
  sealing；after inception, order-derivation drift blocks execute/read。
- Result/episode/postflight chunk tamper blocks economics exposure。
- Cancel/status CAS cannot be overwritten by worker。
- Failure/cancel flushes progress but never publishes partial economics。
- Compare/export/Qualification/R6 cannot resolve replay as normal Run。

### 12.4 Formal full-Dataset Gate

在 28,325,340 Kbar Dataset 上必須證明：

```text
ledger signals = 128802
matched entries = 128802
matched exits = 128802
episodes = 128802
modeled entries = 128802
modeled exits = 128802
all six bidirectional parity boundaries = empty
missing/duplicate including duplicate_match_count = 0
strategy evaluations = 0
provider/broker calls = 0
all canonical digests rebuild
formal SQL exits 0
```

正式數值是 Gate evidence，不得在實作測試中硬編成可跳過 identity 驗證的常數。

Cluster bootstrap、confidence interval 與 hypothesis test 不屬於 v2 contract；若未來
需要，必須以新的 protocol identity 和 Review 加入，不能由 Web request 動態指定。

## 13. Decision matrix after accepted replay

以 normalized episode return 為 primary、one-lot TWD P&L 為 secondary：

| Accepted v2 evidence | Decision |
|---|---|
| Mean pre-slippage return `<= 0` | `above_vwap_entry` research reject；不再用同 Dataset 調參 |
| Pre-slippage `> 0`、mean net return `<= 0` | 只允許 cost／holding-time 研究；不得 promotion |
| Mean net return `> 0` | 只列 exploratory candidate；未做獨立統計推論，且等待 research-eligible Dataset |
| Postflight 任一條件失敗 | Replay INVALID；不得解讀績效 |

任何 outcome 都不會自動改 Strategy lifecycle、啟動 Local Paper 或授權 broker。

## 14. R6 impact

既有 R6 v1 contract 依賴「accepted R5 Backtest Run＋cash-admission allocation」作為
canonical Baseline。Revision 1 已證明該前提不成立；revision 2 又刻意不是 portfolio
Run。因此：

```text
R6 v1 execution: SUPERSEDED / NOT AUTHORIZED
R6 revision 2 design: BLOCKED ON ACCEPTED R5 v2 EVIDENCE
```

R5 v2 接受後，只能另行決定 R6 要：

1. 對每個原子策略建立相同 independent one-lot signal-ledger replay；或
2. 重新設計真正可執行的 portfolio allocation benchmark。

不得把兩種研究問題混在同一 family，也不得直接把 `replay_id` 填入
`baseline_run_id`。

## 15. Implementation slices and Gates

| Gate | Scope | Exit condition | Status |
|---|---|---|---|
| G0 | Contract design | Independent Review closes semantics/identity/persistence/test blockers | PASSED / CONTRACT FROZEN |
| G1 | Pure domain＋artifact | Golden math, matching, canonical bytes, bounded-memory tests pass | PASSED / FORMAL GATE APPROVED |
| G2 | PostgreSQL＋application | Idempotency, CAS, tamper, redaction, security tests pass | PASSED / FORMAL GATE APPROVED |
| G3 | Full preflight | 28.3M bars produce 128,802 complete matches, zero external calls | PASSED / FORMAL GATE APPROVED |
| G4 | Formal replay | 128,802 accepted episodes and formal SQL pass | NOT AUTHORIZED |
| G5 | Research disposition | Metrics reviewed; HOLD/reject/candidate recorded without lifecycle mutation | NOT AUTHORIZED |

每個 Gate 需要獨立明確授權。G0 通過不代表可以實作，G1-G3 通過也不代表可以
執行正式 replay。

## 16. Proposed file map

Implementation Review 通過後的候選修改範圍：

```text
backtest/research_replay/__init__.py
backtest/research_replay/domain.py
backtest/research_replay/ports.py
backtest/research_replay/application.py
backtest/research_replay/artifact_store.py
backtest/research_replay/dataset_adapter.py
backtest/research_replay/postgres_repository.py
backtest/migrations/<next>_r5_signal_ledger_replays.sql
scripts/preflight_vwap_signal_ledger_replay.py
scripts/audit_vwap_signal_ledger_replay.py
tests/test_signal_ledger_replay_domain.py
tests/test_signal_ledger_replay_artifacts.py
tests/test_signal_ledger_replay_application.py
tests/test_signal_ledger_replay_postgres.py
tests/test_signal_ledger_replay_cli.py
architecture/vwap_failure_attribution_research_gate.md
README.md
```

`backtest/engine.py`、Atomic Strategy implementations、Local Paper、market-data provider、
Shioaji、broker account 與 real-money modules 不在 revision-2 implementation scope。

## 17. Current disposition

```text
R5 revision 1: COMPLETE / INVALID / SEALED
R5 revision 2 design: APPROVED / G0 PASSED / CONTRACT FROZEN
R5 revision 2 G1 implementation: APPROVED / FORMAL GATE PASSED
R5 revision 2 G2: APPROVED / FORMAL GATE PASSED / PROGRESS 50%
R5 revision 2 G3: APPROVED / FORMAL GATE PASSED / PROGRESS 66.7%
R5 revision 2 G4-G5: NOT AUTHORIZED
R5 revision 2 execution: NOT AUTHORIZED
R6: BLOCKED / NOT AUTHORIZED
Local Paper / Broker / Real-money: PROHIBITED
```
