# 台股即時選股與交易決策系統 — MVP 架構報告

## 1. 專案目標

建立一個台股盤中即時決策系統，主要用途是：

1. 從全市場找出值得觀察的股票。
2. 允許使用者手動加入自己想觀察的股票。
3. 對候選股票進行買入評分。
4. 允許使用者登記目前持有的股票與成本。
5. 持續監控持倉，提供停利 / 停損 / Exit 建議。
6. 未來可以逐步新增不同的選股策略、評分策略與出場策略。

MVP 第一版的核心原則：

> 找誰 → 值不值得買 → 買了之後何時離場

第一版以「容易理解、容易修改」為優先，不建立複雜的量化研究平台、事件系統、微服務或 AI/ML 模型。

---

# 2. 核心概念

系統分成三個主要決策階段。

## 2.1 Candidate Logic Pool — 選股邏輯池

回答：

> 哪些股票值得進入觀察名單？

例如：

- 開盤跳空 2% ~ 4%
- 成交量異常放大
- 成交金額排行
- 突破昨日高點
- 振幅放大
- 使用者手動加入

Candidate Logic 的結果不是「買入」。

只是代表：

> 這檔股票值得進一步監控。

---

## 2.2 Buy Score Logic Pool — 買股評分邏輯池

回答：

> 已經進入候選池的股票，現在有多值得買？

例如：

- Price > VWAP：+20
- Volume Ratio > 2：+15
- 突破第一根 5 分 K 高點：+20
- Momentum 強：+15
- Spread 合理：+10

最後產生：

```text
Buy Score: 0 ~ 100
```

例如：

```text
3231 緯創

Buy Score: 78

+20 Gap
+20 VWAP
+18 Volume
+20 Momentum
```

---

## 2.3 Exit Logic Pool — 出場邏輯池

回答：

> 已經持有股票後，什麼時候應該退出？

MVP 第一版只需要：

- Stop Loss
- Take Profit

未來再增加：

- 跌破 VWAP
- Momentum Reverse
- Trailing Stop
- Opening Range Breakdown
- 成交量衰退
- 其他 Exit Strategy

---

# 3. MVP 整體資料流程

```text
                 Shioaji
                    │
                    ↓
             MarketDataProvider
                    │
                    ↓
                 StockData
                    │
          ┌─────────┴─────────┐
          │                   │
          ↓                   ↓
 Candidate Engine       Manual Watchlist
          │                   │
          └─────────┬─────────┘
                    ↓
              Candidate Pool
                    ↓
             Buy Score Engine
                    ↓
               Score 0~100
                    ↓
             Terminal / API
                    │
                    │ 使用者決定是否買入
                    ↓
             Position Manager
                    ↓
                Exit Rules
                    ↓
             HOLD / EXIT
```

---

# 4. MVP 專案結構

第一版保持簡單。

```text
tw_intraday_trader/
│
├── app.py
│
├── market_data/
│   ├── provider.py
│   └── models.py
│
├── candidate/
│   ├── engine.py
│   └── rules.py
│
├── scoring/
│   ├── engine.py
│   └── rules.py
│
├── position/
│   ├── manager.py
│   └── exit_rules.py
│
├── config/
│   └── settings.py
│
└── tests/
```

以下資料夾可以等未來真的需要時再加入：

```text
features/
strategies/
backtest/
execution/
alerts/
dashboard/
```

第一版不要先建立複雜抽象。

---

# 5. Market Data Layer

## 5.1 目的

封裝 Shioaji。

Candidate / Scoring / Position 模組禁止直接依賴 Shioaji SDK。

其他模組只應該認識系統自己的 `StockData`。

這樣未來可以把資料來源換成：

```text
Shioaji
歷史 Parquet
Replay
其他券商 API
```

而不需要修改策略邏輯。

---

## 5.2 StockData

第一版可以先定義：

```python
from dataclasses import dataclass


@dataclass
class StockData:
    symbol: str
    name: str

    price: float
    open: float
    high: float
    low: float

    previous_close: float

    volume: int
    previous_day_volume: int

    vwap: float | None = None
```

