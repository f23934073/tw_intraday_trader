# r2 Price-Coverage Source-Digest Drift 修復 Implementation Plan

## 0. 文件狀態

- 狀態：`PLAN_ONLY / NOT_IMPLEMENTED`
- Source snapshot：`main@d0e271e0a247c669adae23423244de0cc7200832`
- 規劃日期：`2026-08-28`
- 計畫代號：`PCD-001`
- 預估工期：1～1.5 個開發日，另加 0.5 日獨立 review
- 安全邊界：**不得修改任何 immutable artifact**（`research/institutional_evaluation/acquisition/` 底下的 `.json` 與 `.canonical.sha256` 一律唯讀）。不得修改 `backtest/historical_download.py` 或 `scripts/download_backtest_history.py`。不得執行任何下載、provider 呼叫或 coverage scan。

### 0.1 執行環境假設（交付給外部 LLM 時必讀）

- 可執行 `python -m pip install -e ".[dev]"` 與 `python -m pytest`（預設 `MockProvider`）。
- **沒有** Shioaji 金鑰、**沒有** PostgreSQL、**不可**連真實行情。本計畫的驗收完全不需要這些資源——目標測試是純檔案／雜湊比對。
- 本計畫的所有驗收都能在 sandbox 完整完成，是五份計畫中最適合外部獨立交付的一份。

---

## 1. 結論先講

專案有一個**長期存在的紅燈測試**，橫跨至少三張票被記錄為「與本次改動無關」而放行：

- `.planning/2026-08-26-pr-tm-012c1-external-runner-draft/progress.md:37` — 「failure isolated to pre-existing price-coverage digest drift outside this scope」
- `.planning/2026-08-28-institutional-research-main-merge/findings.md:11` — 「the sole r2 price-coverage source-digest drift reproduces unchanged on parent `main@a6e096a`」
- `.planning/2026-08-28-institutional-research-main-merge/progress.md:13` — 「`1721 passed, 86 skipped, 1 failed`」

**根因已完全確認**，不需要再調查：

immutable artifact `research/institutional_evaluation/acquisition/price_coverage_scan_configuration_v1_2026-08-21-r2.json` 在 2026-08-21 凍結時，把兩個**當時的 live 原始碼檔案 SHA-256** 寫進了 `scan_configuration`：

| 欄位 | artifact 凍結值 | 檔案現值（`d0e271e`） |
|---|---|---|
| `historical_downloader_source_sha256` | `e194610613f9094e8d610a5ccd2f0843ef6ff59dffeaa803e7cfe3913fc7f036` | `7abd3d3ba479907e836277294272733178b634c05ca598e8e7b4ffa3843d21c9` |
| `cli_source_sha256` | `5950bd1d5117f85c2412a316ab46fe83a2f9579a729b82baff4642d885fce675` | `9f1a3fadf0ba195b62ea9d82ab045e7ec7464ea256b4bd3db8edc8f30bfb61f6` |

而測試 `tests/test_price_coverage_scan_segment_manifest.py::test_r2_configuration_is_frozen_before_resume_and_pins_new_taxonomy` 用一個 helper `_source_sha256()` **在測試執行當下重算 live 檔案的 SHA**，再與 artifact 的凍結值比對。

那兩個原始碼檔案在 2026-08-21 之後被合法修改過，來自兩個 commit：

- `f751843` — `feat(research): gate r3 price coverage activation`
- `1d9d014` — `feat(backtest): add atomic strategy persistence platform`

因此這個測試從那一刻起就**必然永久失敗**，而且會隨著這兩個檔案的每一次正常演進持續失敗。這不是偶發、不是環境問題，是設計上的必然。

**同時要注意**：目前工作目錄裡已經有人動手改過這個測試（`git diff --stat` 顯示 4 insertions / 9 deletions），做法是把 `_source_sha256()` 刪掉、改成硬編碼兩個常數字串。**這個改法會讓斷言變成恆真**——它只驗證「artifact 的欄位等於一個常數」，而那個常數就是從 artifact 抄來的，等於什麼都沒驗證。原本這個測試存在的意義（drift gate）會被完全掏空。本計畫的核心價值就在於用一個既能綠燈、又真的保留 gate 的方案取代它。

