# Working Tree 分批提交與 Git 衛生 Implementation Plan

## 0. 文件狀態

- 狀態：`PLAN_ONLY / NOT_IMPLEMENTED`
- Source snapshot：`main@d0e271e0a247c669adae23423244de0cc7200832`
- 規劃日期：`2026-08-28`
- 計畫代號：`HYG-001`
- 預估工期：1～1.5 個開發日
- 安全邊界：**不改任何 production 行為**。本計畫只做 Git 提交分群、`.gitignore` 補洞與備份；不得修改任何 `.py` 的邏輯、不得 rebase、不得 force push、不得刪除任何 research／records 證據檔。

### 0.1 執行環境假設（交付給外部 LLM 時必讀）

- 可執行 `python -m pip install -e ".[dev]"` 與 `python -m pytest`（預設 `MockProvider`，不需網路行情）。
- **沒有** Shioaji API 金鑰、**沒有** PostgreSQL、**不可**連真實行情。任何需要上述資源的驗收步驟一律標記為 `SKIP_IN_SANDBOX`，由 owner 在本機補做。
- 本計畫的實際執行必須在 owner 本機（有完整 `.venv` 與 macOS launchd 環境）進行；外部 LLM 的產出是**可審核的指令腳本與分群清單**，不是直接推送的 commit。

---

## 1. 結論先講

目前 `main@d0e271e` 的工作目錄同時混著至少 **6 個不同主題**的未完成工作：37 個 modified 檔案、128 筆 untracked 項目，總計 165 筆 `git status` 變更。這代表沒有任何一個 commit 邊界能對應到單一 ticket，一旦誤操作（`git checkout .`、`git stash drop`、IDE 的 discard）就會同時損失多個 ticket 的成果。

另外，`.git/index.lock` 目前**存在且為 0 bytes**（timestamp `2026-08-28 03:43`）。這會讓所有寫入型 git 指令（`add` / `commit` / `checkout`）直接失敗。

本計畫完成後：

1. `.git/index.lock` 已移除，寫入型 git 指令恢復正常。
2. 工作目錄的所有變更已被明確分類為「要提交」「要忽略」「要保留為本機證據」三類，且有一份可審核的分群清單。
3. 每個主題各自成為一個獨立、可通過測試的 commit，訊息遵循既有 `feat(scope):` / `fix:` / `docs():` 慣例。
4. `.gitignore` 補上目前會誤把 20GB `data/` 內容納入 `git add -A` 的破口。
5. 全程有 `git bundle` 備份，任何一步都可回滾。

---

## 2. 現況與主要缺口

### 2.1 現況實測

| 項目 | 實測值 |
|---|---|
| HEAD | `d0e271e0a247c669adae23423244de0cc7200832`（branch `main`） |
| Modified 檔案 | 37 |
| Untracked 項目 | 128 |
| `git status --short` 總行數 | 165 |
| `.git/index.lock` | **存在**，0 bytes，`2026-08-28 03:43` |
| `data/` 大小 | 20 GB（完全 untracked） |
| `research/` | 284 tracked + 79 untracked，41 MB |
| `records/` | 41 tracked + 4 untracked 日期資料夾，70 MB |

### 2.2 P0 缺口

1. **`index.lock` 阻塞寫入**：任何 `git add` / `git commit` 會回報 `Unable to create '.git/index.lock': File exists`。必須在所有其他步驟之前處理。
2. **多主題混雜**：`backtest/atomic_benchmark/`、`market_data/late_delivery_*`、`backtest/finmind_*`、`market_data/shioaji_momentum_stream.py` 分屬四個不同 ticket，卻共存於同一個 dirty tree。
3. **`.gitignore` 破口**：`.gitignore` 只忽略 `data/backtest/`、`data/finmind_sponsor/`、`data/premarket/`、`data/local_paper/`，但 `data/institutional_mvp/` 與 `data/.locks/` **未被忽略**。因此 `git status` 把整個 `data/` 列為 untracked，而一次 `git add -A` 會嘗試把 20 GB 的 runtime artifact 加入索引。
   - 這與已記錄的設計意圖直接衝突：`.planning/2026-08-28-institutional-research-main-merge/findings.md` 明載「The runtime artifacts under `data/institutional_mvp` are intentionally left untracked」。意圖存在，但沒有寫進 `.gitignore`。
