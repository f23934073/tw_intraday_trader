# VWAP 失敗歸因與下一個研究 Gate

## 1. 結論

`above_vwap_entry` Version `c2d5ca63-a871-482b-bc70-b3f81a48f5ba` 目前維持：

```text
Research disposition: HOLD / NOT ELIGIBLE
Local Paper: PROHIBITED
Broker / Real-money: PROHIBITED
```

原始 Run 已證明「目前這組 ENTRY、EOD EXIT、成本與資金配置」不可使用，
但尚不能把全部虧損單獨歸因於 VWAP ENTRY。原因是同日大量訊號受到
`(timestamp, symbol)` 排序與剩餘現金 admission 的強烈抽樣偏差。

原 cash-admission-neutral revision 1 已正式執行，但因 current-equity sizing 仍產生
10,520 筆拒單，且重新跑 portfolio engine 少了 30 筆 ENTRY signal，最終以
`INVALID / ACCEPTANCE REJECTED` 封存。該結果不可解讀為策略績效，也不可 retry、
clone 或用較大資金重跑。

後續改由 [R5 Contract Revision 2 — VWAP Signal-Ledger One-Lot Replay](./vwap_signal_ledger_replay_v2_implementation_plan.md)
重新設計。Revision 2 凍結 baseline signal ledger，每筆獨立一張 replay，不再使用
current equity、共享現金、portfolio position 或策略重新評估。本文件第 5、6 節保留
revision 1／R6 v1 的歷史契約與稽核脈絡，不再構成執行授權。

## 2. 基準證據

基準 Run：`run-91ad87981676414da87b928398fa43c9`

| 指標 | 結果 |
|---|---:|
| Dataset Kbar | 28,325,340 |
| 交易日 | 727 |
| ENTRY signals | 128,802 |
| ENTRY filled | 6,321 |
| ENTRY cash rejected | 122,481 |
| Fill rate | 4.91% |
| 平均 signals / day | 177.17 |
| 平均 filled / day | 8.69 |
| Pre-slippage price P&L | -1,365,500.00 |
| Slippage drag | -1,242,058.15 |
| Commission + tax | -7,262,130.84 |
| Net P&L | -9,869,688.99 |
| 平均單筆 net return | -0.8095% |
| 獲利交易日比例 | 15.65% |

即使移除 slippage、commission 與 tax，已成交樣本的 price path 仍為負。
成本是主要放大器，但不是唯一失敗原因。

## 3. 已凍結的歸因

### 3.1 高信心

1. **目前訊號過度普遍。** 每日平均 177.17 個 ENTRY signal，接近 Dataset
   的 182 檔 observed universe；它不是高選擇性的候選條件。
2. **成交樣本有明顯排序偏差。** 同日 signal ranks 1-10 的 fill rate 為
   39.37%，ranks 101+ 只剩 0.73%。
3. **已成交樣本在 friction 前已無正 edge。** Pre-slippage price P&L 為負，
   且 2023-2026 的平均單筆 net return 每年都為負。
4. **交易 friction 讓弱訊號快速破產。** Slippage、commission 與 tax 合計
   造成約 8.50M drag，占 net loss 約 86.16%。
5. **本 Run 主要是開盤後進場、持有到收盤。** 81.44% trades 於 09:03
   成交，holding-time median 為 267 分鐘。

### 3.2 尚不可分離

- ENTRY 與 `end_of_day_exit_v1` 的獨立貢獻：目前只有組合結果，沒有相同 ENTRY
  搭配不同 EXIT 的 controlled comparison。
- MFE／MAE 與固定持有時間反事實：需要將 6,321 trades 與 immutable 5.5 GiB
  Kbar payload 做 path join，不能由 entry/exit payload 猜測。
- 正式研究效力：Dataset 仍是 CURRENT_SNAPSHOT、partial universe、raw unadjusted
  price、current metadata 與 derived VWAP amount proxy。

## 4. 不採用的下一步

### 4.1 不直接改成 VWAP cross-up

目前 engine 從 09:01 開始、每檔每天只接受第一次 trigger；第一根 close 與
session VWAP 相等，因此第一次 strict `close > VWAP` 通常本身就是第一次
cross-up。若直接新增 cross-up file，可能得到行為相同的策略，不能構成有效
challenger。

### 4.2 不用本 Run 做參數搜尋

