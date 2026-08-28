# Institutional 模組邊界收斂 Implementation Plan

## 0. 文件狀態

- 狀態：`PLAN_ONLY / NOT_IMPLEMENTED`
- Source snapshot：`main@d0e271e0a247c669adae23423244de0cc7200832`
- 規劃日期：`2026-08-28`
- 計畫代號：`ARCH-001`
- 預估工期：3～4 個開發日，另加 0.5 日獨立 review
- 安全邊界：**本計畫是「文件化 + 邊界防護」，不是重構**。不得搬移、合併、刪除任何 `institutional_*` 模組的既有程式碼，不得改變任何函式簽章或行為，不得改變四個模組的 `research_eligible=false` 等 fail-closed 語意。

### 0.1 執行環境假設（交付給外部 LLM 時必讀）

- 可執行 `python -m pip install -e ".[dev]"` 與 `python -m pytest`（預設 `MockProvider`）。
- **沒有** Shioaji 金鑰、**沒有** PostgreSQL、**不可**連真實行情或 FinMind API。
- 本計畫新增的測試必須是純靜態分析（AST / import 掃描），**不得**在測試中實際載入需要外部資源的模組或執行任何 provider 呼叫。

---

## 1. 結論先講

專案有四個名稱高度相似的法人資料模組，合計 **12,456 行**程式碼：

| 模組 | LOC | 現有 docstring |
|---|---:|---|
| `institutional_data` | 2,503 | Post-close institutional-flow data contracts. |
| `institutional_research` | 3,167 | Exploratory institutional factor diagnostics; no execution semantics. |
| `institutional_prior` | 2,234 | Exploratory institutional Candidate Prior; no trading semantics. |
| `institutional_mvp` | 4,552 | Non-formal, read-only institutional MVP utilities. |

實際 import 分析顯示，它們**不是**一條演進鏈，而是**兩條平行血脈**：

```text
         institutional_data  ← 共同 base（contracts + serialization），不依賴其他 institutional_*
            /            \
  (血脈 A)  /              \  (血脈 B)
institutional_research      institutional_mvp
       |                          |
       ↓                          ↓
institutional_prior          backtest.{dataset,engine,domain,
                             strategies,finmind_snapshot,finmind_history}
```

`institutional_mvp` **完全不經過** `research` 或 `prior`，而是直接接 `backtest`。從模組名稱完全看不出這件事。這才是真正的風險：未來新增法人相關功能時，開發者（或 LLM）沒有任何線索判斷該接哪一條血脈，很容易在錯誤的模組重複實作，或是接出 `prior ↔ mvp` 這種會讓兩條血脈糾纏的反向依賴。

本計畫**不做合併重構**（12,456 行、外部消費者僅 2 處，重構的風險遠大於收益）。本計畫做三件事：

1. 寫一份 ADR，把上述血脈圖、各模組的定位與淘汰條件固定下來。
2. 把血脈資訊寫進每個模組的 `__init__.py` docstring，讓讀程式的人第一眼就看到。
3. 新增一個**機器驗證的 import 邊界測試**，讓錯誤的依賴方向在 CI 就被擋下，而不是等到 code review。

---

## 2. 現況與主要缺口

### 2.1 實測依賴矩陣

以 `grep -rhoE "^(from|import) <pkg>"` 對每個模組的 `*.py` 統計得出：

| 模組 | 依賴的 institutional_* | 依賴的其他專案模組 |
|---|---|---|
| `institutional_data` | （無） | （無） |
| `institutional_research` | `institutional_data.{serialization,domain}` | `watchlist.reference_data`、`market_data.daily_kbar_qualification` |
| `institutional_prior` | `institutional_research.{domain,serialization}`、`institutional_data.serialization` | `watchlist.reference_data` |
| `institutional_mvp` | `institutional_data.serialization` | `backtest.{finmind_snapshot,strategies,finmind_history,engine,domain,dataset}` |

### 2.2 實測外部消費者（`institutional_*` 以外，排除 `tests/`、`scripts/`）

只有兩處：

| 消費者 | 消費對象 |
|---|---|
| `candidate/previous_session.py:12` | `from institutional_prior.repository import CandidatePriorRepository` |
| `config/institutional_mvp.py:9-10` | `from institutional_data.serialization import canonical_json, sha256_text`<br>`from institutional_mvp.domain import InstitutionalMvpDailyPolicy` |

### 2.3 實測測試覆蓋

| 模組 | 引用它的 `tests/*.py` 檔案數 |
|---|---:|
| `institutional_data` | 40 |
| `institutional_mvp` | 10 |
| `institutional_research` | 6 |
| `institutional_prior` | 3 |