4. **`WORKFLOW.md` 未進版控**：專案的開發流程規範文件（326 行）目前是 untracked。任何 clone 出來的副本都拿不到流程定義。
5. **已完成的架構文件未提交**：`architecture/local_paper_tax_slippage_implementation_plan.md`、`architecture/local_paper_kill_switch_durability_implementation_plan.md`、`architecture/r6_g3_dynamic_entry_reserve_amendment_a2.md` 三份都是 untracked。

### 2.3 非缺口（明確不處理）

- `research/` 與 `records/` 的自動化 capture 證據**是設計上要進版控的**（已有 284 / 41 個 tracked 檔案）。本計畫不改變這個決定，只把新產生的批次提交進去。
- `.venv/`、`build/`、`__pycache__/`、`.coverage`、`shioaji.log` 已被正確忽略，不需處理。

---

## 3. Scope

### 3.1 In scope

- 移除 `.git/index.lock` 並確認無殘留 git 程序。
- 建立完整備份（`git bundle` + 未追蹤檔清單）。
- 將 165 筆變更分類為 T1～T8 八個主題群。
- 依主題產生 8 個以內的獨立 commit。
- 修補 `.gitignore` 的 `data/` 破口。
- 產出一份 `research/working_tree_triage_2026-08-28.md` 分群紀錄，供事後稽核。

### 3.2 Non-goals

- **不修改任何 Python 檔案的行為**。若某主題的測試現在是紅的，就把該主題留在工作目錄不提交，並在分群清單標註原因，不得為了讓它變綠而改程式。
- **不處理 `tests/test_price_coverage_scan_segment_manifest.py`**。該檔的改動屬於獨立計畫 `PCD-001`（見 `architecture/price_coverage_source_digest_drift_implementation_plan.md`），本計畫必須把它排除在所有 commit 之外並明確標註「移交 PCD-001」。
- 不做 `git rebase`、`git commit --amend`、`git push --force`、`git filter-branch`。
- 不刪除任何 `research/`、`records/`、`data/` 底下的檔案。
- 不建立 PR、不合併、不動 remote。

---

## 4. 主題分群（T1～T8）

以下分群已依實測的 `git status` 逐檔對應。執行者必須先用 Phase 1 的腳本驗證此清單與當下 `git status` 完全一致；若有差異，**停止並回報差異**，不得自行推測歸屬。

### T1 — R6 Atomic Benchmark / G3 Dynamic Entry Reserve

```text
M  backtest/atomic_benchmark/application.py
M  backtest/atomic_benchmark/preflight.py
M  scripts/preflight_atomic_entry_benchmark.py
M  tests/test_atomic_entry_benchmark_full_dataset.py
M  tests/test_atomic_entry_benchmark_postgres.py
?? backtest/migrations/018_r6_dynamic_entry_reserve.sql
?? scripts/apply_r6_g3_migration_018.py
?? scripts/audit_atomic_entry_benchmark_eligibility.py
?? scripts/supervise_atomic_entry_benchmark_preflight.py
?? tests/test_apply_r6_g3_migration_018.py
?? tests/test_audit_atomic_entry_benchmark_eligibility.py
?? tests/test_supervise_atomic_entry_benchmark_preflight.py
?? architecture/r6_g3_dynamic_entry_reserve_amendment_a2.md
```

建議訊息：`feat(r6): add G3 dynamic entry reserve migration and eligibility audit`

注意：`tests/test_atomic_entry_benchmark_postgres.py` 與 `tests/test_apply_r6_g3_migration_018.py` 需要 PostgreSQL，在 sandbox 會 skip。這是**預期行為**，不是失敗。

### T2 — FinMind / Fugle Source Repair 與 Selection Bundle

```text
M  backtest/finmind_snapshot.py
M  scripts/download_finmind_sponsor_history.py
M  tests/test_finmind_sponsor_history.py
?? backtest/finmind_selection_bundle.py
?? backtest/finmind_source_repair.py
?? backtest/fugle_source_repair.py
?? scripts/build_finmind_phase82_selection_bundle.py
?? scripts/capture_fugle_source_repair_candidate.py
?? scripts/derive_fugle_source_repair_candidate.py
?? scripts/manage_finmind_source_repair.py
?? scripts/verify_finmind_selection_bundle.py
?? tests/test_finmind_selection_bundle.py
?? tests/test_finmind_source_repair.py
?? tests/test_fugle_source_repair.py
?? docs/finmind_source_repair.md
```