---

## 2. 現況與主要缺口

### 2.1 涉及檔案

| 檔案 | 角色 | 本計畫可否修改 |
|---|---|---|
| `tests/test_price_coverage_scan_segment_manifest.py` | 失敗的測試 | **是**（唯一允許改的既有檔） |
| `research/.../price_coverage_scan_configuration_v1_2026-08-21-r2.json` | immutable artifact，3,680 bytes | **否** |
| `research/.../price_coverage_scan_configuration_v1_2026-08-21-r2.canonical.sha256` | canonical digest sidecar，65 bytes | **否** |
| `backtest/historical_download.py` | 被 pin 的原始碼 | **否** |
| `scripts/download_backtest_history.py` | 被 pin 的原始碼 | **否** |

### 2.2 測試現況（`main@d0e271e` 已提交版本）

```python
def _source_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

# ...
    assert scan["historical_downloader_source_sha256"] == _source_sha256(
        ROOT / "backtest/historical_download.py"
    )
    assert scan["cli_source_sha256"] == _source_sha256(
        ROOT / "scripts/download_backtest_history.py"
    )
```

### 2.3 工作目錄中已存在的未提交改法（**本計畫不採用**）

```python
    assert scan["historical_downloader_source_sha256"] == (
        "e194610613f9094e8d610a5ccd2f0843ef6ff59dffeaa803e7cfe3913fc7f036"
    )
    assert scan["cli_source_sha256"] == (
        "5950bd1d5117f85c2412a316ab46fe83a2f9579a729b82baff4642d885fce675"
    )
```

### 2.4 P0 缺口

1. **測試把「不可變的凍結值」與「會變動的 live 檔案」綁在一起**。artifact 是 immutable、原始碼是 mutable，兩者不可能長期相等。這是契約設計錯誤，不是測試錯誤。
2. **長期紅燈已造成組織性麻木**。至少三張票把它記為「與我無關」放行。再過幾張票，就沒有人記得為什麼它是紅的，也就無法分辨新的迴歸。
3. **沒有任何地方記錄這個 drift 是「已知且已審核」的**。artifact 的 pin 值與現況的差異目前只存在於 planning 筆記的一句話裡，沒有結構化、可驗證的紀錄。

---

## 3. Scope

### 3.1 In scope

- 重新設計 `test_r2_configuration_is_frozen_before_resume_and_pins_new_taxonomy` 的斷言語意。
- 新增一份 **source drift acknowledgement** 紀錄檔，把「pin 值 vs 現值 vs 造成差異的 commit vs 為什麼可接受」結構化保存。
- 新增針對 acknowledgement 的 fail-closed 測試。
- 在 `.planning/` 與 `progress.md` 記錄此長期紅燈已關閉。

### 3.2 Non-goals

- **不修改 immutable artifact 或其 `.canonical.sha256` sidecar**。
- 不修改 `backtest/historical_download.py`、`scripts/download_backtest_history.py`。
- 不重新產生 r2 artifact、不建立 r3 artifact。
- 不執行任何 coverage scan、下載或 provider 呼叫。
- 不改動同目錄其他 price-coverage 測試（`test_price_coverage_audit_contract.py`、`test_price_coverage_r3_activation.py` 等七個檔案）。
- 不採用 2.3 節那個硬編碼恆真的改法。

---

## 4. 方案比較與選定

| 方案 | 做法 | 綠燈 | 保留 gate | 評價 |
|---|---|:--:|:--:|---|
| A | 硬編碼凍結常數（工作目錄現行改法） | ✅ | ❌ | 斷言恆真，gate 被掏空 |
| B | 刪除這兩行斷言 | ✅ | ❌ | 誠實但直接放棄證據 |
| C | 重算 live SHA 並更新 artifact | ✅ | ⚠️ | **違反 immutable 契約**，不可接受 |
| **D（選定）** | 拆成兩個斷言：artifact 完整性 + 已審核的 drift 紀錄 | ✅ | ✅ | 綠燈且 gate 更強 |

### 4.1 方案 D 設計