### 2.4 P0 缺口

1. **血脈關係無任何文件記載**。四個 docstring 各自成立，但合起來讀不出「mvp 走 backtest、prior 走 research」這個關鍵事實。
2. **依賴方向無防護**。目前沒有任何機制阻止有人寫 `from institutional_mvp.domain import ...` 進 `institutional_prior`，或反向。一旦發生，兩條血脈就永久糾纏，且很難察覺。
3. **無淘汰條件**。`institutional_mvp` 的 docstring 說自己是「Non-formal」，但沒有寫「什麼條件成立時它會被正式化或廢除」。這種模組最容易變成永久存在的技術債。
4. **測試覆蓋嚴重不均**。`institutional_prior` 有 2,234 行卻只有 3 個測試檔引用，而它是**唯一被 production 決策路徑（`candidate/previous_session.py`）消費的**模組。這是覆蓋率與風險倒掛。

### 2.5 明確不是缺口

- 四個模組**共用** `institutional_data.serialization` 是好的，不是重複。
- `institutional_data` 沒有對外依賴、被 40 個測試檔覆蓋，作為 base contracts 層是健康的。

---

## 3. Scope

### 3.1 In scope

- 新增 `architecture/contracts/institutional_bounded_context.md`（ADR）。
- 更新四個 `institutional_*/__init__.py` 的 module docstring（**只改 docstring，不改任何程式碼**）。
- 新增 `tests/test_institutional_module_boundaries.py`：以 AST 靜態驗證允許的 import 方向。
- 新增 `institutional_prior` 的測試補強計畫（**只產出清單與骨架，不強制在本計畫完成全部**）。
- 在 `README.md` 的「架構原則」補一條關於 institutional 血脈的原則。

### 3.2 Non-goals

- **不合併任何模組**、不搬移檔案、不改 package 名稱。
- 不修改任何函式、類別、簽章或行為。
- 不改變 `pyproject.toml` 的 `[tool.setuptools.packages.find]` include 清單。
- 不改變任何 fail-closed 語意（`research_eligible=false`、outcome/holdout/runtime/order authorization 一律維持 false）。
- 不刪除 `institutional_mvp`，即使 ADR 判定它未來應被正式化。
- 不新增任何 provider 呼叫或資料下載。

---

## 4. 目標設計

### 4.1 ADR 必須固定的內容

`architecture/contracts/institutional_bounded_context.md` 至少包含：

1. **血脈圖**（第 1 章的 ASCII 圖，或等價的 Mermaid）。
2. **各模組定位表**：

   | 模組 | 層級 | 血脈 | 允許依賴 | 對外消費者 | 狀態 |
   |---|---|---|---|---|---|
   | `institutional_data` | Contracts (L0) | 共同 base | 無 | 全部 | `STABLE` |
   | `institutional_research` | Diagnostics (L1-A) | A | `institutional_data`、`watchlist`、`market_data` | `institutional_prior` | `EXPLORATORY` |
   | `institutional_prior` | Candidate Prior (L2-A) | A | `institutional_research`、`institutional_data`、`watchlist` | `candidate.previous_session` | `EXPLORATORY` |
   | `institutional_mvp` | MVP Evaluation (L1-B) | B | `institutional_data`、`backtest` | `config.institutional_mvp` | `NON_FORMAL` |

3. **禁止的依賴方向**（明列，作為測試的規格來源）：
   - `institutional_data` → 任何其他 `institutional_*`（base 不得反向依賴）
   - `institutional_research` → `institutional_prior`（下游不得被上游依賴）
   - `institutional_research` → `institutional_mvp`（跨血脈）
   - `institutional_prior` → `institutional_mvp`（跨血脈）
   - `institutional_mvp` → `institutional_research`（跨血脈）
   - `institutional_mvp` → `institutional_prior`（跨血脈）
   - 任何 `institutional_*` → `simulation`、`trading`、`dashboard`、`runtime`（研究模組不得碰執行層）

4. **淘汰／正式化條件**：對 `institutional_mvp` 與 `institutional_prior` 各寫明「什麼證據成立時，它會被正式化、合併或廢除」。內容應引用既有的 evidence gate（例如 `.planning/2026-08-28-institutional-research-main-merge/findings.md` 記載的「至少 60 個 overlapping target sessions」門檻），不得自行發明新門檻。

5. **新功能落點決策樹**：三個問題決定新的法人功能該放哪個模組。

### 4.2 docstring 模板

