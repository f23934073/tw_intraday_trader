# FinMind Sponsor 歷史資料接軌回測 Implementation Plan

## 1. 結論與完成定義

本計畫只完成以下橋接：

```text
data/finmind_sponsor/history.sqlite3
→ 一致性 semantic snapshot
→ immutable Backtest Dataset
→ PostgreSQL ATOMIC_BACKTEST_DEFAULT binding
→ Web Atomic Backtest
```

完成時，Web 不需要使用者準備或選擇 Dataset；但伺服器必須能指出
實際綁定的 Dataset ID、manifest digest、日期、股票數、Kbar 數、資料限制，
並以該精確 identity 建立 immutable Run。

本計畫不把正在寫入的 SQLite 直接交給 Backtest Engine，也不修改
FinMind downloader 的下載契約。

目前 disposition：`G0 APPROVED / CONTRACT FROZEN`、
`G1 APPROVED / GATE PASSED`、`G2 APPROVED / GATE PASSED`。本次實作只
包含小型 saved-plan materialization、deterministic immutable Dataset replay
與 bounded-memory/conflict tests；不執行正式完整 snapshot，不修改
PostgreSQL、Web、Local Paper、broker，亦不提前進入 G3～G5。

## 2. 範圍與非目標

### 2.1 範圍

- 從仍在持續下載的 WAL SQLite 建立一致性 online backup。
- 跨多個 FinMind jobs 建立一份完整、可稽核的 semantic snapshot。
- 只納入 snapshot 當下完整的股票；partial／INVALID 不進 Dataset。
- 沿用既有 raw/canonical digest 驗證與 HistoricalBar 正規化。
- bounded-memory 寫入 timestamp/symbol ordered immutable Dataset。
- PostgreSQL-only immutable registration 與 default binding。
- Web Atomic Backtest 讀取實際 default binding。
- 大型 Run 的 progress write 與 cancellation read 節流。

### 2.2 非目標

- 不宣稱 date-effective full-market universe。
- 不宣稱 survivorship-free 或 corporate-action adjusted。
- 不讓探索 Dataset 通過正式 Qualification。
- 不新增 browser Dataset selector 或資料下載按鈕。
- 不加入 Local Paper、Shioaji 委託、CA、trade subscription 或真實交易。
- 不合併 Strategy Set archive/revision 的 concurrent work。

## 3. 現況與主要缺口

| 邊界 | 已有能力 | 缺口 |
|---|---|---|
| Acquisition | symbol-day checkpoint、WAL、raw/canonical digest、offline audit | 沒有 consistent snapshot reader／materializer |
| Dataset Catalog | manifest、checksum、atomic directory、bounded ordered replay | 大型匯入缺少 timestamp-major bounded writer 與來源 lineage |
| PostgreSQL | Dataset manifest、immutable Run | registration 可 upsert；沒有 default binding |
| Application | replay 沿用原 Dataset、Challenger 沿用 Baseline | standalone Run 仍猜 READY Dataset |
| Web | 已移除 Dataset selector | 顯示的 preferred Dataset 仍是前端自行猜測 |
| Run control | 每 128 bars 檢查取消並回報 progress | 大型 Run 會產生大量 PostgreSQL SELECT／UPDATE |

歷史資料仍持續增加。Reviewer 依序觀測 159、160、161 檔。
任何股票數、partition 數與 Kbar 數都只能是 snapshot evidence，不能成為
寫死的完成門檻。

## 4. 凍結契約

### 4.1 Consistent source snapshot

1. 以 SQLite online backup 取得短時間、一致性的來源副本。
2. materializer 只讀副本；長時間封存不得 pin live WAL read transaction。
3. 所有 counts、選擇、digest 與輸出都來自同一副本。
4. source 在備份完成後新增的 partitions 只會進下一版 Dataset。

### 4.2 Job 相容性

可合併 jobs 必須具備相同：

- `source`、`source_version`；
- requested start/end；
- `trading_dates_json` canonical digest；
- calendar raw digest；
- volume unit contract。

不相容 job 不可默默略過後仍聲稱完整；dry-run 必須列出排除原因。

### 4.3 完整股票

對每個 symbol，materializer 必須驗證：