未來再視需求增加：

```text
bid
ask
spread
first_5m_open
first_5m_high
first_5m_low
first_5m_close
first_5m_volume
amount
ma5
ma20
atr
...
```

---

## 5.3 Provider Interface

```python
class MarketDataProvider:

    def get_stock(self, symbol: str) -> StockData:
        raise NotImplementedError

    def get_market_stocks(self) -> list[StockData]:
        raise NotImplementedError
```

正式版本：

```python
class ShioajiProvider(MarketDataProvider):
    ...
```

未來 Replay：

```python
class ReplayProvider(MarketDataProvider):
    ...
```

---

# 6. Candidate Engine

Candidate Engine 負責執行所有「選股邏輯」。

## 6.1 Rule Interface

```python
class CandidateRule:

    name: str

    def match(self, stock: StockData) -> bool:
        raise NotImplementedError
```

---

## 6.2 Example：Gap Up

```python
class GapUpRule(CandidateRule):

    name = "gap_up"

    def match(self, stock: StockData) -> bool:
        gap_pct = (
            (stock.open - stock.previous_close)
            / stock.previous_close
            * 100
        )

        return 2 <= gap_pct <= 4
```

---

## 6.3 Example：High Volume

```python
class HighVolumeRule(CandidateRule):

    name = "high_volume"

    def match(self, stock: StockData) -> bool:
        return stock.volume >= 100_000
```

實際 threshold 後續應移到 config。

---

## 6.4 Candidate Model

```python
from dataclasses import dataclass, field


@dataclass
class Candidate:
    stock: StockData

    source: str

    matched_rules: list[str] = field(
        default_factory=list
    )
```

`source` 第一版：

```text
AUTO
MANUAL
```

未來可以增加：

```text
POSITION
NEWS
USER_STRATEGY
```

---

## 6.5 Candidate Engine

第一版規則：

> 符合任一 Candidate Rule 即可進 Candidate Pool。

```python
class CandidateEngine:

    def __init__(self, rules):
        self.rules = rules

    def scan(
        self,
        stocks: list[StockData],
    ) -> list[Candidate]:

        results = []

        for stock in stocks:

            matched = []

            for rule in self.rules:
                if rule.match(stock):
                    matched.append(rule.name)

            if matched:
                results.append(
                    Candidate(
                        stock=stock,
                        source="AUTO",
                        matched_rules=matched,
                    )
                )

        return results
```

注意：

Candidate 只是「值得看」。

不是 Entry Signal。

---

# 7. Manual Watchlist

使用者必須能加入自己觀察到的股票。

例如：

```text
2376
3231
2603
```

第一版可以直接從 config 讀取：

```python
MANUAL_WATCHLIST = {
    "2376",
    "3231",
}
```

未來 Dashboard 再改成 DB / API 管理。

Manual Watchlist 規則：

```text
使用者手動加入
→ 一定進 Candidate Pool

Candidate Engine
→ 不可以自動移除 Manual 股票
```

合併後：

```text
Auto Candidate
+
Manual Candidate
=
Candidate Pool
```

記得以 symbol 去重。

---

# 8. Buy Score Engine

只對 Candidate Pool 內的股票評分。

不要掃全部市場。

## 8.1 Score Rule

```python
class ScoreRule:

    name: str
    max_score: int

    def score(self, stock: StockData) -> int:
        raise NotImplementedError
```

---

## 8.2 Above VWAP

```python
class AboveVWAPRule(ScoreRule):

    name = "above_vwap"
    max_score = 20

    def score(self, stock: StockData) -> int:

        if stock.vwap is None:
            return 0

        if stock.price > stock.vwap:
            return 20

        return 0
```

---

## 8.3 Gap Score

```python
class GapScoreRule(ScoreRule):

    name = "gap_score"
    max_score = 20

    def score(self, stock: StockData) -> int:

        gap_pct = (
            (stock.open - stock.previous_close)
            / stock.previous_close
            * 100
        )

        if 2 <= gap_pct <= 4:
            return 20

        return 0
```

---

## 8.4 Score Result