每個 `institutional_*/__init__.py` 的 docstring 改為此格式（以 `institutional_prior` 為例）：

```python
"""Exploratory institutional Candidate Prior; no trading semantics.

Layer:     L2-A (Candidate Prior)
Lineage:   A  (institutional_data -> institutional_research -> institutional_prior)
Depends:   institutional_research, institutional_data, watchlist
Consumed:  candidate.previous_session
Status:    EXPLORATORY

Lineage B (institutional_mvp) is a separate stack built on `backtest` and must
not be imported from here. See architecture/contracts/institutional_bounded_context.md.
"""
```

**限制**：只改 docstring 字串本身。不得新增 import、不得新增 `__all__`、不得改動檔案其餘任何一行。

### 4.3 邊界測試設計（`tests/test_institutional_module_boundaries.py`）

- 用 `ast.parse` 掃描每個 `institutional_*/**/*.py`，收集所有 `ast.Import` 與 `ast.ImportFrom` 的頂層 package 名稱。
- 對照 4.1 的允許清單，任何不在允許清單內的 `institutional_*` / 執行層 import 即 fail。
- 測試必須**資料驅動**：允許矩陣寫成模組層級的常數 `ALLOWED: dict[str, frozenset[str]]`，讓未來調整規則時只改一處。
- 必須包含 fail-closed 自我測試：用 `tmp_path` 建一個假的違規模組，驗證檢查函式確實回報違規（避免檢查邏輯寫錯卻永遠通過）。
- **不得** `import institutional_mvp` 等實際載入模組（那會觸發需要外部資源的初始化）；一律用 AST 靜態分析。

建議測試清單：

| 測試 | 斷言 |
|---|---|
| `test_institutional_data_has_no_institutional_dependencies` | `institutional_data` 不 import 任何其他 `institutional_*` |
| `test_lineage_a_and_b_do_not_cross` | `research`/`prior` 不 import `mvp`；`mvp` 不 import `research`/`prior` |
| `test_no_institutional_module_imports_execution_layer` | 四個模組都不 import `simulation`/`trading`/`dashboard`/`runtime`（已實測：目前為 0 筆違規，本測試是防止未來回歸） |
| `test_declared_consumers_match_actual_imports` | 專案內（排除 `tests/`、`scripts/`）實際消費 `institutional_*` 的檔案，恰好等於 ADR 表格宣告的那兩個 |
| `test_every_institutional_init_declares_layer_and_lineage` | 四個 `__init__.py` 的 docstring 都含 `Layer:`、`Lineage:`、`Status:` 三個欄位 |
| `test_boundary_checker_rejects_synthetic_violation` | fail-closed 自我測試 |

其中 `test_declared_consumers_match_actual_imports` 特別重要：它會在有人新增第三個消費者時強制更新 ADR，讓文件不會再度腐化。

---

## 5. 實作階段

### Phase 1 — 依賴圖重新量測與凍結

1. 撰寫 `scripts/report_institutional_dependencies.py`（純 AST，標準函式庫）：
   - 輸出每個 `institutional_*` 模組的實際 import 集合；
   - 輸出全專案對 `institutional_*` 的消費者清單（分為 `production` / `tests` / `scripts` 三類）。
2. 執行並將結果存為 `research/institutional_dependency_map_2026-08-28.md`。
3. **與本文件第 2 章的實測數字比對**。若有任何不符，停止並回報差異——代表 snapshot 已改變，ADR 的內容需要先修正。

**Acceptance**：報告產出；四個模組的依賴集合與第 2.1 節一致；production 消費者恰為 `candidate/previous_session.py` 與 `config/institutional_mvp.py` 兩處。

**Status**：`NOT_STARTED`

### Phase 2 — 撰寫 ADR

依 4.1 撰寫 `architecture/contracts/institutional_bounded_context.md`。

**淘汰條件的取材限制**：必須引用既有規劃文件中已凍結的 gate，並標註出處檔案路徑。禁止自創新門檻。建議先閱讀：

- `.planning/2026-08-28-institutional-research-main-merge/findings.md`
- `.planning/2026-08-20-pr005-institutional-candidate-prior/`
- `architecture/institutional_premarket_candidate_implementation_plan.md`
- `architecture/institutional_source_coverage.md`

**Acceptance**：ADR 含 4.1 的五個章節；每個淘汰條件都標註來源檔案路徑；禁止依賴清單與 Phase 1 的實測結果無矛盾。

**Status**：`NOT_STARTED`

### Phase 3 — 更新四個 docstring

依 4.2 模板更新。