把原本混在一起的兩件事拆開：

**斷言 1 — artifact 完整性（不變性）**

artifact 的欄位值必須等於凍結常數。這件事**已經**被同一個測試檔既有的 `sha256_text(canonical_json(r2)) == _digest(R2)` 涵蓋（canonical digest 比對），所以這裡只需保留欄位存在性與型別檢查，避免重複。

**斷言 2 — source drift 必須被明確審核**

新增紀錄檔 `research/institutional_evaluation/acquisition/price_coverage_source_drift_acknowledgement_v1.json`，結構如下：

```json
{
  "artifact_id": "price-coverage-source-drift-acknowledgement-v1",
  "acknowledged_on": "2026-08-28",
  "pinned_configuration": {
    "artifact_path": "research/institutional_evaluation/acquisition/price_coverage_scan_configuration_v1_2026-08-21-r2.json",
    "artifact_canonical_sha256": "<從 .canonical.sha256 sidecar 讀取，執行時填入>"
  },
  "pinned_sources": [
    {
      "path": "backtest/historical_download.py",
      "pinned_sha256": "e194610613f9094e8d610a5ccd2f0843ef6ff59dffeaa803e7cfe3913fc7f036",
      "observed_sha256_at_acknowledgement": "7abd3d3ba479907e836277294272733178b634c05ca598e8e7b4ffa3843d21c9",
      "drift_status": "ACKNOWLEDGED_POST_FREEZE_EVOLUTION",
      "causing_commits": ["f751843", "1d9d014"],
      "rationale": "r2 是 2026-08-21 凍結的一次性 scan 設定；其 pin 記錄的是當時執行 scan 的原始碼身分，不是對未來原始碼的約束。此後的合法演進不使 r2 失效，也不改變已產生的 coverage 觀測。"
    },
    {
      "path": "scripts/download_backtest_history.py",
      "pinned_sha256": "5950bd1d5117f85c2412a316ab46fe83a2f9579a729b82baff4642d885fce675",
      "observed_sha256_at_acknowledgement": "9f1a3fadf0ba195b62ea9d82ab045e7ec7464ea256b4bd3db8edc8f30bfb61f6",
      "drift_status": "ACKNOWLEDGED_POST_FREEZE_EVOLUTION",
      "causing_commits": ["f751843", "1d9d014"],
      "rationale": "同上。"
    }
  ],
  "reuse_constraint": "任何重新執行、續跑或延伸此 r2 coverage scan 的行為，必須先重新凍結一份新的 scan configuration（r3 或更新），不得沿用 r2 的 pin 宣稱原始碼身分。"
}
```

同時產生 `price_coverage_source_drift_acknowledgement_v1.canonical.sha256`，格式與同目錄其他 sidecar 一致（用 `institutional_data.serialization.canonical_json` + `sha256_text`）。

**新的測試語意**：

```text
對每個 pinned source：
  live_sha = sha256(檔案現值)
  若 live_sha == artifact 的 pin 值：
      → 通過（沒有 drift）
  否則：
      → acknowledgement 檔中必須存在該路徑的條目，
        且其 pinned_sha256 == artifact 的 pin 值，
        且其 observed_sha256_at_acknowledgement == live_sha，
        且 drift_status == "ACKNOWLEDGED_POST_FREEZE_EVOLUTION"
      → 否則 fail，訊息指出「原始碼有未審核的 drift，請更新 acknowledgement」
```

這樣一來：

- 現在是綠的（因為 drift 已被記錄且 observed 值相符）；
- **如果那兩個檔案再被改動**，`observed_sha256_at_acknowledgement` 就不再相符 → **重新變紅**，強迫開發者重新審核並更新紀錄。gate 不但保住，還比原本更明確。
- 如果有人竄改 artifact 的 pin 值，既有的 canonical digest 斷言會抓到。

### 4.2 為什麼不用「直接刪掉斷言」

因為 `reuse_constraint` 這件事是真的重要：如果未來有人想續跑這個 coverage scan，他必須知道 r2 的 pin 已經不代表當前原始碼。方案 D 把這個知識變成了一個**會在 CI 提醒你**的機制，而不是一句沒人會讀到的 planning 筆記。

