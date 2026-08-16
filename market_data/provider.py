"""
Market Data Provider

封裝所有市場資料來源。
其他模組（Candidate / Scoring / Position）禁止直接依賴 Shioaji SDK。
透過 MarketDataProvider 隔離，未來可換成 ReplayProvider 或其他券商 API。
"""

from __future__ import annotations

import os
import random
from datetime import datetime
from typing import TYPE_CHECKING

from market_data.models import StockData

if TYPE_CHECKING:
    pass


# ---------------------------------------------------------------------------
# Base Interface
# ---------------------------------------------------------------------------


class MarketDataProvider:
    """Market data provider 基礎介面。"""

    def get_stock(self, symbol: str) -> StockData:
        raise NotImplementedError

    def get_market_stocks(self) -> list[StockData]:
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Mock Provider（開發與測試用）
# ---------------------------------------------------------------------------

# 模擬市場資料，不需真實網路連線
# timestamp 由 MockProvider 在取得資料時動態注入（datetime.now()）
_MOCK_STOCKS: list[dict] = [
    {
        "symbol": "3231",
        "name": "緯創",
        "price": 105.5,
        "open": 104.0,
        "high": 106.0,
        "low": 103.5,
        "previous_close": 101.0,
        "volume": 180_000,
        "previous_day_volume": 80_000,
        "vwap": 104.8,
        "market": "TWSE",
    },
    {
        "symbol": "2376",
        "name": "技嘉",
        "price": 215.0,
        "open": 214.0,
        "high": 217.0,
        "low": 213.0,
        "previous_close": 210.0,
        "volume": 95_000,
        "previous_day_volume": 60_000,
        "vwap": 214.5,
        "market": "TWSE",
    },
    {
        "symbol": "2317",
        "name": "鴻海",
        "price": 211.0,
        "open": 207.0,
        "high": 212.5,
        "low": 206.0,
        "previous_close": 205.0,
        "volume": 250_000,
        "previous_day_volume": 150_000,
        "vwap": 209.0,
        "market": "TWSE",
    },
    {
        "symbol": "2330",
        "name": "台積電",
        "price": 980.0,
        "open": 975.0,
        "high": 985.0,
        "low": 970.0,
        "previous_close": 960.0,
        "volume": 300_000,
        "previous_day_volume": 280_000,
        "vwap": 978.0,
        "market": "TWSE",
    },
    {
        "symbol": "2603",
        "name": "長榮",
        "price": 185.0,
        "open": 183.0,
        "high": 186.5,
        "low": 182.0,
        "previous_close": 182.0,
        "volume": 40_000,
        "previous_day_volume": 90_000,
        "vwap": 184.0,
        "market": "TWSE",
    },
]


class MockProvider(MarketDataProvider):
    """
    開發 / 測試用的假資料 Provider。
    不需要任何真實網路連線或帳號。
    """

    def __init__(self, add_noise: bool = False) -> None:
        """
        Args:
            add_noise: 若為 True，每次取得資料時隨機微幅波動，模擬盤中報價更新。
        """
        self._add_noise = add_noise
        # 以 dict 儲存原始資料，timestamp 在每次取得時動態注入
        self._raw: dict[str, dict] = {d["symbol"]: d for d in _MOCK_STOCKS}

    def _build(self, data: dict) -> StockData:
        """從原始 dict 建構 StockData，timestamp 注入當下時間。"""
        return StockData(
            symbol=data["symbol"],
            name=data["name"],
            timestamp=datetime.now(),
            price=data["price"],
            open=data["open"],
            high=data["high"],
            low=data["low"],
            previous_close=data["previous_close"],
            volume=data["volume"],
            previous_day_volume=data["previous_day_volume"],
            vwap=data.get("vwap"),
            market=data.get("market"),
        )

    def _maybe_noisy(self, stock: StockData) -> StockData:
        if not self._add_noise:
            return stock
        noise = random.uniform(-0.005, 0.005)
        return StockData(
            symbol=stock.symbol,
            name=stock.name,
            timestamp=stock.timestamp,
            price=round(stock.price * (1 + noise), 2),
            open=stock.open,
            high=stock.high,
            low=stock.low,
            previous_close=stock.previous_close,
            volume=int(stock.volume * random.uniform(0.95, 1.05)),
            previous_day_volume=stock.previous_day_volume,
            vwap=stock.vwap,
            market=stock.market,
        )

    def get_stock(self, symbol: str) -> StockData:
        if symbol not in self._raw:
            raise KeyError(f"Symbol not found in mock data: {symbol}")
        return self._maybe_noisy(self._build(self._raw[symbol]))

    def get_market_stocks(self) -> list[StockData]:
        return [self._maybe_noisy(self._build(d)) for d in self._raw.values()]


