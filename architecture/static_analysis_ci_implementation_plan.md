# CI 靜態檢查（Ruff / Mypy）導入 Implementation Plan

## 0. 文件狀態

- 狀態：`PLAN_ONLY / NOT_IMPLEMENTED`
- Source snapshot：`main@d0e271e0a247c669adae23423244de0cc7200832`
- 規劃日期：`2026-08-28`
- 計畫代號：`CI-001`
- 預估工期：3～5 個開發日（依 Phase 1 實測的 baseline violation 數而定）
- 安全邊界：**任何 lint 修正都不得改變 runtime 行為**。禁止為了滿足 lint 而修改交易邏輯、fail-closed 判斷、digest 計算或任何 immutable artifact 的序列化順序。

### 0.1 執行環境假設（交付給外部 LLM 時必讀）

- 可執行 `python -m pip install -e ".[dev]"` 與 `python -m pytest`（預設 `MockProvider`）。
- **沒有** Shioaji 金鑰、**沒有** PostgreSQL、**不可**連真實行情。本計畫的所有驗收都只需要 lint 工具與 pytest，可在 sandbox 完整完成。
- ruff / mypy 需能從 PyPI 安裝。若環境無網路，本計畫無法執行，應回報而非略過。

---

## 1. 結論先講

專案有 **561 個 Python 檔、176,733 行**程式碼，其中 443 個檔案使用 `from __future__ import annotations`——代表型別註記的紀律其實不差。但目前：

- `pyproject.toml` **完全沒有** `[tool.ruff]` 設定，`dev` extra 也沒有 ruff；
- `.ruff_cache/` 底下同時存在 `0.13.1` 與 `0.16.3` 兩個版本的快取，代表本機有人在跑，但**版本不一致且未釘住**；
- CI（`.github/workflows/ci.yml`）只有 `compileall`、`check_dashboard_js.py`、`pytest`、`git diff --check` 四道關卡，**沒有任何 lint 或型別檢查**。

`compileall` 只保證語法可解析，抓不到 unused import、未定義名稱、shadowed 變數、錯誤的型別串接。對一個大量使用 dataclass、Protocol、versioned contracts 的專案來說，這些正是最容易在跨模組介面上出錯的地方。

本計畫完成後：

1. ruff 版本被釘死在 `dev` extra 與 `[tool.ruff]` 設定中，本機與 CI 用同一版、同一組規則。
2. 先以**只會抓真 bug** 的規則集（`F` + 部分 `E`）建立 baseline，把既有違規清乾淨。
3. CI 加入 `ruff check`（阻擋）與 `ruff format --check`（初期非阻擋）。
4. mypy 以**極窄 scope** 導入三個 contract-heavy 且無 SDK 依賴的模組，用 per-module override，不做全域 strict。

**重要**：本文件**刻意不預設 violation 數量**。Phase 1 的第一個交付物就是量測 baseline；後續階段的工作量與排程必須依實測數字調整，不得沿用本文件的估計。

---

## 2. 現況與主要缺口

### 2.1 現況實測

| 項目 | 實測值 |
|---|---|
| Python 檔案數（排除 `.venv`/`build`/`__pycache__`） | 561 |
| 總行數 | 176,733 |
| 使用 `from __future__ import annotations` 的檔案 | 443 |
| `pyproject.toml` 的 `[tool.ruff]` | **不存在** |
| `dev` extra 內容 | `httpx2`、`pytest`、`pytest-cov`（**無 ruff、無 mypy**） |
| `.ruff_cache/` 版本 | `0.13.1`、`0.16.3`（兩版並存） |
| CI 檢查步驟 | `compileall`、`check_dashboard_js.py`、`pytest`、`git diff --check` |

### 2.2 各區塊檔案數

| 區塊 | `.py` 檔數 |
|---|---:|
| `tests` | 220 |
| `scripts` | 64 |
| `backtest` | 49 |
| `market_data` | 42 |
| `runtime` | 24 |
| `trading` | 20 |
| `simulation` | 10 |
| `dashboard` | 6 |
| 其餘（`candidate`/`scoring`/`position`/`config`/`signals`/`features`/`premarket`/`institutional_*`/`strategy_catalog`/`atomic_strategies`/`watchlist`) | 餘數 |

### 2.3 P0 缺口

1. **無版本釘選**：兩個 ruff 版本的預設規則集不同，本機綠、CI 紅（或相反）只是時間問題。
2. **無設定檔**：沒有 `[tool.ruff]` 就等於用該版本的預設值，而預設值會隨版本改變。
3. **CI 無 lint**：unused import、未定義名稱這類問題目前只能靠 code review 抓。
4. **無型別檢查**：`atomic_strategies/protocol.py`、`signals/` 的 versioned contracts、`runtime/ports.py` 這些 Protocol / port 定義，跨模組實作是否相符完全沒有機器驗證。

