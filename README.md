# 台股即時選股與交易決策系統 MVP

台股盤中即時決策系統，核心流程：

> 找誰 → 值不值得買 → 買了之後何時離場

---

## 快速開始

### 1. 安裝依賴

```bash
# 建立虛擬環境
python3 -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安裝基本依賴
python3 -m pip install -e ".[dev]"

# 若要使用 Shioaji 真實連線（選填）
python3 -m pip install -e ".[broker,dev]"
```

### 2. 設定環境變數（選填，使用 Shioaji 才需要）

```bash
cp .env.example .env
# 編輯 .env，填入 SHIOAJI_API_KEY 與 SHIOAJI_SECRET
```

### 3. 執行

```bash
python3 app.py
```

預設使用 **MockProvider**，不需網路連線，立即可看到輸出。
若 `.env` 或 shell 已設定 `PROVIDER=shioaji`，它會明確覆寫此預設，必須先安裝 broker extra 並設定 Shioaji 金鑰。

---

## Web 儀表板

本機啟動儀表板與紙上模擬：

```bash
python3 -m dashboard
```

瀏覽器開啟 `http://127.0.0.1:8000`。首頁預設是「市場總覽」：先看候選數、資料健康、待處理委託與已成交持倉，再選取候選股查看完整評估。左側功能欄可收合成圖示列；手機版會變成可滑出的導覽。候選清單仍是單次掃描快照，只有按下「重新掃描」才會再次執行全市場掃描。選取候選股後，預設顯示 1 日來源 Kbar，也可切換 5 日、20 日或 3 月；3 月日 K 額外顯示 MA5／MA20／MA60、成交量與區間高低點。歷史資料只會在選取該股票時向後端查詢；長週期會由後端分段取得，避免超過資料來源的單次 Kbar 查詢限制。

「盤中動能」已從首頁主畫面移到左側的獨立研究工作區，固定讀取 immutable 8039 Replay fixture，用來展示 `ACCELERATING` stage、Evidence Score、episode timeline、告警確認與 Entry／RiskGate 狀態。它會明確標示「Replay fixture／非即時」；瀏覽器每 2 秒只讀本機 Momentum projection，不會因此啟動 Shioaji Provider、重新計算訊號或送出委託。Evidence Score 是 `hypothesis_v0` 規則證據，不是漲停機率。

左側的「模擬下單」可建立本機紙上限價委託；「委託」可查看已送出、成交、取消或拒絕的紀錄；「持倉」只顯示由已成交模擬委託建立的股票與其平均成交價、最新成交、買一／賣一、市值和損益。這些功能會開啟整頁工作區；瀏覽器每 2 秒讀取一次本機投影，不會因畫面更新而輪詢 Shioaji snapshot 或帳務 API。

這個功能是 **LOCAL_PAPER_SIMULATION**：預設虛擬現金為 1,000 萬元，只支援多頭整張限價單（1 張＝1,000 股），不計手續費或稅金。使用 `PROVIDER=shioaji` 時，後端只對持倉與尚未成交委託動態訂閱 Tick＋BidAsk；買進以賣一、賣出以買一判斷並作為本機模擬成交價，Tick 用來更新持倉市值與未實現損益。每檔使用兩個行情訂閱，程式最多允許同時監控 100 檔。若使用 MockProvider，則保留 snapshot 立即撮合，方便離線開發與測試。

所有委託與持倉只存在此 Web process 的記憶體，重啟後會清空。Shioaji 登入明確使用 `subscribe_trade=False`，沒有啟用憑證、註冊委託 callback 或呼叫下單 API；因此它仍不是 Shioaji Simulation 帳戶，也不會送出任何真實券商委託。

---

## 歷史回測（資料研究，不會下單）

在儀表板左側點選「歷史回測」，即可開啟整頁研究工作區；工作流程拆成四個 tab：