建議訊息：`feat(backtest): add FinMind source repair and phase82 selection bundle`

### T3 — Late Delivery Capture / D-Health

```text
M  market_data/late_delivery_capture.py
M  market_data/late_delivery_capture_cli.py
M  market_data/late_delivery_daily_cli.py
M  market_data/late_delivery_evidence.py
M  tests/test_late_delivery_capture.py
M  tests/test_late_delivery_evidence.py
?? scripts/run_one_shot_late_delivery_open.py
?? tests/test_run_one_shot_late_delivery_open.py
?? scripts/launchd/com.stevehuang.tw-intraday-trader.d-health-late-001-open-20260828.plist
```

建議訊息：`feat(market-data): add one-shot late-delivery open capture`

### T4 — Shioaji Momentum Stream

```text
M  market_data/shioaji_momentum_stream.py
M  tests/test_shioaji_momentum_stream.py
```

建議訊息：`fix(market-data): harden Shioaji momentum stream`（實際動詞依 `git diff` 判定）

### T5 — Freshness Calibration 排程

```text
M  scripts/launchd/com.stevehuang.tw-intraday-trader.freshness-calibration.plist
M  tests/test_freshness_calibration_schedule.py
```

建議訊息：`chore(schedule): update freshness calibration launchd window`

### T6 — 其他遷移測試

```text
M  tests/test_backtest_sqlite_postgres_migration.py
M  tests/test_strategy_migrations.py
```

這兩個檔案很可能是 T1 的 migration 018 帶出的連動修改。執行者必須用 `git diff` 確認：若 diff 明確引用 018，則**併入 T1**；否則獨立成 commit `test: update migration list acceptance`。

### T7 — 文件與規劃紀錄

```text
M  findings.md
M  progress.md
M  task_plan.md
M  .planning/.active_plan
M  .planning/2026-08-20-pr008-review-followup/{findings,progress,task_plan}.md
M  .planning/2026-08-21-finmind-sponsor-three-year-rebuild/{findings,progress,task_plan}.md
M  .planning/2026-08-24-finmind-premarket-strategy-impl-plan/{findings,progress,task_plan}.md
M  .planning/2026-08-26-r6-atomic-strategy-benchmark/{findings,progress,task_plan}.md
?? WORKFLOW.md
?? architecture/local_paper_kill_switch_durability_implementation_plan.md
?? architecture/local_paper_tax_slippage_implementation_plan.md
?? .planning/2026-08-24-finmind-premarket-strategy-impl-plan/implementation_plan.md
?? .planning/2026-08-24-vwap-strategy-failure-attribution/audit_r5_terminal.py
?? .planning/2026-08-24-vwap-strategy-failure-attribution/execute_r5_control.py
?? .planning/2026-08-25-pr-tm-012c1-c1-runtime/
?? .planning/2026-08-25-uncommitted-commit-packaging/
?? .planning/2026-08-26-kill-switch-durable-control-implementati/
?? .planning/2026-08-26-local-paper-tax-slippage-implementation-/
?? .planning/2026-08-26-next-parallel-tasks-after-kill-switch-an/
?? .planning/2026-08-26-pr-tm-012c1-next-session-prep/
?? .planning/2026-08-26-pr-tm-012c1-review-remediation/
?? .planning/2026-08-26-pr-tm-012c1-shadow/
?? .planning/2026-08-27-d-health-late-recovery/
?? .planning/2026-08-27-pr-tm-012c1-shadow/
（以及其餘 .planning/2026-08-27 ～ 2026-08-28 的新資料夾）
```

建議拆成兩個 commit：

- `docs: track WORKFLOW.md and completed architecture plans`（`WORKFLOW.md` + 三份 `architecture/*.md`）
- `docs(planning): sync planning workpads through 2026-08-28`（`.planning/` 與根目錄三件套）

### T8 — 自動化產生的證據檔