### 2.4 明確不是缺口

- `git diff --check`（whitespace）與 `check_dashboard_js.py`（JS 語法）已存在且有效，本計畫保留不動。
- 多版本 Python 矩陣（3.11 / 3.12）與 PostgreSQL 整合 job 已存在，不動。

---

## 3. Scope

### 3.1 In scope

- 在 `pyproject.toml` 的 `dev` extra 加入釘死版本的 `ruff` 與 `mypy`。
- 新增 `[tool.ruff]`、`[tool.ruff.lint]`、`[tool.ruff.lint.per-file-ignores]` 設定。
- 量測並記錄 baseline violation。
- 分批修正 `F` 類與選定 `E` 類違規。
- 在 `.github/workflows/ci.yml` 的 `test` job 加入 ruff 步驟。
- 新增 `[tool.mypy]` 設定，僅對 `signals`、`features`、`atomic_strategies` 三個套件啟用。
- 在 CI 加入 mypy 步驟（僅涵蓋上述三個套件）。

### 3.2 Non-goals

- **不啟用會大規模改寫程式碼的規則集**：`ANN`（強制註記）、`D`（docstring 風格）、`PL`（pylint 全家）、`C90`（複雜度）一律不在第一階段啟用。
- **不執行 `ruff format` 對全 repo 重排版**。第一階段只做 `--check` 且非阻擋，避免產生 17 萬行的格式 diff 淹沒 git 歷史。
- 不對 `tests/`（220 檔）套用與 production 相同的嚴格度；用 `per-file-ignores` 放寬。
- 不啟用全域 mypy strict。
- 不引入 pre-commit hook（可作為後續票）。
- 不因 lint 而修改任何交易邏輯、fail-closed 條件、digest / canonical JSON 的欄位順序。

---

## 4. 目標設定

### 4.1 `pyproject.toml` 新增內容

```toml
[project.optional-dependencies]
dev = [
    "httpx2>=2,<3",
    "mypy==1.18.2",
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "ruff==0.16.3",
]
```

> ruff 版本選 `0.16.3`（`.ruff_cache/` 中較新的那一版），用 `==` 完全釘死，避免規則集隨版本漂移。mypy 版本由執行者在 Phase 1 確認當時的穩定版後填入並釘死。

```toml
[tool.ruff]
target-version = "py311"
line-length = 100
extend-exclude = [".venv", "build", "data", "records", "research", ".planning"]

[tool.ruff.lint]
# 第一階段只開「會抓真 bug」與「低風險」的規則。
# 擴充規則集（ANN/D/PL/C90/SIM/RET 等）留待 baseline 清零後另案評估。
select = [
    "F",      # pyflakes：未定義名稱、未使用 import/變數、重複定義
    "E4",     # import 相關
    "E7",     # 語句層級錯誤
    "E9",     # 執行期錯誤（語法／IO）
    "I",      # isort：import 排序
    "UP",     # pyupgrade：過時語法
    "B",      # flake8-bugbear：常見陷阱
]
ignore = [
    "B008",   # 函式呼叫作為預設參數（FastAPI Depends 慣用）
]

[tool.ruff.lint.per-file-ignores]
"tests/**" = ["F401", "F811"]        # fixture 匯入與同名覆寫是 pytest 慣例
"scripts/**" = ["T201"]              # 腳本允許 print
"**/__init__.py" = ["F401"]          # re-export

[tool.ruff.lint.isort]
known-first-party = [
    "app", "atomic_strategies", "backtest", "candidate", "config", "dashboard",
    "features", "institutional_data", "institutional_mvp", "institutional_prior",
    "institutional_research", "market_data", "position", "premarket", "runtime",
    "scoring", "signals", "simulation", "strategy_catalog", "trading", "watchlist",
]
```

**注意**：`extend-exclude` 中的 `data`、`records`、`research`、`.planning` 是為了避免 ruff 掃描 20 GB 的資料目錄。`.planning/` 底下確實有 4 個 `.py` 檔（`2026-08-24-vwap-strategy-failure-attribution/{diagnose_r5_missing_next_bars,audit_r5_terminal,execute_r5_control}.py` 與 `2026-08-21-backtest-memory-streaming/profile_streaming.py`），它們是一次性稽核／profiling 腳本，不應納入 lint。

### 4.2 mypy 目標範圍

只對三個套件啟用，理由：

| 套件 | 理由 |
|---|---|
| `signals` | versioned、replay-safe contracts；docstring 明示「dependency-free model contracts」，無 SDK 依賴 |
| `features` | 「Deterministic intraday feature contracts and evaluation」，純計算 |
| `atomic_strategies` | 有 `protocol.py`，Protocol 實作一致性正是 mypy 最能發揮的地方 |