# ---------------------------------------------------------------------------
# Shioaji Provider（正式連線）
# ---------------------------------------------------------------------------


class ShioajiProvider(MarketDataProvider):
    """
    使用 Shioaji SDK 的正式市場資料 Provider。
    需要安裝 optional dependency: pip install tw-intraday-trader[broker]

    環境變數設定（可放在 .env）：
        SJ_API_KEY      — Shioaji API Key
        SJ_SECRET_KEY   — Shioaji Secret Key
        SJ_SIMULATION   — 'true' 為模擬盤（預設），'false' 為正式環境
    """

    def __init__(self) -> None:
        try:
            import shioaji as sj  # type: ignore[import]
        except ImportError as e:
            raise ImportError(
                "shioaji 未安裝。請執行：pip install tw-intraday-trader[broker]"
            ) from e

        api_key = os.environ.get("SJ_API_KEY", "")
        secret = os.environ.get("SJ_SECRET_KEY", "") or os.environ.get("SJ_SEC_KEY", "")

        if not api_key or not secret:
            raise ValueError(
                "請設定環境變數 SJ_API_KEY 與 SJ_SECRET_KEY，"
                "或在 .env 檔案中設定。"
            )

        simulation_str = os.environ.get("SJ_SIMULATION", "true").lower()
        simulation = simulation_str != "false"

        self._api = sj.Shioaji(simulation=simulation)
        accounts = self._api.login(api_key=api_key, secret_key=secret)

        mode = "模擬盤" if simulation else "正式環境"
        print(f"  [ShioajiProvider] 登入成功（{mode}），帳號數：{len(accounts)}")

    def _snap_to_stock(self, snap: object, contract: object) -> StockData:
        """將 Shioaji snapshot + contract 轉為 StockData。"""
        close = getattr(snap, "close", 0.0) or 0.0
        change = getattr(snap, "change_price", 0.0) or 0.0
        exchange = getattr(contract, "exchange", "")
        market = "TPEX" if str(exchange) == "OTC" else "TWSE"

        return StockData(
            symbol=getattr(contract, "code", ""),
            name=getattr(contract, "name", ""),
            timestamp=datetime.now(),
            price=close,
            open=getattr(snap, "open", 0.0) or 0.0,
            high=getattr(snap, "high", 0.0) or 0.0,
            low=getattr(snap, "low", 0.0) or 0.0,
            previous_close=round(close - change, 2),
            volume=getattr(snap, "volume", 0) or 0,
            previous_day_volume=0,  # snapshot 不提供，未來補充
            vwap=None,              # 未來補充
            market=market,
        )

    def get_stock(self, symbol: str) -> StockData:
        """取得單一股票快照。"""
        contract = self._api.Contracts.Stocks[symbol]
        if contract is None:
            raise KeyError(f"Contract not found: {symbol}")

        snapshots = self._api.snapshots([contract])
        if not snapshots:
            raise KeyError(f"Snapshot not found: {symbol}")

        return self._snap_to_stock(snapshots[0], contract)

    def get_market_stocks(self) -> list[StockData]:
        """取得全市場上市股票快照（TSE 上市股票）。"""
        contracts = [
            c for c in self._api.Contracts.Stocks.TSE
            if c is not None
        ]
        if not contracts:
            return []

        snapshots = self._api.snapshots(contracts)
        results: list[StockData] = []

        for snap, contract in zip(snapshots, contracts):
            try:
                stock = self._snap_to_stock(snap, contract)
                if stock.price > 0:  # 過濾無效報價（收盤或停止交易）
                    results.append(stock)
            except Exception:
                # 跳過個別股票資料異常，不影響整體掃描
                continue

        return results
