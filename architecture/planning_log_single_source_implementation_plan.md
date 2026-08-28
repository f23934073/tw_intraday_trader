# 規劃文件單一真相來源 Implementation Plan

## 0. 文件狀態

- 狀態：`PLAN_ONLY / NOT_IMPLEMENTED`
- Source snapshot：`main@d0e271e0a247c669adae23423244de0cc7200832`
- 規劃日期：`2026-08-28`
- 計畫代號：`DOC-001`
- 預估工期：2～3 個開發日
- 安全邊界：只動 Markdown、`.planning/` 結構與一支新的檢查腳本。**不得修改任何 production Python 模組**，不得改變 `WORKFLOW.md` 所定義的 ticket 流程語意。

### 0.1 執行環境假設（交付給外部 LLM 時必讀）

- 可執行 `python -m pip install -e ".[dev]"` 與 `python -m pytest`（預設 `MockProvider`）。
- **沒有** Shioaji 金鑰、**沒有** PostgreSQL、**不可**連真實行情。本計畫的所有驗收都不需要這些資源。
- 本計畫產出的檢查腳本必須是純標準函式庫（`pathlib` / `json` / `re`），不得引入新依賴。

---

## 1. 結論先講

專案目前有**兩套並存但沒有定義關係**的規劃紀錄：

- 根目錄的 `findings.md`（999 行 / 133 KB）、`progress.md`（1,181 行 / 113 KB）、`task_plan.md`（414 行）；
- `.planning/` 底下 74 個 ticket 資料夾，每個各有同名的 `findings.md` / `progress.md` / `task_plan.md`（共 191 個 tracked 檔案）。

實測已證明兩者**已經失去同步**：`.planning/.active_plan` 指向 `2026-08-27-trading-session-slippage-no-overnight-re`，根 `progress.md` 的最新章節是 `Session: 2026-08-27 — Phase 17`，但根 `task_plan.md` 的 `Current Phase` 仍寫著 `Phase 13 — Freshness Calibration Evidence`，而它的 `Goal` 描述的是 premarket watchlist——與現在進行中的工作完全無關。

也就是說，「現在的狀態該看哪一份」目前**沒有正確答案**。

本計畫完成後：

1. 根目錄三件套與 `.planning/<ticket>/` 三件套的角色由一份 `.planning/README.md` 明確定義，並在 `WORKFLOW.md` 引用。
2. 已 stale 的根 `task_plan.md` 被廢除（其職責完全由 `.planning/<active>/task_plan.md` 承擔）。
3. 根 `findings.md` / `progress.md` 明確定位為「PM 跨 ticket 全域日誌」，並導入**季度歸檔**，讓單一檔案不再無限成長。
4. 新增 `scripts/check_planning_consistency.py` 並掛進 CI，讓上述約定變成**機器可驗證**的規則，而不是靠人記得。

---

## 2. 現況與主要缺口

### 2.1 現況實測

| 檔案 / 目錄 | 行數 | 大小 | 角色（推定） |
|---|---:|---:|---|
| `findings.md` | 999 | 133 KB | PM 全域決策與發現，append-only，跨多個 session |
| `progress.md` | 1,181 | 113 KB | PM 全域進度日誌，以 `## Session: <date>` 分章 |
| `task_plan.md` | 414 | 43 KB | **已 stale**，內容停在 Phase 13 |
| `.planning/` | — | — | 74 個 ticket 資料夾，191 tracked 檔 |
| `.planning/.active_plan` | 1 | — | 純文字，內容為當前 ticket 資料夾名 |
| `.planning/<ticket>/` | — | — | 每個含 `findings.md` / `progress.md` / `task_plan.md` |

### 2.2 P0 缺口

1. **角色未定義**：沒有任何文件說明根目錄三件套與 `.planning/<ticket>/` 三件套的關係。新加入者（人或 LLM）無法判斷該讀哪份、該寫哪份。
2. **根 `task_plan.md` 已 stale 且與 `.active_plan` 直接矛盾**：
   - `.planning/.active_plan` → `2026-08-27-trading-session-slippage-no-overnight-re`
   - 根 `task_plan.md` `Current Phase` → `Phase 13 — Freshness Calibration Evidence`
   - 根 `task_plan.md` `Goal` → 「next-session premarket watchlists」
   - 根 `progress.md` 最新 → `Phase 17`

   四者互不相符。這是最直接的證據：根 `task_plan.md` 已無人維護。
