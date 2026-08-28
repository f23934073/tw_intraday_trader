# 專案衛生改善計畫索引（2026-08-28）

## 0. 文件狀態

- Source snapshot：`main@d0e271e0a247c669adae23423244de0cc7200832`
- 規劃日期：`2026-08-28`
- 這五份計畫來自一次全專案架構檢視。它們處理的是**專案衛生**，不是架構設計——核心決策鏈（`market_data → candidate → scoring → position/simulation → trading`）的分層原則清楚且被遵守，不在改動範圍內。

---

## 1. 五份計畫

| 代號 | 文件 | 主題 | 工期 | 可否由外部 LLM 獨立完成 |
|---|---|---|---|---|
| `HYG-001` | `working_tree_commit_packaging_implementation_plan.md` | 165 筆未提交變更分批提交、`index.lock`、`.gitignore` 破口 | 1～1.5 日 | ❌ 需 owner 本機執行 |
| `DOC-001` | `planning_log_single_source_implementation_plan.md` | 根目錄三件套與 `.planning/` 雙軌收斂、歸檔、一致性檢查 | 2～3 日 | ✅ |
| `ARCH-001` | `institutional_module_boundary_implementation_plan.md` | 四個 `institutional_*` 模組的血脈文件化與 import 邊界防護 | 3～4 日 | ✅ |
| `PCD-001` | `price_coverage_source_digest_drift_implementation_plan.md` | 長期紅燈測試 r2 price-coverage source-digest drift | 1～1.5 日 | ✅ **最適合首發** |
| `CI-001` | `static_analysis_ci_implementation_plan.md` | ruff / mypy 導入 CI | 3～5 日 | ✅ |

---

## 2. 依賴關係與建議順序

```text
HYG-001 (Git 分批提交)
   │  必須最先做：工作目錄乾淨才能安全地分派其他計畫
   │  T9 明確把 tests/test_price_coverage_scan_segment_manifest.py 移交 PCD-001
   ↓
   ├──→ PCD-001 (修紅燈)  ← 建議第二個做，做完全套測試才有可信的綠燈基線
   │        │
   │        ↓
   │     CI-001 (靜態檢查)  ← 需要綠燈基線，否則無法分辨新舊失敗
   │
   ├──→ ARCH-001 (模組邊界)   ← 與 PCD-001／CI-001 無衝突，可並行
   │
   └──→ DOC-001 (規劃文件)    ← 與所有其他計畫無檔案衝突，可並行
```

### 2.1 硬性順序約束

1. **`HYG-001` 必須最先完成**。其餘四份計畫都會新增檔案與 commit；在 165 筆混雜變更之上再疊加，會讓分群變得不可能。
2. **`PCD-001` 必須在 `CI-001` 之前**。`CI-001` 的驗收條件 3 是「相對基線無新增失敗」，若基線本身含一個永久失敗，這條驗收無法可靠執行。
3. `ARCH-001` 與 `DOC-001` 可與上述任一並行，彼此也不衝突。

### 2.2 檔案衝突矩陣

| | `pyproject.toml` | `README.md` | `ci.yml` | `tests/` | `.planning/` |
|---|:--:|:--:|:--:|:--:|:--:|
| `HYG-001` | | | | 只提交，不改 | ✅ 提交 |
| `DOC-001` | | | ✅ 新增步驟 | ✅ 新增檔 | ✅ 重整 |
| `ARCH-001` | | ✅ 加第 8 條 | | ✅ 新增檔 | |
| `PCD-001` | | | | ✅ 改既有檔 | |
| `CI-001` | ✅ | ✅ 加段落 | ✅ 新增步驟 | | |

**唯一需要協調的是 `.github/workflows/ci.yml`**：`DOC-001` 與 `CI-001` 都會插入新步驟。若兩者並行分派，請要求各自只插入自己的步驟、不重排既有步驟，合併時人工確認。

`README.md` 的衝突（`ARCH-001` 改「架構原則」、`CI-001` 在「執行測試」後加新段落）落在不同章節，一般不會產生 git conflict。

---

## 3. 分派給外部 LLM 時的共通說明

每份計畫的第 0.1 節都已寫明環境假設，但分派時建議在 prompt 中再強調三點：

1. **環境**：可 `pip install -e ".[dev]"` 與 `pytest`（`MockProvider`）；**沒有** Shioaji 金鑰、**沒有** PostgreSQL、**不可**連真實行情。相關測試會 skip，那是預期行為，不是失敗。
2. **安全邊界**：這個專案目前**刻意不含任何真實下單路徑**。所有 `institutional_*`、`premarket`、momentum 模組都是 observation-only 且 fail-closed。任何計畫都不得放寬這些邊界，即使 lint 或型別檢查看起來要求這麼做。
3. **Non-goals 是硬約束**：每份計畫的 3.2 節列的禁止事項不是建議。特別是 `PCD-001` 禁止修改 immutable artifact、`ARCH-001` 禁止合併模組、`CI-001` 禁止為了消 lint 而改行為。

---

## 4. 各計畫最關鍵的一件事

| 代號 | 最容易被做錯的地方 |
|---|---|
| `HYG-001` | 用 `git add -A` 把 20 GB 的 `data/` 加進索引。計畫明令只能用明確檔案清單。 |
| `DOC-001` | 歸檔時切錯章節邊界導致內容遺失。計畫要求行數守恆驗證。 |
| `ARCH-001` | 把「收斂」理解成「合併模組」而動了程式碼。計畫只允許改 docstring。 |
| `PCD-001` | 採用工作目錄裡那個硬編碼常數的改法，讓斷言變恆真。驗收條件 6 的反向驗證專門用來抓這個。 |
| `CI-001` | 為了消 lint 而順手改到交易邏輯。驗收條件 7 要求逐行檢視所有非 import 的新增行。 |

---

## 5. 立即可做的一件事（不屬於任何計畫）

`.git/index.lock` 目前存在（0 bytes，`2026-08-28 03:43`），會讓所有寫入型 git 指令失敗：

```bash
cd ~/Documents/tw_intraday_trader
ps aux | grep -i '[g]it'      # 先確認沒有殘留 git 程序
ls -la .git/index.lock        # 確認是 0 bytes
rm -f .git/index.lock
```

這是 `HYG-001` Phase 0 的第一步，但即使不執行 `HYG-001` 也應該先處理，否則無法 commit。