五個 VWAP distance quintiles 全部虧損，晚一點的 entry-minute buckets 也沒有
呈現穩定正向證據。用相同資料調 `minimum_distance_bps` 或時間窗，再用同一份
結果宣稱改善，會造成研究洩漏。

### 4.3 不先組合策略

尚未各自量測的原子策略不可直接用 `ALL`／`ANY` 組合；否則無法辨認績效來自
哪一個策略，也會快速消耗 multiple-testing budget。

## 5. Historical Gate R5 revision 1 — Cash-admission-neutral control

> **SUPERSEDED / SEALED INVALID**：本節是 revision 1 的已執行契約。Control Run
> `run-4de8112d3a154148a1af93fc86a26f83` 已 fail closed；不得依本節建立第二個
> authoritative control。Revision 2 以獨立文件為準。

R5 只回答一個問題：排除「剩餘現金不足」造成的 signal admission 偏差後，
同一組 VWAP ENTRY／EOD EXIT 是否仍無正 edge。現行 engine 會用每筆成交前的
`current_equity` 動態計算 shares，因此 R5 不宣稱 share allocation、order notional
或 P&L weighting 對 symbol order 完全中立；`allocation-neutral` 一詞不再使用。

### 5.1 唯一允許改變的變數

只改 execution capital allocation，其他 identity 全部與基準一致：

- 相同 Dataset ID/digest/binding revision。
- 相同 exact Strategy Set Version。
- 相同 `above_vwap_entry` Version 與 parameters。
- 相同 `end_of_day_exit_v1`。
- 相同 engine、5 bps slippage、0.1425% commission、0.3% sell tax、1,000 股 lot。
- 不修改 Strategy Version，不發布新策略，不啟動 Local Paper。

### 5.2 專用建立與 lineage 契約

R5 不得使用一般 `baseline_run_id` Challenger 路徑，因為現行 comparability
契約正確地要求 Challenger 與 Baseline 使用相同 `starting_cash` 與
`position_fraction`。也不得用一般 Clone 的隨機 `experiment_id` 冒充
authoritative experiment family。

實作前須提供專用 mutation：

```text
POST /api/backtests/runs/{baseline_run_id}/cash-admission-controls
```

Request 至少包含：

```json
{
  "request_schema_version": "cash-admission-control-request-v1",
  "control_contract_version": "cash-admission-control-v1",
  "preflight_digest": "<lowercase sha256>",
  "expected_registration_revision": 0,
  "idempotency_key": "...",
  "actor_id": "local-researcher",
  "change_note": "..."
}
```

Request **不得**接受 caller 提供的 `starting_cash`、`position_fraction`、buffer
ratio 或 rounding mode。這些值全部由 server 依 5.3 的 frozen algorithm 從指定
preflight 推導；出現未知欄位一律 `422`。同一個 baseline Run 與
`cash-admission-control-v1` control contract 只能有一個 authoritative registration
head；request schema version 不參與這個研究身分。

PostgreSQL 至少需要下列 durable identity：

```text
head key = (baseline_run_id, contract_version)
registration key = (baseline_run_id, contract_version, revision)
unique authoritative Run = (baseline_run_id, contract_version, revision)
```

初次建立使用 `expected_registration_revision=0`，成功後封存 revision `1`。
同一 idempotency key＋request digest 回放原 response；相同 baseline／contract 即使
使用不同 key，也只能回傳已封存的 registration／control Run，不得建立第二個
配置或第二個 Run。若 preflight digest 不同，回
`R5_CONTROL_ALREADY_SEALED`，不得以新 key 覆蓋。

已封存 revision 的 preflight、`C/f`、Run 與 postflight 結果都不可修改。若
postflight 失敗，該 revision 永久標記 `INVALID`，不得自動改資金或重跑。只有新的
contract revision／algorithm identity，連同 actor、change note、前次 failure
evidence 與獨立 Review approval event，才能用 head CAS 建立下一個 revision；這不是
一般 retry，也不能由 Web 使用者自行開啟。

Repository transaction 必須：

1. 先依 operation scope＋idempotency key 回放原結果；不同 digest 回 conflict。
2. 對 `(baseline_run_id, contract_version)` 取得 advisory／head row lock，先檢查
   是否已有 sealed registration；不同 idempotency key 不得繞過唯一性。