3. **無成長上限**：根 `findings.md` 與 `progress.md` 是 append-only 且已達 133 KB / 113 KB。它們每個 session 都被讀進 LLM context，成本隨時間線性上升，而且舊內容（例如 2026-08-20 的 PR006 細節）對現在的工作沒有幫助。
4. **無一致性檢查**：`.active_plan` 可以指向不存在的資料夾、ticket 資料夾可以缺三件套之一，目前 CI 都不會發現。

### 2.3 明確不是缺口

- `.planning/<ticket>/` 每個 ticket 各有三件套**是正確設計**（對應 `WORKFLOW.md` 的 Workpad 模板），本計畫不改變它。
- 74 個歷史 ticket 資料夾**不刪除**。它們是稽核軌跡。

---

## 3. Scope

### 3.1 In scope

- 新增 `.planning/README.md`：定義兩層規劃文件的角色、寫入規則、歸檔規則。
- 廢除根 `task_plan.md`（移入歸檔，不刪除內容）。
- 根 `findings.md` / `progress.md` 加入標頭區塊，明示角色、涵蓋範圍與歸檔政策。
- 建立 `.planning/_archive/` 並將 2026-08-25 之前的根日誌內容切分歸檔。
- 新增 `scripts/check_planning_consistency.py` 與 `tests/test_planning_consistency.py`。
- 在 `.github/workflows/ci.yml` 加入一個檢查步驟。
- 在 `WORKFLOW.md` 加入指向 `.planning/README.md` 的段落。

### 3.2 Non-goals

- **不刪除任何歷史內容**。歸檔＝搬移到 `.planning/_archive/`，不是刪除。
- 不修改 74 個既有 ticket 資料夾裡的任何內容。
- 不改變 `WORKFLOW.md` 既有的 status map、Step 0～4 流程、guardrails 語意；只新增一段交叉引用。
- 不引入外部文件系統（Notion、Linear 以外的工具）。
- 不自動化 ticket 建立；`.planning/<ticket>/` 仍由既有流程手動建立。

---

## 4. 目標設計

### 4.1 兩層角色定義（寫入 `.planning/README.md`）

| 層級 | 位置 | 角色 | 寫入時機 | 生命週期 |
|---|---|---|---|---|
| **全域層** | `findings.md`、`progress.md` | 跨 ticket 的 PM 決策與 session 進度。回答「這個專案整體現在到哪、為什麼這樣決定」 | 每個 PM session 結束時 | 季度歸檔至 `.planning/_archive/` |
| **Ticket 層** | `.planning/<ticket>/{findings,progress,task_plan}.md` | 單一 ticket 的完整工作區。回答「這張票要做什麼、做到哪、學到什麼」 | ticket 執行期間持續 | 永久保留，ticket 關閉後不再修改 |
| **指標** | `.planning/.active_plan` | 單行純文字，指向當前 active 的 ticket 資料夾名 | ticket 切換時 | 永遠只有一行 |

**關鍵規則**：

1. 「現在正在做什麼」的唯一真相來源是 `.planning/.active_plan` 指向的資料夾裡的 `task_plan.md`。根目錄**不再有** `task_plan.md`。
2. 根 `progress.md` 只寫 session 層級的摘要與跨 ticket 協調，**不重複** ticket 內的逐步細節。
3. 根 `findings.md` 只寫會影響**未來其他 ticket** 的決策；只影響單一 ticket 的發現留在該 ticket 資料夾。

### 4.2 歸檔規則

- 根 `findings.md` / `progress.md` 以 `## Session: <YYYY-MM-DD>` 或 `## <YYYY-MM-DD> — <title>` 為切分單位。
- 每季（或當單檔超過 **1,500 行**）將最舊的章節搬到 `.planning/_archive/findings_<YYYY>Q<N>.md` 與 `progress_<YYYY>Q<N>.md`。
- 歸檔檔案開頭必須有一行 `> Archived from findings.md on <date>. Covers <first-date> .. <last-date>.`
- 主檔結尾保留一行索引：`> Earlier sessions: see .planning/_archive/`。

### 4.3 一致性檢查規則（`scripts/check_planning_consistency.py`）

腳本必須以 exit code 0/1 表示通過與否，並印出可讀的錯誤清單。檢查項目：