- exact session-date set 等於凍結 calendar；
- 每個 identity 狀態為 `READY` 或 `EMPTY`；
- 沒有 `INVALID`、缺日或額外日期；
- 每個 raw/canonical payload digest 可重算；
- `EMPTY` 重新正規化後仍是零根 Kbar。

### 4.4 跨 job duplicate

跨 job 的 canonical identity 是 `(symbol, session_date)`：

| 情況 | 行為 |
|---|---|
| digest、status、bar count、first/last event 全相同 | 安全去重，lineage 保存全部 job IDs |
| canonical digest 不同 | fail closed |
| digest 相同但 status/count/event boundary 不同 | fail closed |
| 一份 complete、一份 partial | 依合併後 exact-date identities 驗證；不可直接選 complete job 當勝者 |

不得依 job 新舊、status、資料量或列順序決定 winner。

### 4.5 Stable identity and replay

`source_snapshot_digest` 的 canonical projection 包含：

- source／version、requested dates、calendar digest；
- `TaiwanStockInfo` raw-body digest、mapping contract version；
- 依 symbol 升冪排序的 reference mapping projection：
  `(symbol, selected_date, name, market)`；
- volume／amount contracts；
- 每個納入 identity 的 symbol、date、status、bar count、canonical digest、
  first／last event；
- contributing job IDs。

並由 projection 內已存在的 event boundary 定義：

```text
snapshot_identity_at = max(included last_event_at)
manifest.created_at = snapshot_identity_at
```

Snapshot 必須至少包含一根 READY Kbar；若沒有任何 included `last_event_at`，
以 `EMPTY_DATASET` fail closed，不得用 wall clock 補值。Event boundary 先解析成
aware datetime，再 canonicalize 為 Asia/Taipei RFC3339 字串後進 projection。

partition 的 acquisition `created_at`／`updated_at` 只屬 audit metadata，完全
不進 source projection、Dataset ID 或 manifest digest。只改 acquisition 時間、
不改 canonical rows／event boundaries 時，所有 identity 必須保持一致；若
`last_event_at` 改變，source digest 必須改變。

```text
source_snapshot_digest = 64 lowercase hexadecimal SHA-256 characters
dataset_id = dataset-finmind-sponsor-sha256-<full source_snapshot_digest>
```

不得截短 digest，也沒有 prefix-length 或碰撞 fallback。若相同完整 Dataset ID
對到不同 source／manifest digest，視為 immutable identity corruption 並 fail
closed。

Materialization wall-clock time 只寫 operation audit，不寫 immutable manifest。
相同 semantic snapshot 即使在另一個乾淨環境重建，也必須得到相同 Dataset
ID 與 manifest digest。

final directory 已存在時：

1. 讀取既有 manifest；
2. 核對 source snapshot digest；
3. 串流驗證 payload checksum、bar count、order 與 manifest digest；
4. 完全相同則回傳既有 manifest；
5. 任一不同即 conflict，不覆寫。

並行第一次 materialization 使用不同 temporary directories；只有一個 writer
可原子發布，loser 必須驗證 winner 後 replay。

### 4.6 Reference metadata

`name` 與 `market` 會寫入 `bars.jsonl`，因此必須來自一份明確且
content-addressed 的外部 reference artifact：

```text
--stock-info-raw data/finmind_sponsor/universes/raw/TaiwanStockInfo_<sha>.json.gz
reference.dataset = TaiwanStockInfo
reference.raw_body_sha256 = sha256(gzip_decompress(file))
reference.mapping_contract = FINMIND_CURRENT_LISTING_REFERENCE_V1
```

檔名與 gzip container bytes 不是 authority；必須驗證解壓後 HTTP body digest、
FinMind response envelope 與 `TaiwanStockInfo` row schema。原始 response 沒有
Dataset-name 欄位，因此 Dataset 名稱是 CLI/plan 的凍結 input，不能宣稱由 body
自我證明。每個 included symbol 的 mapping 規則固定為：

1. symbol trim、uppercase，僅讀 valid ISO date 與 `type in {twse,tpex}`；
2. 使用該 exact artifact 內 symbol 的最大 valid date；
3. 同日重複 industry rows 可忽略 industry 後去重，但必須只剩一個
   `(stock_name, type)`；