---

## 5. 實作階段

### Phase 0 — 前置：處理工作目錄的既有改動

`tests/test_price_coverage_scan_segment_manifest.py` 目前在工作目錄有未提交的改動（方案 A 的硬編碼版本）。本計畫**不沿用**它。

```bash
# 先確認 diff 內容與本文件 2.3 節一致
git diff tests/test_price_coverage_scan_segment_manifest.py

# 確認一致後，還原到 main@d0e271e 的版本，從乾淨的起點開始
git checkout -- tests/test_price_coverage_scan_segment_manifest.py
```

**若 diff 與 2.3 節不符**：停止並回報，代表有人做了本計畫未預期的修改。

**Acceptance**：`git diff tests/test_price_coverage_scan_segment_manifest.py` 無輸出；`hashlib` import 與 `_source_sha256` helper 回到檔案中。

**Status**：`NOT_STARTED`

### Phase 1 — 重現失敗並凍結證據

```bash
python -m pytest tests/test_price_coverage_scan_segment_manifest.py -q
```

預期：`test_r2_configuration_is_frozen_before_resume_and_pins_new_taxonomy` FAILED，其餘通過。

記錄：

1. 完整失敗輸出。
2. 兩個 live 檔案的實際 SHA：

   ```bash
   python -c "import hashlib,pathlib; [print(p, hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()) for p in ['backtest/historical_download.py','scripts/download_backtest_history.py']]"
   ```

3. 造成變動的 commit：

   ```bash
   git log --oneline --since=2026-08-21 -- backtest/historical_download.py scripts/download_backtest_history.py
   ```

**Acceptance**：實測 SHA 與本文件第 1 章表格完全一致；commit 清單含 `f751843` 與 `1d9d014`。**若不一致，停止並回報**——代表 snapshot 已改變，acknowledgement 的 observed 值必須用實測值而非本文件的值。

**Status**：`NOT_STARTED`

### Phase 2 — 建立 acknowledgement artifact

1. 撰寫 `scripts/build_price_coverage_source_drift_acknowledgement.py`：
   - 讀 r2 artifact 取得兩個 pin 值；
   - 讀 r2 的 `.canonical.sha256` sidecar；
   - 計算兩個 live 檔案的 SHA；
   - **只有在 live SHA 與 pin 值不同時**才寫入該條目（相同就不需要 acknowledge）；
   - `causing_commits` 由 `git log --since=<r2 凍結日> -- <path>` 推導，不得硬編碼；
   - 用 `institutional_data.serialization.canonical_json` 序列化並用 `sha256_text` 產生 sidecar；
   - 支援 `--check` 模式：不寫檔，只驗證既有 acknowledgement 是否仍與現況相符（供 CI 或人工使用）。
2. 執行產生兩個檔案。

**Acceptance**：兩個檔案存在；`sha256_text(canonical_json(載入的 json))` 等於 sidecar 內容；`--check` 模式 exit 0。

**Status**：`NOT_STARTED`

### Phase 3 — 改寫測試

1. 移除 `test_r2_configuration_is_frozen_before_resume_and_pins_new_taxonomy` 中兩行直接比對 live SHA 的斷言，改為驗證欄位存在且為 64 字元 hex 字串。
2. 新增 `test_pinned_scan_sources_have_no_unacknowledged_drift`，實作 4.1 的判定邏輯。
3. 新增 `test_drift_acknowledgement_is_canonically_sealed`：驗證 acknowledgement 的 canonical digest 與 sidecar 相符。
4. 新增 fail-closed 測試（用 `tmp_path` + `monkeypatch`，**不得**動到真實檔案）：
   - `test_unacknowledged_source_drift_fails_closed`：live SHA 與 pin 不同、acknowledgement 缺該條目 → 應 fail；
   - `test_stale_acknowledgement_fails_closed`：acknowledgement 的 `observed_sha256_at_acknowledgement` 與 live SHA 不同 → 應 fail；
   - `test_tampered_acknowledgement_digest_fails_closed`：改動 acknowledgement 內容但不更新 sidecar → 應 fail。