不要只回一個數字。

一定要保留明細。

```python
@dataclass
class ScoreDetail:
    rule: str
    score: int
    max_score: int


@dataclass
class BuyScoreResult:
    symbol: str
    total_score: int
    details: list[ScoreDetail]
```

例如：

```text
3231

Buy Score = 72

GapScore       20 / 20
AboveVWAP      20 / 20
HighVolume     17 / 20
Momentum       15 / 20
```

Explainability 從第一版就保留。

---

# 9. Position Manager

Position Manager 管理使用者實際持有的股票。

第一版不需要自動下單。

使用者手動輸入：

```text
Symbol
Entry Price
Quantity
```

---

## 9.1 Position Model

```python
@dataclass
class Position:
    symbol: str
    entry_price: float
    quantity: int
```

---

## 9.2 Position Manager

```python
class PositionManager:

    def __init__(self):
        self.positions = {}

    def add(self, position: Position):
        self.positions[position.symbol] = position

    def remove(self, symbol: str):
        self.positions.pop(symbol, None)

    def get(self, symbol: str):
        return self.positions.get(symbol)

    def get_all(self):
        return list(self.positions.values())
```

Position 股票永遠必須持續監控。

即使它：

```text
不在 Candidate Pool
不在 Market Scanner
Buy Score 很低
```

都不可以停止監控。

---

# 10. Exit Rules

第一版只做最容易理解的兩個。

## 10.1 Stop Loss

```python
class StopLossRule:

    def __init__(self, percent: float):
        self.percent = percent

    def should_exit(
        self,
        position: Position,
        stock: StockData,
    ) -> bool:

        pnl_pct = (
            stock.price - position.entry_price
        ) / position.entry_price

        return pnl_pct <= -self.percent
```

例如：

```text
stop_loss = 0.02
```

代表：

```text
-2%
```

---

## 10.2 Take Profit

```python
class TakeProfitRule:

    def __init__(self, percent: float):
        self.percent = percent

    def should_exit(
        self,
        position: Position,
        stock: StockData,
    ) -> bool:

        pnl_pct = (
            stock.price - position.entry_price
        ) / position.entry_price

        return pnl_pct >= self.percent
```

例如：

```text
take_profit = 0.03
```

代表：

```text
+3%
```

---

# 11. app.py

`app.py` 是第一版的 orchestration layer。

它的目的不是放 business logic。

它只負責把模組串起來。

概念：

```python
market = ShioajiProvider()

candidate_engine = CandidateEngine(
    rules=[
        GapUpRule(),
        HighVolumeRule(),
    ]
)

score_engine = BuyScoreEngine(
    rules=[
        GapScoreRule(),
        AboveVWAPRule(),
    ]
)

position_manager = PositionManager()
```

流程：

```python
stocks = market.get_market_stocks()

auto_candidates = candidate_engine.scan(stocks)

manual_candidates = load_manual_candidates(
    stocks
)

candidates = merge_candidates(
    auto_candidates,
    manual_candidates,
)

for candidate in candidates:

    score_result = score_engine.calculate(
        candidate.stock
    )

    print_candidate(
        candidate,
        score_result,
    )

check_positions(
    position_manager,
    market,
)
```

---

# 12. MVP Terminal Output

第一版不做 Dashboard。

Terminal 能清楚看到結果即可。

例如：

```text
=================================================
09:05:00 MARKET SCAN
=================================================

🔥 AUTO CANDIDATES

3231 緯創

Matched:
  ✓ Gap Up
  ✓ High Volume

Buy Score: 78

Score:
  Gap          +20
  VWAP         +20
  Volume       +18
  Momentum     +20


-------------------------------------------------

👀 MANUAL WATCHLIST

2376 技嘉

Buy Score: 61

Score:
  Gap           +0
  VWAP          +20
  Volume        +16
  Momentum      +25


-------------------------------------------------

💰 POSITIONS

2317 鴻海

Entry:     205
Current:   211
Quantity:  1000

PnL:
+2.93%

Exit Decision:
HOLD
```

---

# 13. 第一版明確不做的功能