4. `twse → TWSE`、`tpex → TPEX`，name trim 後不得為空；
5. included symbol 缺值、market 不支援或 identity ambiguous，整份 plan fail
   closed；不得用 symbol 代替 name，也不得留空 market。

對所有 included symbols 產生下列 canonical projection，依 symbol 升冪排序後
進 source projection、plan identity 與 immutable manifest：

```text
(symbol, selected_date, normalized_name, normalized_market)
```

不使用單一 `metadata_as_of_date` 代表所有股票。UI 若需要摘要，可從 mapping
projection 推導 `min_selected_date`／`max_selected_date`，但摘要值不是另一個
authority。Raw-body digest 與 mapping contract version 同樣進 source projection；
name／market 也會進 payload checksum。`TaiwanStockMarketValue` 不參與 bar
payload，bridge 不在 materialization 時重新查詢或另選市值資料。這份
reference 是 current descriptive metadata，不具 point-in-time 語意。

### 4.7 Volume, amount and proxy VWAP

新 snapshot 的 canonical token 固定為：

```text
volume.unit = COMMON_LOTS
amount.kind = DERIVED_CLOSE_X_VOLUME_PROXY
amount.is_actual_turnover = false
```

既有 daily manifests 的 `COMMON_LOT` bytes 與 digest 不改。Reader 只可透過
明確 legacy alias 解讀為同一 domain enum；新 materialization 不可輸出單數
token，也不可把 `close × volume` 描述成真實成交金額。

G0 選擇允許 `above_vwap_entry` 在這份 exploratory Dataset 執行，但計算名稱與
evidence 必須是 `COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY`，不可稱為 exchange
turnover VWAP：

- manifest 保存完整 amount contract 及 digest；
- immutable Run snapshot 複製 amount contract、digest 與 Dataset issue；
- `vwap_session_v1` Feature input／evaluation evidence 保存
  `amount.kind`、amount-contract digest 與 proxy semantic；
- comparability contract 將 amount-contract digest 視為必要相等 identity；
- Backtest runtime preflight 不可只看一般 `OHLCV` capability；若 exact Strategy
  Set 要求 `vwap_session_v1`，必須額外解析 Dataset amount contract；
- 第一批 allowlist 只有 `DERIVED_CLOSE_X_VOLUME_PROXY →
  COMPLETED_1M_CLOSE_VOLUME_WEIGHTED_PROXY`；符合時可建立 exploratory Run；
- amount kind 缺少或不在 allowlist 時，在建立 Run 前 fail closed；Feature
  adapter 執行時仍重驗證一次；
- 這是 `BACKTEST_KBAR_1M` adapter 的 input-contract 規則，不改變 Local Paper
  runtime binding 的獨立行情／Feature 來源；
- 由於 `research_eligible=false`，Qualification 一律拒絕，不因策略可執行而
  升格成正式研究證據。

### 4.8 Research status

第一批 FinMind snapshot 固定：

```text
universe_scope = CURRENT_SNAPSHOT
research_eligible = false
```

Manifest issues 至少包含：

- `PARTIAL_MARKET_UNIVERSE`
- `CURRENT_SNAPSHOT_SURVIVORSHIP_LIMITED`
- `RAW_PRICE_UNADJUSTED`
- `AMOUNT_DERIVED_PROXY`
- `REFERENCE_METADATA_CURRENT_NOT_PIT`

可以跑策略與比較相同 Dataset 的 Runs；Qualification 仍必須拒絕正式通過。

## 5. Components

### 5.1 `FinMindSemanticSnapshotReader`

建議新增 `backtest/finmind_snapshot.py`：

- `backup_source()`：online backup 至 task-scoped temporary path。
- `inspect()`：驗證 schema、job compatibility、identity conflicts。
- `plan()`：回傳 immutable `FinMindSnapshotPlan`。
- `iter_symbol_bars()`：依 symbol/date 讀取並重驗證 partitions。
- `source_snapshot_digest()`：計算 semantic digest。

`FinMindSnapshotPlan` 至少保存：