```text
?? research/captures/freshness_broker_account/*.json        （16 檔）
?? research/captures/freshness_quote/*.json                 （17 檔）
?? research/freshness_calibration/broker_account_scheduled_runs/*.json （16 檔）
?? research/freshness_calibration/scheduled_runs/*.json     （14 檔）
?? research/freshness_calibration/reviews/*.md              （4 檔）
?? research/trade_management_shadow/premarket_2026082*.json(.sha256)
?? research/trade_management_shadow/session_input_drafts/
?? research/late_delivery_evidence/runtime/
?? research/finmind_source_repairs/
?? research/finmind_source_repair_9960_20260320_tpex_daily_v1.json
?? records/market_events/2026-08-25/ ～ 2026-08-28/
```

建議訊息：`chore(research): archive 2026-08-25..28 scheduled capture evidence`

**決策點**：這批 79 + 4 個檔案是 launchd 排程每日產生的，會持續累積（目前 `research/` 41 MB、`records/` 70 MB）。本計畫先照既有慣例提交，但必須在 `research/working_tree_triage_2026-08-28.md` 記下「長期需決定保留政策」，並開一張後續票，不在此處變更政策。

### T9 — 不提交（明確排除）

```text
M  tests/test_price_coverage_scan_segment_manifest.py   → 移交 PCD-001
?? data/                                                → 應由 .gitignore 忽略（Phase 4 處理）
```

---

## 5. 實作階段

### Phase 0 — 解鎖與備份（阻塞全部後續階段）

1. 確認沒有殘留的 git 程序：

   ```bash
   ps aux | grep -i '[g]it'
   ```

2. 確認 `index.lock` 為 0 bytes（代表是中斷留下的空鎖，不是進行中的交易）：

   ```bash
   ls -la .git/index.lock
   ```

3. 移除鎖：

   ```bash
   rm -f .git/index.lock
   ```

4. 驗證寫入型指令恢復：

   ```bash
   git status --short > /tmp/status_before.txt && wc -l /tmp/status_before.txt
   ```

5. 建立備份：

   ```bash
   git bundle create ../tw_intraday_trader_backup_20260828.bundle --all
   git status --short > research/working_tree_triage_2026-08-28.raw.txt
   ```

**Acceptance**：`git status --short` 成功執行且無 lock 警告；bundle 檔存在且 `git bundle verify` 通過；`/tmp/status_before.txt` 為 165 行。

**Status**：`NOT_STARTED`

### Phase 1 — 分群清單產生與比對

1. 撰寫 `scripts/triage_working_tree.py`（**新檔，本計畫唯一允許新增的程式**）：
   - 讀取 `git status --porcelain`。
   - 依第 4 章的 T1～T9 規則（以檔案路徑 prefix / glob 對應）分類。
   - 對任何**無法歸類**的路徑，列入 `UNCLASSIFIED` 區塊。
   - 輸出 Markdown 到 `research/working_tree_triage_2026-08-28.md`。
2. 執行並人工檢查 `UNCLASSIFIED` 區塊。

**Acceptance**：`UNCLASSIFIED` 為空；分群後各群檔案數總和 == 165；`research/working_tree_triage_2026-08-28.md` 已產生。

**若 `UNCLASSIFIED` 非空**：停止，回報未歸類清單給 owner，不得自行猜測。

**Status**：`NOT_STARTED`

### Phase 2 — 逐主題提交

對 T1～T8 每一群，依序執行：

1. `git add <該群的明確檔案清單>`（**禁止使用 `git add -A` 或 `git add .`**）。
2. `git status --short` 確認暫存區只有該群的檔案。
3. 執行該群相關的 focused 測試（見下表）。
4. 測試通過才 `git commit`；不通過則 `git reset HEAD <該群>`，把該群標記為 `DEFERRED` 並在 triage 文件記錄失敗訊息。