為了讓 fail-closed 測試可行，判定邏輯應抽成一個可注入路徑的純函式（例如 `_evaluate_source_drift(pins, live_shas, acknowledgement) -> list[str]` 回傳違規訊息清單），測試對該函式做表格驅動驗證，避免用檔案系統 mock 真實 artifact。

**Acceptance**：`python -m pytest tests/test_price_coverage_scan_segment_manifest.py -q` **全綠**；新增測試數 ≥ 5；至少 3 個是 fail-closed 案例。

**Status**：`NOT_STARTED`

### Phase 4 — 全套驗證與紅燈關閉紀錄

1. 全套測試：

   ```bash
   python -m pytest tests/ -q
   ```

   **預期：先前記錄的 `1 failed` 消失**。其餘 skip 數（PostgreSQL / Shioaji 相關）應與基線相當。
2. `python -m compileall -q backtest scripts tests`
3. `git diff --check`
4. 在 `progress.md`（或依 `DOC-001` 完成後的新規則寫入 `.planning/<ticket>/progress.md`）記錄：
   - 此長期紅燈的根因；
   - 選定方案 D 的理由；
   - 「`1721 passed, 86 skipped, 1 failed` 的那個 1 failed 已關閉」；
   - 未來重跑 coverage scan 必須先凍結新 configuration 的約束。

**Acceptance**：全套測試無 failed；紀錄已寫入。

**Status**：`NOT_STARTED`

---

## 6. 驗收條件（總）

1. `python -m pytest tests/test_price_coverage_scan_segment_manifest.py -q` 全綠。
2. `python -m pytest tests/ -q` 的 failed 數為 **0**。
3. `research/institutional_evaluation/acquisition/` 底下**原有**的 `.json` 與 `.canonical.sha256` **全部 byte-identical 未變**：

   ```bash
   git status --short research/institutional_evaluation/acquisition/
   # 應只顯示兩個新增的 acknowledgement 檔案，無任何 M
   ```

4. `backtest/historical_download.py` 與 `scripts/download_backtest_history.py` 未變更。
5. `python scripts/build_price_coverage_source_drift_acknowledgement.py --check` exit 0。
6. **反向驗證（reviewer 必做）**：手動在 `backtest/historical_download.py` 末尾加一個空白行，重跑 `pytest tests/test_price_coverage_scan_segment_manifest.py`，**應該變紅**並提示 acknowledgement 過期；然後還原該行，應恢復綠燈。這證明 gate 真的活著，而不是恆真斷言。

驗收條件 6 是本計畫與方案 A 的關鍵區別，**不可略過**。

---

## 7. 風險

| 風險 | 等級 | 緩解 |
|---|---|---|
| 執行者為了求快，直接採用工作目錄裡的硬編碼版本 | **高** | Phase 0 明訂先 `git checkout --` 還原；驗收條件 6 的反向驗證會直接抓到恆真斷言 |
| 誤改或重新產生 immutable artifact | **高** | Non-goals 明訂；驗收條件 3 用 `git status` 驗證零修改 |
| snapshot 已變動，本文件記錄的 SHA 過期 | 中 | Phase 1 明訂先實測比對，不符即停止回報 |
| `causing_commits` 推導錯誤 | 低 | 由 `git log` 產生而非硬編碼；即使不精確也不影響 gate 行為，只影響 rationale 可讀性 |
| 抽出的純函式改變了原測試對其他欄位的覆蓋 | 低 | Phase 3 只動兩行 SHA 斷言，其餘斷言（`prior_segments`、`resume_boundary`、`summary_lineage_policy`、`execution_lock`）完全保留 |

---

## 8. 交付物

1. `research/institutional_evaluation/acquisition/price_coverage_source_drift_acknowledgement_v1.json`
2. `research/institutional_evaluation/acquisition/price_coverage_source_drift_acknowledgement_v1.canonical.sha256`
3. `scripts/build_price_coverage_source_drift_acknowledgement.py`（含 `--check` 模式）
4. `tests/test_price_coverage_scan_segment_manifest.py` 更新（+5 個以上測試）
5. 紅燈關閉紀錄（`progress.md` 或對應 ticket 的 workpad）