```text
schema_version
identity
  source_snapshot_digest
  snapshot_identity_at
  included identities and included-only READY/EMPTY/bar counts
  contributing job IDs and calendar digest
  TaiwanStockInfo raw_body_sha256 and mapping contract version
  sorted (symbol, selected_date, name, market) mapping projection
  volume/amount contracts
plan_identity_digest
selection_audit
  compatible job IDs
  excluded jobs/symbols and reason codes
  snapshot-observed selection counts
selection_audit_digest
handoff_evidence
  copied_sqlite_sha256
handoff_evidence_digest
locators
  copied_sqlite_path
  taiwan_stock_info_raw_path
operation_audit
  planned_at, actor, effective paths, expected output size, free-space evidence
operation_audit_digest
```

Digest 契約固定為：

```text
plan_identity_digest = sha256(canonical_json(identity))
selection_audit_digest = sha256(canonical_json(selection_audit))
handoff_evidence_digest = sha256(canonical_json(handoff_evidence))
operation_audit_digest = sha256(canonical_json(operation_audit))
```

`selection_audit` 保存當次 snapshot 的完整排除／相容性報告，但完全不進
`plan_identity_digest`、Dataset ID 或 immutable manifest；背景下載只增加仍不
完整 symbol 的 partition 時，只可改變 selection audit。Immutable `counts` 必須
完全由 included partition projection 推導。`locators` 完全不進
`plan_identity_digest`、`source_snapshot_digest`、Dataset ID、manifest digest
或 Run identity。`operation_audit` 也不進 immutable
identity，因為 wall clock、主機 path 與 free-space evidence 在 clean root 本來就
可能不同。`handoff_evidence` 只證明一次 plan→execute 使用指定的實體 SQLite
backup，也不進任何 immutable identity 或 manifest。Execute 可用 CLI 覆寫
locator；SQLite path 以 handoff SHA 驗證，reference raw path 以 identity 內的
raw-body SHA 驗證，並把 effective paths 寫入新的 operation audit。

Immutable manifest 只保存 canonical `identity` projection 與
`plan_identity_digest`，不可保存原始 plan body、locator 或 operation audit。
同樣不可保存 selection audit、copied SQLite SHA 或 handoff evidence。完整 plan
artifact（含 selection/handoff evidence）只進 materialization operation audit。
相同 canonical 資料即使
acquisition audit timestamps 或 SQLite page layout／整檔 bytes 不同，plan
identity、Dataset ID、payload 與 manifest digest 必須完全相同；selection
audit、handoff 與 operation audit digests 可以不同。

### 5.2 HistoricalDatasetCatalog extension

擴充既有 writer，不新增另一套 Engine 資料來源：

- input 是每個 symbol 的 validated sorted iterator；
- 以 k-way merge 寫成 `(timestamp, symbol)` 順序；
- bounded memory 只保留各 symbol 當前 head／session；
- 寫入時同步計算 bar count、payload checksum、cadence 與 watermarks；
- manifest 保存 source snapshot lineage 與 volume／amount contracts；
- manifest 保存 plan identity projection/digest，不保存 locator 或原始完整
  plan body；
- timestamp-major manifest 讓 Run 直接串流，不做外部排序。

### 5.3 CLI

新增 `scripts/materialize_finmind_backtest_dataset.py`：

```bash
python scripts/materialize_finmind_backtest_dataset.py \
  --plan \
  --source data/finmind_sponsor/history.sqlite3 \
  --stock-info-raw data/finmind_sponsor/universes/raw/TaiwanStockInfo_<sha>.json.gz \
  --snapshot-out data/backtest/finmind_plans/<operation>/source.sqlite3 \
  --plan-out data/backtest/finmind_plans/<operation>/snapshot-plan.json

python scripts/materialize_finmind_backtest_dataset.py \
  --execute --plan-file data/backtest/finmind_plans/<operation>/snapshot-plan.json \
  --snapshot-file /relocated/source.sqlite3 \
  --stock-info-raw /relocated/TaiwanStockInfo_<sha>.json.gz

python scripts/materialize_finmind_backtest_dataset.py \
  --execute --plan-file data/backtest/finmind_plans/<operation>/snapshot-plan.json \
  --activate-default \
  --expected-binding-revision 0 \
  --activation-idempotency-key <key> \
  --actor local-researcher \
  --change-note "activate verified FinMind snapshot"
```