1. 準備歷史資料：建立或選擇封存的歷史資料集；按「建立資料集」會在背景透過後端 Provider 下載 Kbar，不會卡住網頁。
2. 設定策略組合：分別選擇買入與賣出策略，每一側可只選 1 個獨立執行，也可複選多個並設定 `ANY`、`ALL` 或「至少 N 個」條件。
3. 回測工作與結果：建立回測後，可查看進度、取消、失敗重試、OOS 勝率／信賴區間、損益、回撤、Profit Factor、交易明細與策略歸因。
4. Baseline／Challenger 比較：選擇舊 Run、填寫調整原因後複製並調整，再比較兩個已完成 Run。

點選交易可查看該筆進出場的主要策略、所有同時觸發策略、門檻與當時觀測值；也可以匯出 CSV。

回測使用獨立的 `backtest/` composition：只讀已封存的資料集，買入訊號最早在下一根 Kbar 才成交，並納入手續費、賣出證交稅與滑價。它不會啟動本機紙上模擬、Shioaji 下單、帳務、CA 或 trade subscription。

本機預設把資料集與歷史結果存於 `data/backtest/`（SQLite）；平台部署可設定 `BACKTEST_DATABASE_URL=postgresql://...` 並安裝 PostgreSQL extra：

```bash
python3 -m pip install -e ".[postgres,dev]"
BACKTEST_DATABASE_URL='postgresql://user:password@host:5432/tw_backtest' python3 -m dashboard
```

### 可續傳的歷史資料下載 script

全市場三年 Kbar 不適合只靠瀏覽器背景工作：時間長，而且 Shioaji 另有每日行情流量與查詢頻率限制。可改用獨立 CLI；每完成一檔股票，就會把 canonical JSONL 以 gzip 壓縮後寫入目前回測資料庫的 `backtest_history_partitions`。按 `Ctrl+C`、連線失敗或關閉終端機後，已完成股票不會遺失。

先用少量股票確認帳號、日期與資料量：

```bash
PROVIDER=shioaji .venv/bin/python scripts/download_backtest_history.py \
  --years 3 \
  --symbols 2330 2317
```

確認後下載目前 Provider 可列出的全部股票：

```bash
PROVIDER=shioaji .venv/bin/python scripts/download_backtest_history.py --years 3
```

script 啟動時會先輸出 `dataset-download-*` 工作 ID。若中斷，使用相同 Provider 接續：

```bash
PROVIDER=shioaji .venv/bin/python scripts/download_backtest_history.py \
  --resume dataset-download-請替換成實際ID
```

Downloader 會把 Shioaji Kbar 查詢限制在每 10 秒最多 40 次，低於官方 50 次上限；每次查詢前也會讀取 `api.usage()`，至少保留 16 MiB 安全流量。若接近每日上限，或收到無法判定為真實無資料的空 Kbar，工作會標為 `PAUSED` 並以 exit code `75` 結束，不會把 0 根資料誤存成完成。Shioaji 流量於交易日上午 `08:00` 重置，重置後執行同一個 `--resume` 指令即可。

舊版 Downloader 已經寫入「資料來源未回傳 Kbar」的工作也可以直接使用新版 `--resume`。新版除了找第一個 0 根異常，也會辨識舊程式超速後常見的「多檔股票同時只剩最後一年」截斷模式，保留最早異常以前的成功資料並重抓後續尾段；不需要刪除資料庫，也不要建立新的 job。這會一併修復異常點之後看似非零、實際只有部分日期的分區。

SQLite 預設寫入 `data/backtest/backtest.sqlite3`；若有設定 `BACKTEST_DATABASE_URL=postgresql://...`，partition 與工作進度會寫入 PostgreSQL。全部完成後，script 會以 streaming 方式封存 `bars.jsonl`／`manifest.json`、驗證 SHA-256，並在 `backtest_datasets` 登記為 `READY`；回到網頁按「重新整理」即可選取。

不要同時執行網頁的「建立資料集」與 CLI 全市場下載，否則不同 process 無法共用同一個頻率限制器，也會重複消耗 Provider 額度。舊版已經在執行中的網頁工作沒有資料庫 partition，無法把其中途進度轉成新的 `--resume` 工作；請先在網頁取消，再啟動或接續 CLI。

