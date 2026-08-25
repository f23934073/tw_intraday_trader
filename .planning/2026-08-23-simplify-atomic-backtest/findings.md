# Findings

## 參照 task

- 「建立三年歷史資料」使用獨立的 FinMind checkpoint／canonical SQLite store：`data/finmind_sponsor/history.sqlite3`。
- 該 task 已完成一批 8 檔、5,816 個 symbol-day 的三年資料，並仍在擴大取得其他股票資料。
- 這證明歷史資料取得流程已存在，但不等同於 Backtest PostgreSQL 已存在可直接執行的 READY immutable Dataset。

## 現有產品契約

- Backtest Run 目前以 PostgreSQL Dataset identity 作為 immutable evidence 的一部分。
- 現有 Atomic Run 瀏覽器表單要求使用者選擇 `atomic-backtest-dataset`，並在 payload 傳 `dataset_id`。
- 歷史回測目前有四步；第一步會在頁內觸發資料同步，第二步同時混有 Atomic 與 Legacy 回測。

## 初步設計方向

- UI 移除資料準備與 Dataset selector，但不能把 Dataset identity 從 Run evidence 移除。
- 應由伺服器在建立 Run 時選定並鎖定 READY Dataset；若沒有可用快照，明確 fail closed。
- 不應讓回測直接讀取背景下載中、仍會變動的資料庫。

## UX 與既有決策檢索

- UI/UX 指引支持保留清楚的步驟指示；移除資料準備後應把流程重新編號為三步，而不是留下跳號或隱藏步驟。
- Memory registry 沒有找到本專案更精確的 Dataset 自動解析既有決策；本次以目前 repository 契約與引用 task 的現況為準。

## Repository 盤點

- `BacktestService` 的 Legacy 與 Atomic 建立流程目前都要求明確 `dataset_id`，並驗證該 Dataset 為 `READY`。
- Repository 已提供依 `created_at DESC` 的 `list_datasets()`，但尚無伺服器端「預設 READY Dataset」resolver。
- `scripts/download_finmind_sponsor_history.py` 只處理 sponsor history store；現有搜尋沒有找到它直接登記至 `backtest_datasets` 的 bridge。
- 另一條既有 Provider Backtest 下載流程會在完整封存、驗證 SHA-256 後才把 Dataset 登記為 `READY`；這是本次自動選取可安全依賴的邊界。
- 前端目前同時綁定 Atomic Dataset selector、Legacy submit handler 與資料同步 panel；需要一起移除事件 wiring，避免留下隱藏 mutation 路徑。

## 實作契約

- `create_atomic_run()` 仍應接收一個已解析的 Dataset ID，這樣既有 config digest、comparability 與 worker preflight 都能維持不變。
- 最小安全改法是在 Application 層新增 deterministic READY resolver，讓 HTTP Atomic create 不再接受 client `dataset_id`，但 service 內仍將選定的 Dataset identity 寫入 Run。
- Legacy `/api/backtests/runs` 與 Dataset sync API 可暫留作相容／維運介面；本次移除的是使用者頁面與瀏覽器 mutation 路徑，避免擴張成資料庫 migration 或 CLI 破壞性刪除。
- Atomic launcher 的 Baseline comparability 仍可能要求與自動選取 Dataset 相同；後端既有 comparability check 會 fail closed。

## 受影響測試與 UI

- `test_backtest_dashboard_ui.py` 目前明確鎖定四步、資料同步狀態、Legacy selector 與 experimental capability 過濾；這些需改成三步與 Atomic-only 契約。
- `test_atomic_strategy_web_api.py` 的 API probe 仍傳 `dataset_id`；StrictRequest 更新後應新增「未知 dataset_id 為 422」與「service 自動解析後建立 Run」覆蓋。
- 目前 Atomic launcher 文案仍宣稱「下方舊版選擇器保留」，需要改成「系統自動鎖定最新 READY 歷史快照」。
- 結果頁與比較頁仍顯示 Run 的 Dataset identity，這些資訊應保留，因為它們是研究可重現性證據，不是使用者輸入欄位。

## 最小修改面

- API request model 可直接移除 `dataset_id`；StrictRequest 會自然拒絕舊欄位，避免 client 仍能指定任意 Dataset。
- HTTP route 仍沿用既有 audit／idempotency 流程；Application resolver 選出的 Dataset 會成為 `create_atomic_run()` 的內部輸入。
- `backtest.js` 可移除 Legacy DOM references、Legacy render／request／submit 及 Dataset sync polling；保留 `state.backtest.datasets` 供 readiness 顯示與 Run 結果 evidence。
- `app.js` 目前直接綁定已刪除按鈕／form，需改為 optional chaining 或移除對應 listener，否則頁面啟動會因 null element 中斷。

## Idempotency 與 Baseline 決策

- Repository 的 `create_run()` 會以 `idempotency_key` 查回既有 Run 並比較完整 `config_digest`；若背景同步後自動選到新 Dataset，同 key retry 會變成錯誤衝突。
- 因此 Application 需要先依 idempotency key 找既有 Run：合法 replay 固定使用原 Run 的 Dataset，再走既有 config digest 比對；不同 request 仍會 409。
- 建立 Challenger 時應優先沿用 Baseline Run 的 Dataset，否則「最新 READY」可能讓原本可比較的研究無法建立。
- 新的首次 Atomic Run 才依 repository 的 `created_at DESC`，選第一個能滿足該 exact Strategy Set capabilities 的 READY Dataset。

## 已實作

- 歷史回測改為三步，預設直接開啟「設定策略組合」。
- 「準備歷史資料」panel、Dataset selector 與「舊版固定策略回測」表單已從 DOM 與 JavaScript wiring 移除。
- Atomic create request 不再接受 client `dataset_id`；Application 會自動選擇相容 READY Dataset，並處理 replay／Baseline 的穩定 Dataset identity。
- 頁面只顯示歷史資料 readiness 摘要，不要求使用者管理 Dataset。
- Python 與 Dashboard JavaScript syntax 初步檢查通過。

## 文件漂移

- README 仍把網頁描述成四步、要求使用者選 READY Dataset，且宣稱同步狀態顯示在「準備歷史資料」。
- CLI 下載／封存與 incremental sync API 仍是有效維運能力，不應因 UI 移除而刪除；README 需改成「背景／CLI 管理，Web 自動使用」。
- Atomic clone 原本讀取已刪除的 Legacy form 欄位；已改為只允許 Atomic Run，並使用 Atomic launcher 的資金欄位。Legacy 歷史 Run 保留唯讀查閱。

## 最終 Dataset 選取規則

1. 同 idempotency key replay：沿用原 Run Dataset。
2. Challenger：沿用 Baseline Dataset。
3. 首次獨立 Run：在相容的 READY Dataset 中，優先 research-eligible，再依既有 `created_at DESC` 取最新。
4. 沒有相容 READY Dataset：fail closed，不建立 Run。