- `--plan` 只建立 online-backup snapshot 與 canonical plan evidence，不寫
  Dataset 或 PostgreSQL。
- `--execute` 必須帶 `--plan-file`；locator 可來自 plan hints 或明確的
  `--snapshot-file`／`--stock-info-raw` override。執行前核對 plan identity
  digest、handoff evidence digest、copied-file SHA、reference raw-body SHA，並
  重算 semantic source digest。任一不符即 fail closed，絕不重新開啟 live
  source。若要使用 semantic 相同但 SQLite bytes 不同的獨立重建，必須先為
  該 backup 產生新的 plan/handoff artifact；不得竄改舊 handoff。
- `--execute` 不帶 activate 時只封存檔案；manifest lineage 只保存 canonical
  plan identity projection/digest，effective paths 只寫 operation audit。
- `--activate-default` 需要 PostgreSQL，先驗證完整 artifact，再做 registration
  與 binding，且四個 activation arguments 全部必填；PostgreSQL unavailable
  時 fail closed。

### 5.4 PostgreSQL Dataset registration

新增 repository operation：

```text
register_immutable_dataset(manifest)
```

- 不存在：INSERT READY。
- 同 dataset ID＋同 manifest digest：idempotent replay。
- 同 dataset ID＋不同 digest：409/conflict。
- 不使用一般 upsert 覆寫 immutable manifest。

### 5.5 Default binding

在 implementation preflight 確認 current migration tip。現在存在 concurrent
untracked `011_strategy_set_archives.sql`，因此本計畫不預先佔用檔名；若 011
保留，binding 使用下一個可用編號。

`backtest_dataset_bindings` 至少包含：

- `binding_name` primary key；
- `dataset_id`；
- `dataset_digest`；
- monotonic `revision`；
- actor、change note、created/updated timestamps。

同一 migration 另建立 durable activation operation／audit ledger，至少保存：

- binding name＋activation idempotency key unique；
- canonical request digest；
- target Dataset ID／digest、plan identity digest；
- caller-supplied expected revision；
- actor、change note；
- result kind、result revision 與 canonical response。

binding activation transaction：

1. request digest 必須包含 binding name、target Dataset ID／digest、plan
   identity digest、expected revision、actor、change note；
2. 以 PostgreSQL transaction-level lock 序列化固定 binding name，即使 revision
   `0` 尚無 head row 也能保護首次建立；
3. 在 lock 內依 idempotency key 重查 operation：same key／same request digest
   回放原 canonical result；same key／different digest 回 409；
4. 讀取 binding head；不存在時 current revision 定義為 `0`；
5. caller `expected_binding_revision` 必須等於 current revision，否則回
   `409 DATASET_BINDING_REVISION_CONFLICT`，不註冊 mutation audit、不改 head；
6. 驗證 Dataset row READY、PostgreSQL manifest digest 與 filesystem manifest
   digest；
7. target Dataset ID／digest 與 current target 相同時，保存
   `NOOP_ALREADY_BOUND`
   operation result，revision 不增加；
8. target 不同時建立 revision `current + 1`，保存 actor／change note／old-new
   identity 與 operation result；
9. binding head、revision audit 與 operation result 在同一 transaction commit。

首次建立必須傳 expected revision `0`，成功後 revision 是 `1`。Stale revision
即使 target 剛好相同也回 409；只有相同 idempotency key／request digest 的
durable response-loss replay 可以略過目前 revision 檢查並回傳原結果。使用新
key、current expected revision 且 target 相同則是 NOOP，revision 仍不增加。

正式 binding name：`ATOMIC_BACKTEST_DEFAULT`。

## 6. Application and Web selection

### 6.1 Resolver

| 情境 | Dataset identity |
|---|---|
| response-loss replay | 原 Run Dataset |
| retry/clone requiring original semantics | 原 Run Dataset |
| Challenger | Baseline Dataset |
| 新 standalone Atomic Run | `ATOMIC_BACKTEST_DEFAULT` |

Standalone resolution 失敗條件：

- binding 不存在；
- Dataset 不存在或不是 READY；
- bound digest 與 registry/filesystem manifest 不符；
- exact Strategy Set required capabilities 不相容；
- Strategy Set 要求 `vwap_session_v1`，但 Dataset amount contract 缺少、未知或
  不符合 Backtest adapter allowlist。