```toml
[tool.mypy]
python_version = "3.11"
files = ["signals", "features", "atomic_strategies"]
ignore_missing_imports = true
warn_unused_ignores = true
no_implicit_optional = true
check_untyped_defs = true

[[tool.mypy.overrides]]
module = ["signals.*", "features.*", "atomic_strategies.*"]
disallow_untyped_defs = true
```

若 Phase 4 實測發現某個套件的錯誤數過高（例如 > 50），該套件先降級為只開 `check_untyped_defs`，並記錄原因；**不得**用 `# type: ignore` 大量掩蓋。

---

## 5. 實作階段

### Phase 1 — Baseline 量測（**本計畫的第一個交付物**）

1. 安裝釘死版本：

   ```bash
   python -m pip install "ruff==0.16.3"
   ```

2. 在**尚未加入任何設定**的狀態下，先跑一次寬鬆量測取得規模感：

   ```bash
   ruff check . --exclude .venv,build,data,records,research,.planning --statistics
   ```

3. 加入 4.1 的 `[tool.ruff]` 設定後再跑一次：

   ```bash
   ruff check . --statistics
   ruff check . --output-format=concise > /tmp/ruff_baseline.txt
   wc -l /tmp/ruff_baseline.txt
   ```

4. 依規則代碼分組統計，並區分 `production` 與 `tests/` 與 `scripts/`。
5. 產出 `research/static_analysis_baseline_2026-08-28.md`，內容至少含：
   - 每個規則代碼的違規數；
   - 前 10 個違規最多的檔案；
   - 明確標示哪些是 `F821`（未定義名稱）等**可能是真 bug** 的項目——這些要優先且逐一人工檢視。

**Acceptance**：baseline 文件存在；含依規則代碼與依目錄的兩張統計表；`F821`、`F811`、`F402` 等高風險項目已被單獨列出。

**決策點**：若 `select` 清單下的總違規數 > 500，回報 owner 並提議縮減第一階段 `select`（例如先只開 `F` + `E9`），不要硬修。

**Status**：`NOT_STARTED`

### Phase 2 — 修正高風險違規（`F` 類優先）

依此順序處理，**每一組獨立 commit**：

| 順序 | 規則 | 說明 | 風險 |
|---:|---|---|---|
| 1 | `F821` | 未定義名稱 | **可能是真 bug**，逐一人工判讀，不得盲改 |
| 2 | `F811` | 重複定義（覆寫） | 可能是真 bug |
| 3 | `F841` | 賦值後未使用的區域變數 | 可能藏著漏掉的邏輯，逐一判讀 |
| 4 | `F401` | 未使用的 import | 低風險，但 `__init__.py` 的 re-export 已由 per-file-ignores 排除 |
| 5 | `B` 類 | bugbear 陷阱 | 中風險，逐一判讀 |
| 6 | `UP` 類 | 過時語法 | 低風險，可用 `ruff check --fix` |
| 7 | `I` 類 | import 排序 | 低風險，可用 `ruff check --fix` |

**強制規則**：

- 前三類（`F821`/`F811`/`F841`）**禁止使用 `--fix`**，必須逐一人工判讀。若判定是真 bug，**不在本計畫修**——開一張獨立票，並在該行加 `# noqa: F821  # tracked by <ticket>` 暫時放行，且在 baseline 文件記錄。本計畫的目標是「讓 lint 可以進 CI」，不是順手改行為。
- 每組 commit 後必須跑 `python -m pytest tests/ -q`，確認相對基線無新增失敗。

**Acceptance**：`ruff check .` exit 0；每組 commit 都通過測試；所有 `# noqa` 都帶有追蹤票號註解。

**Status**：`NOT_STARTED`

### Phase 3 — CI 導入 ruff

在 `.github/workflows/ci.yml` 的 `test` job，`Install test dependencies` 之後、`Compile Python packages` 之前插入：

```yaml
      - name: Lint with Ruff
        run: python -m ruff check .

      - name: Check formatting with Ruff (non-blocking)
        run: python -m ruff format --check .
        continue-on-error: true
```

**設計說明**：`ruff format --check` 設 `continue-on-error: true`，因為對 176,733 行既有程式碼做一次性重排版會產生無法審核的巨大 diff。先讓它跑起來累積資訊，是否轉為阻擋另案決定。

**Acceptance**：CI 設定檔 YAML 合法；本機以相同指令模擬 `python -m ruff check .` exit 0。

**Status**：`NOT_STARTED`

### Phase 4 — mypy 窄範圍導入

1. 確認 mypy 當前穩定版並釘死寫入 `dev` extra。
2. 加入 4.2 的 `[tool.mypy]` 設定。
3. 量測：

   ```bash
   python -m mypy 2>&1 | tail -5
   ```

