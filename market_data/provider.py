"""
Market Data Provider

封裝所有市場資料來源。
其他模組（Candidate / Scoring / Position）禁止直接依賴 Shioaji SDK。
透過 MarketDataProvider 隔離，未來可換成 ReplayProvider 或其他券商 API。
"""

from __future__ import annotations

import os
import random
from datetime import date, datetime, time, timedelta, timezone
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from market_data.models import KBar, StockData

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

    def supports_kbars(self) -> bool:
        """是否能提供可用於歷史圖表的 Kbar 資料。"""
        return False

    def get_kbars(self, symbol: str, start: date, end: date) -> list[KBar]:
        """取得一個商品在指定日期區間內的 OHLCV Kbar。"""
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
        self._history_anchor_date = datetime.now(ZoneInfo("Asia/Taipei")).date()

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

    def supports_kbars(self) -> bool:
        return True

    def get_kbars(self, symbol: str, start: date, end: date) -> list[KBar]:
        """提供穩定的模擬 Kbar，供本機儀表板與測試使用。"""
        if symbol not in self._raw:
            raise KeyError(f"Symbol not found in mock data: {symbol}")
        if end < start:
            raise ValueError("Kbar 結束日期不可早於開始日期")

        data = self._raw[symbol]
        if start == end:
            return self._mock_intraday_kbars(data, start)

        bars: list[KBar] = []
        for offset in range((end - start).days + 1):
            bar_date = start + timedelta(days=offset)
            if bar_date.weekday() < 5:
                bars.append(
                    self._mock_daily_kbar(
                        data,
                        bar_date,
                        self._history_anchor_date,
                    )
                )
        return bars

    @staticmethod
    def _mock_daily_kbar(data: dict, bar_date: date, end: date) -> KBar:
        """建立一根與目前 Mock 快照一致的模擬日 K。"""
        days_ago = (end - bar_date).days
        price = float(data["price"])
        variation = 0.0 if days_ago == 0 else ((bar_date.toordinal() % 5) - 2) * 0.0009
        close = price if days_ago == 0 else round(price * (1 - days_ago * 0.0016 + variation), 2)
        open_price = round(close * (1 + ((bar_date.toordinal() % 4) - 1.5) * 0.0018), 2)
        span = max(price * 0.006, 0.5)
        high = round(max(open_price, close) + span * 0.55, 2)
        low = round(min(open_price, close) - span * 0.55, 2)
        volume = int(data["volume"] * (0.65 + (bar_date.toordinal() % 4) * 0.12))
        return KBar(
            timestamp=datetime.combine(
                bar_date,
                time(13, 30),
                tzinfo=ZoneInfo("Asia/Taipei"),
            ),
            open=open_price,
            high=high,
            low=low,
            close=close,
            volume=volume,
        )

    @classmethod
    def _mock_intraday_kbars(cls, data: dict, bar_date: date) -> list[KBar]:
        """建立 5 分鐘的模擬盤中 Kbar；僅供 MockProvider 顯示用途。"""
        daily = cls._mock_daily_kbar(data, bar_date, bar_date)
        bar_count = 54
        interval = timedelta(minutes=5)
        timestamp = datetime.combine(
            bar_date,
            time(9, 0),
            tzinfo=ZoneInfo("Asia/Taipei"),
        )
        previous_close = daily.open
        span = max(daily.high - daily.low, 0.5)
        bars: list[KBar] = []

        for index in range(bar_count):
            progress = (index + 1) / bar_count
            trend_close = daily.open + (daily.close - daily.open) * progress
            wobble = ((index % 7) - 3) * span * 0.035
            close = daily.close if index == bar_count - 1 else round(trend_close + wobble, 2)
            high = round(max(previous_close, close) + span * 0.04, 2)
            low = round(min(previous_close, close) - span * 0.04, 2)
            bars.append(
                KBar(
                    timestamp=timestamp + interval * index,
                    open=previous_close,
                    high=high,
                    low=low,
                    close=close,
                    volume=max(1, int(daily.volume / bar_count * (0.75 + (index % 5) * 0.1))),
                )
            )
            previous_close = close

        return bars


# ---------------------------------------------------------------------------
# Shioaji Provider（正式連線）
# ---------------------------------------------------------------------------