不得靜默 fallback 到其他 READY Dataset。

新 standalone request 必須包含：

```text
expected_binding_revision
expected_dataset_digest
```

處理順序固定：

1. 先以 idempotency key＋request digest 查 durable Run operation；
2. same-key／same-digest 回放原 Run，不讀目前 binding；
3. same-key／different-digest 回 `409 IDEMPOTENCY_CONFLICT`；
4. 新 operation 在 transaction 內鎖定／讀取 binding head；
5. revision 或 Dataset digest 與 request precondition 不同，回
   `409 ATOMIC_BACKTEST_BINDING_CHANGED`，不建立 Run；
6. 相同才驗證 Dataset／Strategy Set compatibility 並建立 immutable Run。

Request digest 必須包含兩個 binding preconditions；不得在 digest 前先把它們
替換成目前 binding 值。

### 6.2 Web

Web 不自行 `find(research_eligible)`。API 回傳 resolved binding projection：

- binding name/revision；
- Dataset ID/digest；
- source、start/end、symbol/bar counts；
- capabilities；
- amount kind/digest 與 VWAP semantic label；
- research eligibility 與 issues。

按鈕只有在 binding 完整且策略能力相容時可用。畫面顯示的 Dataset 必須與
submit 後 Run 保存的 Dataset 完全相同。前端以 hidden state 保存
`expected_binding_revision` 與 `expected_dataset_digest` 並隨 POST 提交；409
時不得自動改用新 binding，必須重新整理 projection、提示使用者再確認。

## 7. Large-run DB throttling

Engine 可保留每 128 bars 的 local callback cadence，但 callback 只讀記憶體
cache，不得每次碰 PostgreSQL。

`DurableRunControlProbe`：

- 使用 monotonic clock；
- durable cancellation poll 預設最多每秒一次；
- poll 後 cache status；
- local callback 讀 cache；
- DB error fail closed，使 Run 失敗而不是忽略取消狀態。

`ThrottledProgressReporter`：

- progress UPDATE 預設最多每秒一次，或進度跨越設定 delta；
- phase/status 變更立即寫入；
- terminal COMPLETED／FAILED／CANCELLED 強制 flush；
- clock／throttle state 不進 config/result digest。

驗收需計算實際 DB SELECT/UPDATE 數量，證明其隨 wall time／progress delta
成長，而不是隨 Kbar 數線性成長。

## 8. Failure and recovery

| Failure | Required behavior |
|---|---|
| live acquisition continues after backup | 只影響下一版 snapshot |
| source backup interrupted | 不建立 Dataset directory/row |
| plan/copy digest mismatch | execute fail closed，不回讀 live source |
| reference raw missing/digest drift | plan/execute fail closed |
| reference symbol missing/ambiguous | 整份 plan fail closed，不填 fallback name/market |
| duplicate digest conflict | dry-run/execute fail closed |
| disk insufficient | 寫入前拒絕 |
| crash during materialization | final directory 不可見；unique temp 可清理 |
| file sealed, PostgreSQL unavailable | 保留 orphan immutable artifact；不標 READY/default，重跑可 reconcile |
| registration replay | 同 digest 回放 |
| activation expected revision stale | 回 409，不改 binding revision／target |
| activation response lost | same key／request digest 回放原 result，不依目前 head |
| activation same current target | 保存 no-op operation result，不增加 revision |
| binding switch failure | 保留舊 binding |
| Web binding revision/digest drift | 回 409，禁止建立 Run，不自動跟隨新 binding |
| Run worker restart | 既有 Run evidence不變；恢復策略另依現有 Run contract處理 |

Rollback 不刪除 Dataset 或 Runs，只把 default binding 以新 revision 切回前一個
已驗證 Dataset。

## 9. Test Plan

### 9.1 Snapshot unit tests

- backup 期間 source 新增 partition，plan 仍固定。
- complete／partial／INVALID／EMPTY selection。
- exact calendar set，不以 count 冒充完整。
- compatible/incompatible jobs。
- duplicate equal digest dedupe。
- duplicate different digest conflict。
- only partition `updated_at` changes: source/Dataset/manifest digests unchanged。
- event boundary changes: source digest changes。
- stable semantic digest and `snapshot_identity_at`。
- full 64-hex digest produces the exact frozen Dataset ID；no truncation path。
- saved plan identity digest plus separate copy-SHA handoff；execute never reopens live
  source。