3. 鎖定並驗證 baseline Run 為 `COMPLETED`，且 Run/config/Dataset/result identity
   未漂移。
4. 驗證 preflight canonical body、digest、baseline／Dataset／Strategy／cost identity，
   並依 frozen algorithm 重算 `C/f`；request 不得帶入或覆寫推導結果。
5. 從 baseline config 重建 control config，只由 server 覆寫 `starting_cash` 與
   `position_fraction`。
6. 保留 baseline 的 exact Dataset binding snapshot，不依賴當下 default binding head。
7. 設定 `parent_run_id=baseline_run_id`；`baseline_run_id`、`experiment_id` 與
   `research_baseline_digest` 保持 `null`，避免誤登記為 Qualification Challenger。
8. 將 registration、operation result、完整 `research_control_snapshot`、Run 與
   head revision 在同一 PostgreSQL transaction 建立；任何 unique/CAS conflict
   都必須重讀 authoritative registration 或 fail closed。

`research_control_snapshot` 至少保存 baseline Run/config/result digests、preflight
body/digest、唯一允許的 config delta、Dataset binding、Strategy Set/Version、
Feature/amount/engine/cost identity、actor、change note 與建立時間。後續 R6 以
已完成的 R5 Run 作為 canonical Baseline 時，所有 Challenger 必須逐字繼承這份
snapshot；comparability 不得忽略它。

### 5.3 Canonical preflight

Preflight 是一個獨立、canonical、可重建的 evidence artifact。PostgreSQL 提供
baseline ENTRY order keys；streaming reader 再從 immutable `bars.jsonl` 找到每個
order 的 exact next-bar open。不得重新呼叫 FinMind 或其他 Provider。

`cash-admission-control-v1` 必須逐字遵循 frozen engine 的 execution 語意：普通
`INTRADAY_NEXT_BAR`／未明示 horizon 的 pending order 使用該 symbol 下一個 observed
Kbar，即使它位於下一個 session；不得額外加入 same-session filter。只有
`DAILY_NEXT_BAR` 使用獨立的 session-date admission 規則，而 R5 v1 不接受該 horizon。

Preflight 計算：

- `S_max`：單日最多 distinct ENTRY signals。
- `P_max`：所有 eligible next-bar open 的最高價。
- `L`：minimum lot shares。
- `m_entry`：exact entry cost multiplier：
  `(1 + slippage_bps / 10000) × (1 + commission_rate)`。
- `candidate_order_count`、`matched_next_bar_count`、`missing_next_bar_count`。

候選 `starting_cash=C` 與 `position_fraction=f` 至少須滿足：

```text
C × f >= P_max × L
S_max × C × f × m_entry <= C × 0.80
```

`cash-admission-control-v1` 的推導是 server-owned deterministic contract：

```text
buffer_ratio = 0.80                         # frozen constant
f_raw = buffer_ratio / (S_max * m_entry)
f = floor(f_raw, 12 decimal places)
C_raw = (P_max * L) / f
C = ceil(C_raw to the next whole TWD)
```

所有運算使用 Decimal，不得使用 binary floating point；`S_max > 0`、`P_max > 0`、
`L > 0`、`m_entry > 0`、`f > 0` 才能建立 registration。Server 必須把 raw value、
rounding mode、scale 與重算結果寫入 preflight。相同 baseline identity 與相同
contract version 必須得到完全相同的 `C/f` 與 config digest，沒有可供操作者挑選
結果的自由參數。

這是候選 config 的安全篩選，不是零拒單證明：engine 依 `current_equity` sizing，
盤中 mark-to-market 仍可能改變後續 shares。唯一 authoritative acceptance 是完成
Run 後的 server postflight。若 postflight 任一條件不成立，整個 Run 標記
`INVALID_CASH_ADMISSION_CONTROL`，不得查看或引用績效，也不得自動改參數重跑；
必須回到 R5 design review，核准新的 contract revision 後才能建立新 preflight。

Canonical preflight body 至少包含：

- contract／algorithm implementation identity。
- baseline Run/config/result digests。
- Dataset ID/manifest/bars SHA-256/binding revision。
- exact Strategy Set/Version/parameters/implementation digests。
- engine、lot、slippage、commission、tax identity。
- `S_max`、`P_max`、所有 order/next-bar coverage counts。
- `C`、`f`、`m_entry`、buffer ratio 與公式驗證結果。
- artifact digest；locator path 只能進 operation audit，不進 identity。