### 收盤後自動增量同步

Dashboard process 啟動時會啟用收盤排程。預設每個工作日 `14:30`（`Asia/Taipei`）檢查一次最新的 `READY` Provider 資料集，只重抓每檔股票最後一根 Kbar 所在日期到今天，並把 watermark 以前的重疊資料排除。舊資料集不會被改寫；有新 Kbar 時會建立 `parent + delta` 的新 immutable dataset，沒有新資料時只記錄本日已檢查並沿用原資料集。

第一次仍需先用上述 CLI 完成三年基礎資料集。若完整下載仍在執行，排程會顯示「等待既有下載工作」並持續重試，不會再啟動另一份全市場下載。休市日不會建立空資料集；程式停機數日後再次於收盤時間運行，會從各檔既有 watermark 接續到當天。

排程狀態會顯示在網頁「歷史回測 → 準備歷史資料」，也可以讀取 `GET /api/backtests/datasets/incremental-sync`。若修改設定，需要重新啟動 Dashboard：

```bash
BACKTEST_INCREMENTAL_SYNC_ENABLED=true
BACKTEST_INCREMENTAL_SYNC_CLOSE_TIME=14:30
BACKTEST_INCREMENTAL_SYNC_POLL_SECONDS=60
BACKTEST_INCREMENTAL_SYNC_OVERLAP_DAYS=1
BACKTEST_ACTIVE_JOB_STALE_MINUTES=30
```

這是應用程式內排程，因此電腦與 Dashboard process 必須運行。SQLite 適合目前單一 Dashboard process；若平台部署多個 Web process，應只讓一個 process 啟用排程，其他 process 設定 `BACKTEST_INCREMENTAL_SYNC_ENABLED=false`。

其他可用設定：`BACKTEST_ENABLED`（預設 `true`）、`BACKTEST_DATA_DIR`（預設 `data/backtest`）、`BACKTEST_DATABASE_URL` 與 `BACKTEST_WORKERS`。完整驗證可先執行：

```bash
python3 -m pytest -q tests/test_backtest_core.py tests/test_backtest_api.py
```

### 統一策略目錄

左側的「策略目錄」會讀取 `/api/strategies`，集中顯示所有策略家族，不限於回測可執行的買入／賣出策略。每個版本包含：

- `role`：`CANDIDATE`、`SCORE`、`SIGNAL`、`ENTRY`、`EXIT`
- `session_phase`：`PRE_MARKET`、`OPENING`、`INTRADAY`、`END_OF_DAY`、`POSITION_LIFECYCLE`
- `status`、資料能力、execution binding、標籤與可任意巢狀的 JSON `parameters`

`/api/backtests/strategies` 只會回傳已在伺服器註冊、且目錄版本與 execution binding 完全一致的 `ENTRY`／`EXIT` 策略。目錄中的候選、評分、訊號、草稿或尚未接上歷史執行器的研究策略不會出現在回測選單，也不會因資料庫 metadata 而被當成程式執行。

目前的盤前跳空觀察名單定義會標示為 `DRAFT`，因為現有資料流程尚未提供盤前試撮資料；開盤跳空、高成交量、VWAP、動能與回測策略則會各自標示實際時段與研究狀態。這樣可以先統一目錄，再逐步接上候選池與盤中決策，不會把「候選」誤當成「買入」。

策略版本是 immutable：同一個 `strategy_id + version` 若內容不同，API 會拒絕覆蓋，必須建立新版本。新增或調整資料庫策略可使用 `POST /api/strategies`；新邏輯先存為 `DRAFT`，只有已部署且白名單內的 execution binding 才能標為 `ACTIVE`／`EXPERIMENTAL`。資料庫只保存定義與參數，不會直接執行任意程式碼。

### 近三年全市場的資料限制