4. 產出 `research/mypy_baseline_2026-08-28.md`，依套件與錯誤碼分組。
5. 修正錯誤。**同 Phase 2 的原則**：疑似真 bug 的一律開票，不在本計畫改行為。
6. CI 加入：

   ```yaml
      - name: Type-check contract packages
        run: python -m mypy
   ```

**Acceptance**：`python -m mypy` exit 0；baseline 文件存在；`signals`、`features`、`atomic_strategies` 三個套件全數通過。

**降級條款**：若某套件錯誤數 > 50，將該套件從 `disallow_untyped_defs` override 移除並在文件記錄原因與後續計畫。**不得**用大量 `# type: ignore` 掩蓋。

**Status**：`NOT_STARTED`

### Phase 5 — 文件與清理

1. `README.md` 的「執行測試」段落後新增「靜態檢查」段落：

   ```markdown
   ## 靜態檢查

   ```bash
   python -m ruff check .        # lint
   python -m ruff format --check .  # 格式（目前非阻擋）
   python -m mypy                # 型別檢查（僅 signals/features/atomic_strategies）
   ```

   ruff 與 mypy 版本已在 `pyproject.toml` 的 `dev` extra 釘死，本機請用 `pip install -e ".[dev]"` 安裝，勿自行升級，否則規則集會與 CI 不一致。
   ```

2. 清理過期的 ruff 快取：

   ```bash
   rm -rf .ruff_cache/0.13.1
   ```

3. 確認 `.gitignore` 已含 `.ruff_cache/`（目前未含，需補上）。

**Acceptance**：README 段落存在；`.gitignore` 含 `.ruff_cache/`；`git status` 不再顯示 ruff 快取。

**Status**：`NOT_STARTED`

---

## 6. 驗收條件（總）

1. `python -m ruff check .` exit 0。
2. `python -m mypy` exit 0。
3. `python -m pytest tests/ -q` 相對於本計畫開始前**無新增失敗**（既有的 r2 price-coverage 失敗歸 `PCD-001`）。
4. `python -m compileall -q app.py backtest candidate config dashboard features market_data position runtime scoring signals simulation strategy_catalog trading scripts tests` 通過。
5. `pyproject.toml` 的 ruff 與 mypy 版本皆為 `==` 完全釘死。
6. 兩份 baseline 文件存在，且所有 `# noqa` / `# type: ignore` 都有追蹤票號註解。
7. **行為不變證明（reviewer 必做）**：對本計畫產生的所有 commit 執行

   ```bash
   git diff <base>..HEAD -- '*.py' | grep -E '^\+' | grep -vE '^\+\+\+' | grep -vE '^\+\s*(import|from|#|$)'
   ```

   人工檢視每一行**非 import、非註解**的新增行，確認沒有任何邏輯改動。

驗收條件 7 是本計畫最重要的一關：lint 修正很容易「順手」改到行為，而 176,733 行的專案沒有人能靠印象發現。

---

## 7. 風險

| 風險 | 等級 | 緩解 |
|---|---|---|
| 為了消 lint 而改到交易邏輯或 fail-closed 判斷 | **高** | 驗收條件 7 的逐行檢視；`F821`/`F841` 禁止 `--fix`；疑似 bug 一律開票不改 |
| `--fix` 對 `I`（import 排序）動到有副作用的 import 順序 | 中 | `I` 排在最後處理；修正後必跑全套測試；特別注意 `config/`、`runtime/composition.py` 這類有初始化順序的檔案 |
| baseline 違規數遠超預期，計畫失控 | 中 | Phase 1 設決策點（> 500 即縮減 `select` 並回報） |
| ruff 版本升級導致 CI 突然紅燈 | 中 | `==` 完全釘死；README 明示勿自行升級 |
| `ruff format` 產生巨大 diff | 中 | 第一階段設 `continue-on-error: true`，不阻擋 |
| mypy 對 dataclass / Protocol 的推斷產生大量假陽性 | 中 | 窄 scope + 降級條款；禁止大量 `# type: ignore` |
| 新 CI 步驟拖慢流程 | 低 | ruff 對 17 萬行約數秒；mypy 僅三個套件 |

---

## 8. 交付物

1. `pyproject.toml`：`dev` extra 加入釘死的 ruff / mypy；新增 `[tool.ruff]`、`[tool.ruff.lint]`、`[tool.ruff.lint.per-file-ignores]`、`[tool.ruff.lint.isort]`、`[tool.mypy]`
2. `research/static_analysis_baseline_2026-08-28.md`
3. `research/mypy_baseline_2026-08-28.md`
4. 分組的 lint 修正 commit（依 Phase 2 的 7 個順序）
5. `.github/workflows/ci.yml`：新增 ruff check、ruff format --check（非阻擋）、mypy 三個步驟
6. `README.md`「靜態檢查」段落
7. `.gitignore` 補上 `.ruff_cache/`