### 5.4 Control acceptance

- Baseline 與 control 各恰好一筆，且 baseline 已是 `COMPLETED`；control 只有在
  server postflight 通過後才可由 `CONTROL_POSTFLIGHT` 轉成 `COMPLETED`。
- Preflight `missing_next_bar_count = 0`，且
  `candidate_order_count = matched_next_bar_count`。
- Control 必須滿足
  `ENTRY orders = ENTRY fills = candidate_order_count`；每筆 ENTRY status 都是
  `FILLED`，所有 rejection／blocked／cancelled／unresolved reason 的總數為 0，
  不可依賴特定中文顯示文字。
- ENTRY signal keys 必須與 baseline 完全相同，並以 multiplicity-aware
  `EXCEPT ALL`（或 canonical grouped counts）做雙向驗證；兩邊差異都必須為 0。
- Result/config/Dataset/amount/strategy digests 必須通過既有完整驗證。
- `research_control_snapshot` 與 preflight digests 必須可從 durable Run 重建。
- 保存 pre-slippage price P&L、slippage、fees/tax、net P&L、PF、drawdown、
  year/session/symbol cuts 與 admission-rank fill rate。
- 零 FinMind、Shioaji、CA、account、trade-subscription 或 broker 呼叫。

Worker 必須在 result publication 前執行 postflight：先完成 engine result 與所有
order/fill projections，在同一個 PostgreSQL transaction／一致的 immutable result
projection 上重算上述條件，保存 canonical `research_control_postflight_snapshot`、
digest 與 registration status，再決定 terminal status。通過時才可同 transaction
發布完整 result 並標記 `COMPLETED/ACCEPTED`；失敗時只保存 diagnostic counts 與
digest，標記 `INVALID_CASH_ADMISSION_CONTROL`，完整績效 payload 不得發布。

在 registration 尚未 `ACCEPTED` 前，Run list/detail、comparison、export、report、
Qualification 與 R6 resolver 都不得回傳或使用 P&L、PF、drawdown 等績效欄位；
應回 `409 R5_CONTROL_POSTFLIGHT_NOT_ACCEPTED`。Restart/replay 必須先讀 durable
postflight operation，不能重複發布或越過這個狀態。人工 SQL 只是第二層 Reviewer
evidence，不是第一個阻擋績效曝光的 Gate。

`r5_control_acceptance_queries.sql` 必須以 `REPEATABLE READ READ ONLY` 執行，
逐項輸出上述 counts，並在任一條件失敗時以非 0 exit code 結束；不得只產生報表後
成功退出。

### 5.5 Decision matrix

| Control 結果 | 決策 |
|---|---|
| Pre-slippage P&L <= 0 | `above_vwap_entry` 維持 research reject；不再調參 |
| Pre-slippage > 0、net <= 0 | 只允許獨立 cost/holding-time 研究，不可 promotion |
| Net > 0 但 Dataset 不合格 | 只列 exploratory candidate，等待 research-eligible Dataset |
| Cash rejection > 0 | Control invalid，先修正 preflight，不解讀策略 |

任何結果都不會自動變更 lifecycle 或啟動 Local Paper。

## 6. Gate R6 — Atomic ENTRY benchmark matrix

> **SUPERSEDED / NOT AUTHORIZED**：本節的 R6 v1 假設存在 accepted R5 portfolio
> Run 與可繼承的 cash-admission allocation。R5 revision 1 已 invalid，而 revision 2
> 刻意不是 portfolio Run，因此本節只保留歷史設計。R6 必須等 R5 v2 accepted 後
> 另行 Review；不得把 `replay_id` 當成 `baseline_run_id`。

R5 完成後，才可用同一套 cash-admission-neutral execution policy，分別建立下列
單一 ENTRY Strategy Set：

1. 突破盤中前高
2. 滾動報酬突破
3. 成交量加速
4. 開盤區間突破 ORB
5. EMA 黃金交叉
6. RSI 超賣
7. Bollinger 下軌回歸

每個 Run 只改一個 exact ENTRY Version；EOD EXIT、Dataset、cost、engine、
cash-admission allocation 與 R5 `research_control_snapshot` 全部固定。