class ShioajiProvider(MarketDataProvider):
    """
    使用 Shioaji SDK 的正式市場資料 Provider。
    需要安裝 optional dependency: pip install tw-intraday-trader[broker]

    環境變數設定（可放在 .env）：
        SHIOAJI_API_KEY — Shioaji API Key（或舊版 SJ_API_KEY）
        SHIOAJI_SECRET  — Shioaji Secret Key（或舊版 SJ_SECRET_KEY / SJ_SEC_KEY）
        SJ_SIMULATION   — 'true' 為模擬盤（預設），'false' 為正式環境
    """

    SNAPSHOT_BATCH_SIZE = 500

    def __init__(self) -> None:
        try:
            import shioaji as sj  # type: ignore[import]
        except ImportError as e:
            raise ImportError(
                "shioaji 未安裝。請執行：pip install tw-intraday-trader[broker]"
            ) from e

        api_key = (
            os.environ.get("SHIOAJI_API_KEY", "")
            or os.environ.get("SJ_API_KEY", "")
        )
        secret = (
            os.environ.get("SHIOAJI_SECRET", "")
            or os.environ.get("SJ_SECRET_KEY", "")
            or os.environ.get("SJ_SEC_KEY", "")
        )

        if not api_key or not secret:
            raise ValueError(
                "請設定環境變數 SHIOAJI_API_KEY 與 SHIOAJI_SECRET，"
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
        total_volume = getattr(snap, "total_volume", 0) or 0
        yesterday_volume = getattr(snap, "yesterday_volume", 0) or 0
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
            # Shioaji 的 volume 是單筆 Tick 量；選股需要日內累積量。
            volume=int(total_volume),
            previous_day_volume=int(yesterday_volume),
            # Snapshot 提供 average_price，可作為日內 VWAP 使用。
            vwap=getattr(snap, "average_price", None),
            # 這是 total_volume / yesterday_volume，並非過去 N 日同期 RVOL。
            relative_volume=getattr(snap, "volume_ratio", None),
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
        """取得 TSE 與 OTC 股票快照，按 Shioaji 限制分批查詢。"""
        contracts = [
            contract
            for exchange_contracts in (
                self._api.Contracts.Stocks.TSE,
                self._api.Contracts.Stocks.OTC,
            )
            for contract in exchange_contracts
            if contract is not None
        ]
        if not contracts:
            return []

        results: list[StockData] = []

        for start in range(0, len(contracts), self.SNAPSHOT_BATCH_SIZE):
            batch = contracts[start:start + self.SNAPSHOT_BATCH_SIZE]
            snapshots = self._api.snapshots(batch)

            for snap, contract in zip(snapshots, batch):
                try:
                    stock = self._snap_to_stock(snap, contract)
                    if stock.price > 0:  # 過濾無效報價（收盤或停止交易）
                        results.append(stock)
                except Exception:
                    # 跳過個別股票資料異常，不影響整體掃描
                    continue

        return results

    def supports_kbars(self) -> bool:
        return True

    def get_kbars(self, symbol: str, start: date, end: date) -> list[KBar]:
        """取得 Shioaji 的原始 Kbar，並維持 SDK 與系統模型的隔離。"""
        if end < start:
            raise ValueError("Kbar 結束日期不可早於開始日期")
        if (end - start).days > 29:
            raise ValueError("Shioaji Kbar 單次查詢最多 30 個日曆日")

        contract = self._api.Contracts.Stocks[symbol]
        if contract is None:
            raise KeyError(f"Contract not found: {symbol}")

        raw_kbars = self._api.kbars(
            contract=contract,
            start=start.isoformat(),
            end=end.isoformat(),
        )
        return self._map_kbars(raw_kbars)

    @staticmethod
    def _kbar_values(kbars: object, field: str) -> list[object]:
        if isinstance(kbars, dict):
            values = kbars.get(field, kbars.get(field.lower(), []))
        else:
            values = getattr(kbars, field, getattr(kbars, field.lower(), []))
        return list(values or [])

    @classmethod
    def _map_kbars(cls, raw_kbars: object) -> list[KBar]:
        timestamps = cls._kbar_values(raw_kbars, "ts")
        opens = cls._kbar_values(raw_kbars, "Open")
        highs = cls._kbar_values(raw_kbars, "High")
        lows = cls._kbar_values(raw_kbars, "Low")
        closes = cls._kbar_values(raw_kbars, "Close")
        volumes = cls._kbar_values(raw_kbars, "Volume")

        bars: list[KBar] = []
        for timestamp, open_price, high, low, close, volume in zip(
            timestamps,
            opens,
            highs,
            lows,
            closes,
            volumes,
        ):
            try:
                bars.append(
                    KBar(
                        timestamp=cls._kbar_timestamp(timestamp),
                        open=float(open_price),
                        high=float(high),
                        low=float(low),
                        close=float(close),
                        volume=int(volume),
                    )
                )
            except (OverflowError, TypeError, ValueError):
                continue

        return sorted(bars, key=lambda bar: bar.timestamp)

    @staticmethod
    def _kbar_timestamp(value: object) -> datetime:
        taipei = ZoneInfo("Asia/Taipei")
        if isinstance(value, datetime):
            return value.replace(tzinfo=taipei) if value.tzinfo is None else value.astimezone(taipei)

        timestamp = float(value)
        if abs(timestamp) >= 10_000_000_000_000:
            timestamp /= 1_000_000_000
        elif abs(timestamp) >= 10_000_000_000:
            timestamp /= 1_000
        # Shioaji numeric Kbar ts encodes Taiwan market wall time.  Do not
        # convert it from UTC, or a 09:01 Kbar becomes 17:01 in the dashboard.
        source_wall_time = datetime.fromtimestamp(timestamp, tz=timezone.utc)
        return source_wall_time.replace(tzinfo=taipei)