**Acceptance**：`git diff --stat` 顯示恰好 4 個檔案變更，且每個檔案的 diff **只包含 docstring 區塊**；`python -m compileall -q institutional_data institutional_research institutional_prior institutional_mvp` 通過；`python -m pytest tests/ -q` 相對基線無新增失敗。

**Status**：`NOT_STARTED`

### Phase 4 — 邊界測試

依 4.3 實作 `tests/test_institutional_module_boundaries.py`。

**Acceptance**：`python -m pytest tests/test_institutional_module_boundaries.py -q` 全綠且含 6 個以上測試；其中至少 1 個是 fail-closed 自我測試；測試檔完全不 import 任何 `institutional_*` 模組本體（用 `grep -n "^from institutional\|^import institutional" tests/test_institutional_module_boundaries.py` 驗證應無輸出，只允許出現在字串常數中）。

**Status**：`NOT_STARTED`

### Phase 5 — `institutional_prior` 測試缺口清單

`institutional_prior` 有 2,234 行、是唯一進 production 決策路徑的模組，卻只有 3 個測試檔引用。本階段**只產出清單，不實作測試**：

1. 列出 `institutional_prior/*.py` 每個 public 函式／類別，標記是否已被現有測試觸及。
2. 依「是否在 `CandidatePriorRepository` 的呼叫路徑上」排序風險。
3. 輸出 `research/institutional_prior_test_gap_2026-08-28.md`，並開一張後續票。

**Acceptance**：清單涵蓋 `institutional_prior` 全部 public surface；高風險項目（在 production 呼叫路徑上且無測試）已明確標示。

**Status**：`NOT_STARTED`

### Phase 6 — README 架構原則補充

在 `README.md` 的「架構原則」清單末尾新增一條：

```markdown
8. `institutional_*` 分為兩條互不交叉的血脈：A（`data → research → prior`，供 Candidate Prior）與 B（`data → mvp → backtest`，供 MVP 評估）。跨血脈 import 由 `tests/test_institutional_module_boundaries.py` 擋下；定位與淘汰條件見 `architecture/contracts/institutional_bounded_context.md`。
```

**Acceptance**：README 該節從 7 條變 8 條，格式與既有條目一致。

**Status**：`NOT_STARTED`

---

## 6. 驗收條件（總）

1. `python -m pytest tests/test_institutional_module_boundaries.py -q` 全綠。
2. `python -m pytest tests/ -q` 相對於本計畫開始前**無新增失敗**（既有的 r2 price-coverage 失敗歸 `PCD-001`）。
3. `python -m compileall -q institutional_data institutional_research institutional_prior institutional_mvp` 通過。
4. `git diff` 對四個 `institutional_*` 套件的變更**僅限 `__init__.py` 的 docstring**——這點必須由 reviewer 逐行確認。
5. ADR 的禁止依賴清單與 `tests/test_institutional_module_boundaries.py` 的 `ALLOWED` 常數**語意一致**（reviewer 交叉比對）。
6. 四份研究／文件交付物齊備。

---

## 7. 風險

| 風險 | 等級 | 緩解 |
|---|---|---|
| 執行者把「收斂」理解為「合併模組」，動了程式碼 | **高** | Non-goals 與 Phase 3 acceptance 都明訂只改 docstring；驗收條件 4 要求逐行確認 diff |
| 邊界測試把既有合法 import 誤判為違規，CI 立刻紅 | 中 | Phase 1 先量測實際依賴，`ALLOWED` 直接由實測結果建構；先跑一次確認當前 repo 通過 |
| ADR 自創淘汰門檻，與既有已凍結的 evidence gate 衝突 | 中 | Phase 2 明訂必須引用既有文件並標註出處，禁止自創 |
| 測試中誤 import `institutional_mvp` 觸發外部資源初始化 | 中 | 4.3 明訂只用 AST；Phase 4 acceptance 有 grep 驗證 |
| 消費者比對測試過於嚴格，日後每次新增消費者都紅燈 | 低 | 這是刻意設計——強制同步更新 ADR。ADR 中須說明此意圖 |

---

## 8. 交付物

1. `architecture/contracts/institutional_bounded_context.md`（ADR）
2. `scripts/report_institutional_dependencies.py`
3. `research/institutional_dependency_map_2026-08-28.md`
4. `research/institutional_prior_test_gap_2026-08-28.md`
5. `tests/test_institutional_module_boundaries.py`
6. 四個 `institutional_*/__init__.py` 的 docstring 更新
7. `README.md` 架構原則第 8 條