### 6.1 Server-owned family budget

現行 Qualification contract 固定使用：

```text
planned_attempts = 20
family alpha = 0.05
adjustment = BONFERRONI
adjusted alpha = 0.0025
```

R6 不修改這份已核准的 server policy，也不宣稱 family budget 為 7。七個 atomic
候選占 family attempt slots 1–7；slots 8–20 保留但不得在新的 sealed matrix
registration／Review 前使用。

### 6.2 Sealed matrix registration

R5 完成且 identity 驗證通過後、任何 R6 Challenger Run 建立前，必須以同一
PostgreSQL transaction 建立或驗證 head sequence `0` 的 authoritative family，
並封存 matrix registration。至少需要：

```text
matrix_id
contract_version = atomic-entry-benchmark-matrix-v1
family_id / research_baseline_digest / canonical R5 baseline_run_id
family_planned_attempts = 20
registered_slots = 7
execution/comparability/research_control_snapshot digests
actor / change_note / sealed_at
registration_json / registration_digest
```

每個 slot 必須預先保存：

```text
slot_sequence = 1..7
hypothesis_id
exact Strategy Set Version ID/digest
exact ENTRY Strategy Version ID
configuration/implementation/Feature Request digests
expected family attempt_sequence
status = REGISTERED
```

Registration sealed 後不可修改或刪除。建立 Challenger 時 request 必須帶
`matrix_id`、`registration_digest` 與 `slot_sequence`；repository 在 family head lock
內驗證 exact Run snapshot，並以 compare-and-consume 將 slot 轉成 `RUN_CREATED`。
未註冊、重複消耗、順序錯誤、strategy digest 漂移或 family head 漂移均 fail
closed。`hypothesis_id` 在 Run 建立時即進 attempt ledger，不可延後到
Qualification 才由使用者填入。

沒有單一 atomic candidate 通過前，不建立策略組合。

### 6.3 Historical implementation map

R5/R6 execution 前至少修改：

- `backtest/domain.py`：加入 digested `research_control_snapshot` 與 matrix slot
  evidence、registration/postflight state 與 invalid terminal status。
- `backtest/application.py`：專用 R5 control use case、deterministic `C/f` resolver、
  result publication 前 postflight；R6 request resolver 必須 carry forward 已接受的
  R5 control identity。
- `backtest/postgres_repository.py`：R5 head lock、registration revision、唯一
  authoritative Run、replay/transaction 與 postflight publication；R6 family-head
  lock、sealed registration 與 slot compare-and-consume。
- `dashboard/server.py`：strict R5 control request 與 R6 matrix/slot request。
- `dashboard/static/js/workspaces/backtest.js`：明確分離 sensitivity control 與
  Qualification Challenger；未 sealed 不可建立 R6 Run。
- `scripts/preflight_vwap_cash_admission_control.py`：read-only PostgreSQL＋immutable
  Dataset streaming preflight，輸出 canonical JSON/SHA-256。
- `backtest/migrations/<next_available>_research_control_matrix.sql`：R5 head、sealed
  registration、operation/postflight evidence，以及 R6 matrix／slot；實作時避開
  shared worktree 已存在的 migration 編號。
- `tests/`：idempotency、tamper、binding drift、unapproved delta、current-equity
  rejection、不同 key 不得建立第二個 control、revision CAS、postflight 前績效
  redaction、missing next bar、所有非 FILLED reason、multiplicity parity、family
  budget 20、sealed slot order、concurrent consume。

本次契約修正不授權建立 migration、產品 endpoint、Replay 或任何 Run。

本 Dataset 只能做 exploratory screening。正式 promotion 仍須使用
`research_eligible=true`、date-effective、adjusted-price、point-in-time metadata
Dataset，重新通過 Qualification Gate。

## 7. Gate 狀態

```text
Failure Attribution: COMPLETE
Gate R5 revision 1: COMPLETE / INVALID / SEALED
Gate R5 revision 2 design: APPROVED / G0 PASSED / CONTRACT FROZEN
Gate R5 revision 2 implementation/execution: NOT AUTHORIZED
Gate R6 v1: SUPERSEDED / NOT AUTHORIZED
Gate R6 revision 2: BLOCKED ON ACCEPTED R5 V2 / NOT AUTHORIZED
Local Paper / Broker / Real-money: PROHIBITED
```