- same canonical rows with different acquisition audit timestamps and different
  SQLite file SHA/page layout produce identical source/plan/Dataset/manifest
  identity while handoff digest may differ。
- excluded symbol gains partitions but remains incomplete: source/Dataset/plan
  identity stay identical while selection audit digest changes。
- execute rejects a copied SQLite file that does not match that plan artifact's
  handoff evidence, even if a separate rebuild could be semantically equal。
- same identity and files under different locator paths produce the same plan,
  Dataset, payload, and manifest identities。
- locator/host/free-space changes affect operation audit only。
- manifest contains plan identity projection/digest and no path/full-plan body,
  selection audit, copied SQLite SHA, or handoff evidence。
- KeyboardInterrupt/SystemExit before plan publication removes only the snapshot
  created by that invocation; a completed snapshot/plan pair remains intact。
- required `TaiwanStockInfo` raw-body digest and Dataset validation。
- latest-date duplicate-industry collapse with unique name/market identity。
- sorted per-symbol selected-date/name/market projection is deterministic；
  derived min/max summary does not replace it。
- missing, blank, unsupported, or ambiguous reference identity fails closed。
- `COMMON_LOTS` new output and `COMMON_LOT` legacy read compatibility。
- amount proxy evidence and unknown amount kind fail closed。
- `OHLCV` present but VWAP amount input contract missing/unknown still fails
  preflight。
- proxy rule is Backtest-runtime specific and does not alter Local Paper input
  semantics。

### 9.2 Materialization tests

- bounded-memory multi-symbol write。
- strict timestamp/symbol order。
- no external-sort path for new snapshot。
- checksum/count/watermark/cadence verification。
- same snapshot in clean roots produces same ID/manifest digest。
- same semantic data with different acquisition audit timestamps produces the
  same payload and manifest identity。
- existing directory exact replay。
- existing directory conflict。
- concurrent first writers converge to one artifact。
- disk-space preflight and interrupted temp recovery。

### 9.3 PostgreSQL tests

- migration tables/indexes/constraints。
- register, replay, different-digest conflict。
- concurrent registration。
- binding CAS/revision/audit。
- first activation expected `0` creates revision `1`。
- stale expected revision returns 409 and cannot restore an older Dataset。
- same current target with current expected revision is no-op without revision
  increase。
- same activation key/request digest replays original response；same key with
  different digest conflicts。
- concurrent activations from the same expected revision permit one mutation。
- non-READY/missing/file-drift refusal。
- PostgreSQL unavailable and no SQLite fallback。

### 9.4 API/UI tests

- standalone uses exact default binding。
- replay and Challenger retain original identities。
- no fallback to research-eligible or newest Dataset。
- UI projection equals created Run Dataset。
- matching binding revision/digest creates Run。
- binding switched after GET returns 409 and creates no Run。
- same-key/same-digest response-loss replay returns the original Run after a
  binding switch；different request digest conflicts。
- missing/incompatible binding disables submit and explains reason。
- proxy amount kind/digest is present in Run snapshot and VWAP Feature evidence。
- Web binding projection labels the VWAP source as close-volume proxy。
- Runs with different amount-contract digests are not comparable。
- proxy Dataset remains ineligible for Qualification。

### 9.5 Throttle tests

- many local callbacks produce bounded SELECT/UPDATE counts。
- cancellation becomes visible within configured interval。
- terminal progress always flushes。
- monotonic clock rollback is irrelevant。
- DB poll failure fails closed。

### 9.6 Real acceptance

- saved `--plan` identity evidence and execute use the exact same copied source；counts
  are recorded, not compared to a hard-coded number。
- full artifact checksum/readback passes。
- disposable PostgreSQL full suite passes。
- exact artifact is registered and bound。
- one full Atomic Run completes。
- provider/broker call count during Run is zero。

## 10. File Map