| 群 | Focused 測試指令 |
|---|---|
| T1 | `python -m pytest tests/test_atomic_entry_benchmark_full_dataset.py tests/test_audit_atomic_entry_benchmark_eligibility.py tests/test_supervise_atomic_entry_benchmark_preflight.py -q` |
| T2 | `python -m pytest tests/test_finmind_sponsor_history.py tests/test_finmind_selection_bundle.py tests/test_finmind_source_repair.py tests/test_fugle_source_repair.py -q` |
| T3 | `python -m pytest tests/test_late_delivery_capture.py tests/test_late_delivery_evidence.py tests/test_run_one_shot_late_delivery_open.py -q` |
| T4 | `python -m pytest tests/test_shioaji_momentum_stream.py -q` |
| T5 | `python -m pytest tests/test_freshness_calibration_schedule.py -q` |
| T6 | `python -m pytest tests/test_backtest_sqlite_postgres_migration.py tests/test_strategy_migrations.py -q` |
| T7 | 無程式碼變更，改跑 `git diff --check`（whitespace）|
| T8 | 無程式碼變更，改跑 `git diff --check` |

**Acceptance**：每個成功的 commit 都只含該群檔案（用 `git show --stat` 驗證）；`DEFERRED` 群的原因已記錄。

**Status**：`NOT_STARTED`

### Phase 3 — `.gitignore` 補洞

在 `.gitignore` 的「Local immutable historical backtest datasets」區塊補上：

```gitignore
# Runtime artifacts intentionally kept out of version control
# (see .planning/2026-08-28-institutional-research-main-merge/findings.md)
data/institutional_mvp/
data/.locks/
```

**Acceptance**：`git status --short | grep '^?? data/'` 無輸出；`git check-ignore -v data/institutional_mvp` 指向新加入的規則。

**注意**：只加 ignore 規則，**不得**執行 `git rm --cached`（目前 `data/` tracked 數為 0，本來就沒被追蹤，不需要移除）。

**Status**：`NOT_STARTED`

### Phase 4 — 最終驗證

1. `git status --short | wc -l` 應大幅下降；剩餘項目必須恰好等於 T9（`tests/test_price_coverage_scan_segment_manifest.py`）加上任何 `DEFERRED` 群。
2. `git log --oneline -10` 確認 commit 訊息格式與既有慣例一致。
3. 全套測試：

   ```bash
   python -m pytest tests/ -q
   ```

   預期結果：除了 `PCD-001` 追蹤中的 r2 price-coverage 失敗（1 failed）與需要 PostgreSQL / Shioaji 的 skip 之外全綠。**不得**為了讓那 1 個失敗變綠而修改任何檔案。
4. `python -m compileall -q app.py backtest candidate config dashboard features market_data position runtime scoring signals simulation strategy_catalog trading scripts tests`
5. `git diff --check`

**Acceptance**：上述 5 項全部通過；`research/working_tree_triage_2026-08-28.md` 最終版已提交。

**Status**：`NOT_STARTED`

---

## 6. 回滾程序

任何階段出錯：

```bash
# 回到本計畫開始前的 HEAD（commit 只是新增，不會動到既有歷史）
git reset --soft d0e271e0a247c669adae23423244de0cc7200832
# 檔案內容完全不受影響，回到全部 unstaged 的狀態
```

若連工作目錄都損壞，用 Phase 0 的 bundle 還原：

```bash
git clone ../tw_intraday_trader_backup_20260828.bundle recovered_repo
```

---

## 7. 風險

| 風險 | 等級 | 緩解 |
|---|---|---|
| `index.lock` 其實是進行中交易，刪除會壞索引 | 低 | Phase 0 先確認為 0 bytes 且無 git 程序；已有 bundle 備份 |
| 誤用 `git add -A` 把 20 GB `data/` 加入索引 | **高** | Phase 2 明令禁止 `-A` / `.`；Phase 3 補 ignore 規則 |
| 分群歸屬判斷錯誤，把兩個 ticket 的改動混進一個 commit | 中 | Phase 1 的 `UNCLASSIFIED` 必須為空才能繼續；T6 明訂要看 diff 才決定歸屬 |
| 某群測試本來就是紅的，執行者為了提交而改程式 | 中 | Non-goals 明訂禁止；改用 `DEFERRED` 標記 |
| 提交過程被 PCD-001 的失敗測試干擾 | 低 | T9 明確排除；Phase 4 預期結果已寫明容許該 1 failed |

---

## 8. 交付物

1. `scripts/triage_working_tree.py`
2. `research/working_tree_triage_2026-08-28.md`（分群紀錄，含 `DEFERRED` 原因）
3. `.gitignore` 更新
4. 8 個以內的主題 commit
5. `../tw_intraday_trader_backup_20260828.bundle`（不進版控）