透過目前 Provider 直接下載時，只能列出「今天仍存在」的 contracts；系統會把這種資料集標為 `CURRENT_SNAPSHOT`／探索性，並禁止它得到 `RESEARCH_PASS`，避免把 survivorship bias 當成正式勝率證據。要驗證「近三年所有當時可交易的台股」，必須先匯入含 date-effective 上市／下市、商品類型、交易日與調整／參考價資訊的資料集，並將其登錄為 `DATE_EFFECTIVE`。系統已保留這種 immutable import contract；沒有這些歷史 universe 資料時，網頁仍可執行回測，但結果只能用於探索，不能宣稱涵蓋完整市場。

完整資料由受控的 server-side JSONL 匯入，不從瀏覽器上傳。每行必須是 `HistoricalBar.to_dict()` 的 JSON；資料經過 OHLC、時區、重複列與 SHA-256 驗證後，才會出現在網頁的資料集選單：

```bash
python scripts/import_backtest_dataset.py \
  --bars /secure-data/twse_tpex_2023_2026_1m.jsonl \
  --source twse-tpex-date-effective-v1 \
  --universe-scope DATE_EFFECTIVE \
  --research-eligible
```

---

## 切換至 Shioaji 真實資料

編輯 `.env` 或 `config/settings.py`：

```env
PROVIDER=shioaji
SHIOAJI_API_KEY=your_key
SHIOAJI_SECRET=your_secret
```

---

## 手動觀察清單

編輯 `config/settings.py`：

```python
MANUAL_WATCHLIST = {
    "2376",
    "3231",
}
```

手動加入的股票**永遠進入 Candidate Pool**，不會被自動掃描移除。

---

## 持倉管理

掃描結果目前仍在 `app.py` 直接設定一筆示範持倉，用於既有出場規則展示：

```python
position_manager.add(Position(symbol="2317", entry_price=205.0, quantity=1000))
```

Web 的「模擬持倉」與這筆示範資料分開，完全由 `simulation/` 中已成交的本機紙上委託推導。後續策略自動下單應呼叫同一個 `SimulationService.submit_order()` 指令入口，而非由瀏覽器或策略程式直接操作券商 SDK。

---

## 執行測試

```bash
python3 -m pytest tests/ -v
```

---

## 專案結構

```text
tw_intraday_trader/
├── app.py                  # Orchestration layer（主程式）
├── market_data/
│   ├── models.py           # StockData
│   └── provider.py         # Snapshot、Kbar 與 Shioaji Tick/BidAsk adapter
├── candidate/
│   ├── models.py           # Candidate
│   ├── rules.py            # GapUpRule, HighVolumeRule
│   └── engine.py           # CandidateEngine
├── scoring/
│   ├── models.py           # ScoreDetail, BuyScoreResult
│   ├── rules.py            # AboveVWAPRule, GapScoreRule
│   └── engine.py           # BuyScoreEngine
├── position/
│   ├── models.py           # Position
│   ├── manager.py          # PositionManager
│   └── exit_rules.py       # StopLossRule, TakeProfitRule
├── config/
│   └── settings.py         # 所有 threshold 與設定
├── simulation/
│   └── service.py          # 本機紙上模擬委託與持倉投影
├── strategy_catalog/
│   ├── domain.py           # 統一策略定義、角色、時段、狀態與版本摘要
│   └── service.py          # 內建策略 bootstrap、查詢與版本化保存
└── tests/                  # 單元測試
```

---

## 架構原則

1. 其他模組禁止直接依賴 Shioaji SDK，透過 `MarketDataProvider` 隔離
2. Candidate ≠ 買入訊號，只代表「值得監控」
3. Manual Watchlist 的股票不可被自動掃描移除
4. Position 永遠持續監控（即使不在 Candidate Pool）
5. 評分必須提供 breakdown，不只回傳一個數字
6. 系統級安全與資料設定集中在 `config/`；策略 threshold 隨版本保存在 `strategy_catalog` 定義中
7. 網頁紙上模擬與未來策略程式共用後端下單指令；Shioaji 只提供行情，目前不包含 Shioaji 或真實帳戶下單