| File | Planned change |
|---|---|
| `backtest/finmind_snapshot.py` | New consistent snapshot reader and semantic plan |
| `backtest/finmind_history.py` | Minimal read-only helpers/volume enum integration; acquisition behavior unchanged |
| `backtest/dataset.py` | Stable lineage fields and bounded timestamp-major writer |
| `backtest/feature_adapters.py` | Preserve proxy amount contract in VWAP Feature input/evaluation evidence |
| `features/specifications.py` | Declare the runtime input-contract evidence required by `vwap_session_v1` without conflating Backtest and Local Paper sources |
| `backtest/comparability.py` | Require exact amount-contract identity |
| `backtest/repository.py` | Immutable registration and binding protocol |
| `backtest/postgres_repository.py` | PostgreSQL transaction/CAS implementation |
| `backtest/migrations/<next>_backtest_dataset_bindings.sql` | Binding head, revision audit, and durable activation-operation schema after migration-tip preflight |
| `backtest/application.py` | Exact binding resolver and throttled Run control |
| `dashboard/server.py` | Binding projection and strict Run precondition request fields |
| `dashboard/static/js/workspaces/backtest.js` | Render server binding and submit its hidden revision/digest preconditions |
| `scripts/materialize_finmind_backtest_dataset.py` | Plan/execute/activate CLI |
| `tests/test_finmind_backtest_snapshot.py` | Snapshot and materialization contracts |
| `tests/test_postgres_backtest.py` or focused new module | PostgreSQL registration/binding contracts |
| `tests/test_atomic_strategy_web_backtest.py` | Resolver/replay/Baseline behavior |
| `tests/test_backtest_streaming_memory.py` | Timestamp-major and bounded control tests |
| `README.md` | Operator workflow and exploratory limitations |

## 11. Implementation Order and Gates

1. **G0 Contract Review** — timestamp/full-digest identity, locator exclusion,
   plan handoff, per-symbol reference mapping, proxy semantics, duplicate/unit
   rules, binding activation CAS/replay, and migration ownership frozen.
2. **G1 Snapshot Reader** — deterministic saved-plan/copy handoff and conflict
   tests pass.
3. **G2 Small Materialization** — clean-root replay has exact same digest.
4. **G3 Full Artifact** — one dynamic full snapshot atomically sealed and read back.
5. **G4 PostgreSQL Binding** — disposable PostgreSQL registration/concurrency passes.
6. **G5 Web Full Run** — actual binding is displayed and one full Atomic Run completes
   with bounded control traffic and zero provider/broker calls.

The selector-less Web flow is not deliverable before G4. The bridge is not
complete before G5.

## 12. Definition of Done

- Same semantic source snapshot always produces the same Dataset and manifest
  identity, including in a clean output root.
- Acquisition audit timestamp differences alone cannot change Dataset identity.
- Execute consumes the exact copied SQLite and reference raw artifact approved
  by the saved plan; it never silently resnapshots live acquisition state.
- Locator and host-operation changes cannot alter plan/Dataset/manifest
  identity; manifests never retain local paths.
- SQLite whole-file bytes are handoff evidence only; different page layout or
  acquisition audit timestamps cannot alter immutable Dataset/manifest identity.
- Dataset ID uses the complete lowercase 64-hex source SHA-256.
- Cross-job conflicts cannot be hidden by job ordering.
- Every included symbol has one unambiguous content-addressed name/market
  mapping; missing reference metadata never falls back silently.
- New snapshots use `COMMON_LOTS`; legacy manifests remain replayable without
  digest changes.
- `amount` and VWAP are visibly proxy semantics, preserved in Dataset, Run,
  Feature evidence, and comparability; proxy Runs cannot qualify.
- Full Dataset creation and replay remain bounded-memory.
- PostgreSQL is authoritative for immutable registration and default binding.
- Default activation requires caller expected revision and cannot let a stale
  plan overwrite a newer binding; replay/no-op never increments revision.
- Web display and Run identity come from the same binding revision/digest, with
  a 409 precondition failure instead of TOCTOU switching.
- Neither progress nor cancellation DB traffic grows linearly with Kbar count.
- Partial/invalid source data never enters the Dataset.
- Counts are dynamic snapshot evidence, not hard-coded gates.
- No real-time market data, account, broker order, CA, trade subscription, or
  real-money capability is added.