| 編號 | 規則 | 失敗訊息 |
|---|---|---|
| `PC001` | `.planning/.active_plan` 存在、恰好一行非空白內容 | `active_plan pointer is missing or malformed` |
| `PC002` | `.active_plan` 指向的資料夾存在於 `.planning/` 下 | `active_plan points to non-existent ticket: <name>` |
| `PC003` | active ticket 資料夾含 `task_plan.md`、`findings.md`、`progress.md` | `active ticket is missing <file>` |
| `PC004` | 專案根目錄**不存在** `task_plan.md` | `root task_plan.md is deprecated; use .planning/<active>/task_plan.md` |
| `PC005` | 根 `findings.md` 與 `progress.md` 各不超過 1,500 行 | `<file> exceeds 1500 lines; archive older sessions to .planning/_archive/` |
| `PC006` | 根 `findings.md` 與 `progress.md` 開頭 10 行內含 `<!-- planning-scope: global -->` 標記 | `<file> is missing its planning-scope header` |
| `PC007` | `.planning/` 下每個非 `_` 開頭的資料夾都含三件套（僅 WARN，不 fail） | `ticket <name> is missing <file>` |

`PC007` 設為 warning 是因為 74 個歷史資料夾可能有例外；執行者應先跑一次記錄實際 warning 數，寫進 plan 的 Phase 1 結果。

---

## 5. 實作階段

### Phase 1 — 現況盤點與規則驗證

1. 統計 `.planning/` 下所有資料夾，列出缺三件套的資料夾清單。
2. 解析根 `findings.md` / `progress.md` 的章節切分點，輸出 `(章節標題, 起始行, 結束行, 日期)` 清單。
3. 產出 `research/planning_docs_inventory_2026-08-28.md` 記錄上述兩項。
4. 確認 `PC007` 的實際 warning 數量，若超過 10 個則在文件中記錄，並維持 warning 等級。

**Acceptance**：inventory 文件存在；章節切分清單涵蓋兩個根檔案的 100% 行數（無遺漏區間）。

**Status**：`NOT_STARTED`

### Phase 2 — 建立 `.planning/README.md`

依 4.1 與 4.2 撰寫，內容必須包含：

- 兩層角色表；
- 「現在正在做什麼」的單一真相來源宣告；
- 歸檔規則與門檻；
- `scripts/check_planning_consistency.py` 的用法；
- 一段「給 LLM 協作者的指示」：明確說明開始工作前該讀哪幾份、依什麼順序。

**Acceptance**：`.planning/README.md` 存在；`WORKFLOW.md` 新增一段連結到它（放在 `## Default posture` 之後）。

**Status**：`NOT_STARTED`

### Phase 3 — 廢除根 `task_plan.md`

1. 將現有 `task_plan.md` 完整搬到 `.planning/_archive/task_plan_deprecated_2026-08-28.md`。
2. 在該歸檔檔開頭加入：

   ```markdown
   > Deprecated on 2026-08-28. This file's `Current Phase` (Phase 13) had drifted
   > from `.planning/.active_plan` and `progress.md` (Phase 17). Per DOC-001, the
   > single source of truth for the active plan is
   > `.planning/<active_plan>/task_plan.md`.
   ```

3. 刪除根目錄的 `task_plan.md`。
4. 全專案搜尋對 `task_plan.md` 的引用（`WORKFLOW.md`、`.planning/*/`、`README.md`），確認沒有指向根目錄那份的路徑；有的話改寫為相對於 ticket 的路徑。

**Acceptance**：根目錄無 `task_plan.md`；`grep -rn "^task_plan.md\|/task_plan.md" --include="*.md" .` 的結果都指向 `.planning/` 底下。

**Status**：`NOT_STARTED`

### Phase 4 — 加標頭與首次歸檔

1. 在根 `findings.md` 與 `progress.md` 最前面加入：

   ```markdown
   <!-- planning-scope: global -->
   > 全域 PM 日誌。單一 ticket 的細節請見 `.planning/<ticket>/`。
   > 規則見 `.planning/README.md`。較早的 session 見 `.planning/_archive/`。
   ```

2. 依 Phase 1 的章節清單，把 **2026-08-25 之前**的章節搬到：
   - `.planning/_archive/findings_2026Q3_part1.md`
   - `.planning/_archive/progress_2026Q3_part1.md`