請不要在 MVP 初版加入：

```text
AI / LLM 選股
Machine Learning
自動下單
微服務
Kafka
Redis
Event Bus
複雜 Feature Registry
Strategy Dependency Graph
YAML Strategy DSL
Strategy Lifecycle
Dashboard
WebSocket Frontend
Notification System
Full Backtest Platform
Statistical Validation Framework
```

原因：

第一版的主要目標是先驗證整體 pipeline 可以工作，而且開發者可以完整理解程式流程。

---

# 14. 但必須保留的擴充邊界

雖然第一版不實作，程式架構不能阻礙下面這些未來需求。

## 14.1 Feature Engine

未來：

```text
Market Data
    ↓
Feature Engine
    ↓
Candidate / Score / Exit
```

統一計算：

```text
VWAP
Gap
Volume Ratio
MA
ATR
Opening Range
Momentum
Order Book Features
```

MVP 先允許 Rule 自己做簡單計算。

等重複計算明顯增加，再抽 Feature Engine。

---

## 14.2 Strategy Config

未來可能希望：

```yaml
name: opening_gap

candidate:
  - gap_pct between [2, 4]
  - first_5m_volume_ratio >= 0.1
```

但 MVP 不需要做 YAML parser。

第一版先用 Python Class。

---

## 14.3 Backtest / Replay

未來 MarketDataProvider 可以增加：

```python
ReplayProvider
```

讓相同 Candidate / Scoring / Exit Logic 可以套用在歷史資料。

因此 Strategy 不可以直接呼叫 Shioaji。

---

## 14.4 Shadow Trading

未來可以加入：

```text
Buy Score >= threshold
↓
產生 Virtual Trade
↓
不實際下單
↓
追蹤策略績效
```

第一版不做。

---

## 14.5 Risk Gate

未來 Buy Score 前可以加入：

```text
Risk / Tradeability Gate
```

例如：

```text
流動性不足
Spread 太大
行情資料 stale
接近漲跌停
市場異常
```

直接禁止 Entry。

第一版保留概念，不實作。

---

## 14.6 Data Health

未來要監控：

```text
CONNECTED
HEALTHY
STALE
DISCONNECTED
RECOVERING
```

資料異常時禁止產生新買入訊號。

第一版不需要。

---

# 15. 未來完整架構方向

MVP 成功後，逐步演進成：

```text
                     Market Data
                          ↓
                     Data Health
                          ↓
                     Candle Builder
                          ↓
                    Feature Engine
                          ↓
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
 Candidate Logic     Buy Score Logic      Exit Logic
       Pool               Pool               Pool
        ↓                 ↓                 ↓
 Candidate Pool        Buy Score        Exit Signal
        ↓
 Subscription Manager
        ↓
 Realtime Monitoring
        ↓
 WAIT / WATCH / READY / ENTER
        ↓
 Position Manager
        ↓
 HOLD / REDUCE / EXIT
```

研究線則為：

```text
Strategy Idea
     ↓
Backtest
     ↓
Statistical Validation
     ↓
Shadow Trading
     ↓
Approved
     ↓
Realtime Strategy
```

---

# 16. 第一階段開發順序

請嚴格依此順序進行。

## Phase 1 — Project Skeleton

建立：

```text
market_data
candidate
scoring
position
config
tests
```

確認程式可以執行。

---

## Phase 2 — Market Data

完成：

```text
StockData
MarketDataProvider
ShioajiProvider
```

至少能取得市場股票資料。

Acceptance：

```text
可以取得 symbol / price / open / previous_close / volume
```

---

## Phase 3 — Candidate Engine

先實作：

```text
GapUpRule
HighVolumeRule
CandidateEngine
```

Acceptance：

```text
可以從市場資料產生 Candidate List
```

---

## Phase 4 — Manual Watchlist

完成：

```text
manual watchlist
AUTO + MANUAL merge
symbol deduplication
```

Acceptance：

```text
手動加入的股票永遠會出現在 Candidate Pool
```

---

## Phase 5 — Buy Score Engine

先實作：

