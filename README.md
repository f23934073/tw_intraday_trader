# 台股即時選股與交易決策系統 MVP

台股盤中即時決策系統，核心流程：

> 找誰 → 值不值得買 → 買了之後何時離場

---

## 快速開始

### 1. 安裝依賴

```bash
# 建立虛擬環境
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 安裝基本依賴
pip install -e ".[dev]"

# 若要使用 Shioaji 真實連線（選填）
pip install -e ".[broker,dev]"
```

### 2. 設定環境變數（選填，使用 Shioaji 才需要）

```bash
cp .env.example .env
# 編輯 .env，填入 SHIOAJI_API_KEY 與 SHIOAJI_SECRET
```

### 3. 執行

```bash
python app.py
```

預設使用 **MockProvider**，不需網路連線，立即可看到輸出。

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

目前版本在 `app.py` 直接設定持倉（示範用）：

```python
position_manager.add(Position(symbol="2317", entry_price=205.0, quantity=1000))
```

未來版本改為互動式輸入或 DB 管理。

---

## 執行測試

```bash
python -m pytest tests/ -v
```

---

## 專案結構

```text
tw_intraday_trader/
├── app.py                  # Orchestration layer（主程式）
├── market_data/
│   ├── models.py           # StockData
│   └── provider.py         # MarketDataProvider / MockProvider / ShioajiProvider
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
└── tests/                  # 單元測試
```

---

## 架構原則

1. 其他模組禁止直接依賴 Shioaji SDK，透過 `MarketDataProvider` 隔離
2. Candidate ≠ 買入訊號，只代表「值得監控」
3. Manual Watchlist 的股票不可被自動掃描移除
4. Position 永遠持續監控（即使不在 Candidate Pool）
5. 評分必須提供 breakdown，不只回傳一個數字
6. 所有 threshold 集中在 `config/settings.py`