3. 確認搬移後兩個主檔都 < 1,500 行。
4. 驗證搬移無內容遺失：

   ```bash
   # 行數守恆檢查（扣掉新增的標頭與索引行）
   wc -l findings.md .planning/_archive/findings_2026Q3_part1.md
   ```

**Acceptance**：`findings.md` + 歸檔檔的總行數 ≥ 原始 999 行；`progress.md` + 歸檔檔 ≥ 原始 1,181 行；兩個主檔各 < 1,500 行；無任何章節同時出現在主檔與歸檔檔（用章節標題比對）。

**Status**：`NOT_STARTED`

### Phase 5 — 檢查腳本與測試

1. 實作 `scripts/check_planning_consistency.py`：
   - 只用標準函式庫；
   - `python scripts/check_planning_consistency.py` → exit 0 通過、exit 1 失敗；
   - `--warn-only` 旗標讓 `PC007` 以外的規則也降級為 warning（供本機探索用）；
   - 錯誤輸出格式：`<RULE_ID>: <message>`。
2. 實作 `tests/test_planning_consistency.py`：
   - 對**當前 repo** 跑一次，斷言 exit 0；
   - 用 `tmp_path` 建構人工違規情境，逐一驗證 `PC001`～`PC006` 都會被抓到（至少 6 個 fail-closed 測試）；
   - 驗證 `PC007` 只產生 warning、不影響 exit code。

**Acceptance**：`python -m pytest tests/test_planning_consistency.py -q` 全綠；`python scripts/check_planning_consistency.py` exit 0。

**Status**：`NOT_STARTED`

### Phase 6 — 掛進 CI

在 `.github/workflows/ci.yml` 的 `test` job 中，`Check dashboard JavaScript syntax` 之後、`Run tests` 之前插入：

```yaml
      - name: Check planning document consistency
        run: python scripts/check_planning_consistency.py
```

**Acceptance**：CI 設定檔語法正確（`python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/ci.yml'))"`）；步驟名稱與既有風格一致。

**Status**：`NOT_STARTED`

---

## 6. 驗收條件（總）

1. `python scripts/check_planning_consistency.py` exit 0。
2. `python -m pytest tests/test_planning_consistency.py -q` 全綠，且包含至少 6 個 fail-closed 案例。
3. 根目錄無 `task_plan.md`。
4. 根 `findings.md`、`progress.md` 各 < 1,500 行且含 `planning-scope` 標頭。
5. 歸檔前後行數守恆（無內容遺失）。
6. `.planning/README.md` 與 `WORKFLOW.md` 的交叉引用雙向可達。
7. `python -m pytest tests/ -q` 相對於本計畫開始前**沒有新增任何失敗**（既有的 r2 price-coverage 失敗由 `PCD-001` 處理，不在此計畫範圍）。

---

## 7. 風險

| 風險 | 等級 | 緩解 |
|---|---|---|
| 歸檔時切錯章節邊界，內容遺失 | **高** | Phase 4 明訂行數守恆驗證；先在 git 已提交的狀態下操作，隨時可 `git checkout` 還原 |
| 廢除根 `task_plan.md` 後，某個既有流程或腳本讀不到它 | 中 | Phase 3 明訂全專案 grep；內容搬到 `_archive/` 而非刪除 |
| `PC005` 的 1,500 行門檻太緊，導致 CI 常態性紅燈 | 中 | 門檻寫成腳本常數並在 `.planning/README.md` 記錄；首次歸檔後應有充足餘裕，實測後可調整 |
| 74 個歷史 ticket 有大量缺件，`PC007` 噪音過大 | 低 | `PC007` 設計為 warning-only；Phase 1 先量測實際數量 |
| CI 新步驟拖慢流程 | 低 | 純檔案檢查，預期 < 1 秒 |

---

## 8. 交付物

1. `.planning/README.md`
2. `.planning/_archive/`（含 `task_plan_deprecated_2026-08-28.md`、`findings_2026Q3_part1.md`、`progress_2026Q3_part1.md`）
3. `scripts/check_planning_consistency.py`
4. `tests/test_planning_consistency.py`
5. `research/planning_docs_inventory_2026-08-28.md`
6. `findings.md`、`progress.md` 標頭更新；根 `task_plan.md` 移除
7. `WORKFLOW.md` 交叉引用段落
8. `.github/workflows/ci.yml` 新增檢查步驟