```text
GapScoreRule
AboveVWAPRule
BuyScoreEngine
ScoreDetail
```

Acceptance：

```text
每檔 Candidate 有 0~100 score
並且可以看到 score breakdown
```

---

## Phase 6 — Position Manager

完成：

```text
Position
PositionManager
```

Acceptance：

```text
可以新增 / 刪除 / 取得持倉
```

---

## Phase 7 — Exit Rules

完成：

```text
StopLossRule
TakeProfitRule
```

Acceptance：

```text
Position 可以得到 HOLD / EXIT 判斷
```

---

## Phase 8 — Terminal Integration

完成完整輸出：

```text
Candidates
Manual Watchlist
Buy Score
Positions
Exit Decision
```

到此 MVP 第一版完成。

---

# 17. Testing 最低要求

至少包含：

```text
test_gap_up_rule.py
test_candidate_engine.py
test_buy_score_engine.py
test_position_manager.py
test_exit_rules.py
```

不要第一版就測 Shioaji 網路連線。

核心 business logic 使用 fake `StockData` 測試。

例如：

```python
stock = StockData(
    symbol="TEST",
    name="Test",
    price=103,
    open=103,
    high=105,
    low=102,
    previous_close=100,
    volume=200000,
    previous_day_volume=1000000,
    vwap=102,
)
```

預期：

```text
GapUpRule = True
AboveVWAP = True
```

---

# 18. Coding Principles

開發時遵守以下原則。

## Rule 1

不要過度工程化。

---

## Rule 2

Candidate、Scoring、Exit 必須分開。

---

## Rule 3

Candidate 不等於 Buy Signal。

---

## Rule 4

Manual Watchlist 不可被 Scanner 自動移除。

---

## Rule 5

Position 永遠需要監控。

---

## Rule 6

其他模組不要直接依賴 Shioaji SDK。

透過：

```text
MarketDataProvider
```

隔離。

---

## Rule 7

評分必須提供 breakdown。

不要只回：

```text
score = 72
```

必須能回答：

```text
為什麼是 72？
```

---

## Rule 8

參數不要散落 magic number。

例如：

```python
2 <= gap <= 4
```

後續應逐步搬到 config。

MVP 初期可以接受 hard-code，但同一參數不要重複散落。

---

# 19. 第一版的核心成功條件

MVP 完成時，使用者執行：

```bash
python app.py
```

可以看到類似：

```text
09:05 MARKET SCAN

AUTO

3231
Matched:
- GapUp
- HighVolume

Buy Score: 78


MANUAL

2376

Buy Score: 61


POSITIONS

2317
Entry: 205
Current: 211

PnL: +2.93%

Decision:
HOLD
```

只要做到這一步，就先停止增加架構。

下一階段再開始處理：

```text
Realtime Tick
5m Candle
Feature Engine
更多 Rule
Replay
Backtest
Shadow Trading
Dashboard
Alert
Auto Execution
```

---

# 20. 給開發 LLM 的重要指示

請以「MVP 可理解性」為最高優先級。

不要自行把此架構升級成完整量化平台。

如果發現可以使用更複雜的 pattern，例如：

```text
Repository Pattern
CQRS
Event Sourcing
Kafka
Plugin Framework
Dependency Injection Container
Feature DAG
Rule DSL
Microservices
```

第一版一律不要導入。

只有當現有 MVP 實際遇到問題時才重構。

開發原則：

> Make it work → Make it understandable → Verify it → Then make it extensible.

不要：

> Design everything first.

---

# 21. 最終架構摘要

```text
第一版核心只有：

MarketDataProvider
        ↓
Candidate Engine
        ↓
Candidate Pool
        ↓
Buy Score Engine
        ↓
Recommendation
        ↓
Position Manager
        ↓
Exit Rules
```

搭配：

```text
Manual Watchlist
```

這就是 MVP。

未來才逐步加入：

```text
Feature Engine
Risk Gate
State Machine
Subscription Manager
Data Health
Backtest
Shadow Trading
Strategy Config
Dashboard
Alert
Auto Execution
```

不要在第一版一次實作。
