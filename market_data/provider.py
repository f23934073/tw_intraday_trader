"""
Market Data Provider

封裝所有市場資料來源。
其他模組（Candidate / Scoring / Position）禁止直接依賴 Shioaji SDK。
透過 MarketDataProvider 隔離，未來可換成 ReplayProvider 或其他券商 API。
"""

from __future__ import annotations

import os
import random
import json
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from threading import RLock
from time import monotonic, sleep
from typing import TYPE_CHECKING, Callable
from zoneinfo import ZoneInfo

from market_data.models import (
    KBar,
    LocalPaperInstrumentDescriptorV1,
    LocalPaperProductClass,
    RealtimeQuoteUpdate,
    StockData,
)
from premarket.artifacts import canonical_json, sha256_text_digest
from premarket.models import (
    CompletenessStatus,
    ContractIdentity,
    ContractIdentityStatus,
    HistoricalTick,
    NightBar,
    QualificationCapture,
    SessionWindow,
    SourceObservation,
)

if TYPE_CHECKING:
    pass


@dataclass(frozen=True)
class MarketDataUsage:
    """Provider-neutral view of the current market-data traffic allowance."""

    connections: int
    bytes_used: int
    limit_bytes: int
    remaining_bytes: int


class MarketDataLimitReached(RuntimeError):
    """Raised before a historical query would exceed a Provider safety limit."""


class MarketDataTemporarilyUnavailable(RuntimeError):
    """Raised after bounded retries for a transient Provider failure."""


class _RollingRequestLimiter:
    """Small thread-safe rolling-window limiter used by Shioaji Kbar queries."""

    def __init__(
        self,
        *,
        max_calls: int,
        window_seconds: float,
        clock: Callable[[], float] = monotonic,
        sleep: Callable[[float], None] = sleep,
    ) -> None:
        self._max_calls = max_calls
        self._window_seconds = window_seconds
        self._clock = clock
        self._sleep = sleep
        self._calls: deque[float] = deque()
        self._lock = RLock()

    def wait(self) -> None:
        while True:
            with self._lock:
                now = self._clock()
                threshold = now - self._window_seconds
                while self._calls and self._calls[0] <= threshold:
                    self._calls.popleft()
                if len(self._calls) < self._max_calls:
                    self._calls.append(now)
                    return
                delay = self._window_seconds - (now - self._calls[0])
            self._sleep(max(delay, 0.001))


# ---------------------------------------------------------------------------
# Base Interface
# ---------------------------------------------------------------------------


class MarketDataProvider:
    """Market data provider 基礎介面。"""

    def get_stock(self, symbol: str) -> StockData:
        raise NotImplementedError

    def get_stock_identity(self, symbol: str) -> tuple[str, str]:
        """Resolve canonical symbol/name; default providers may use a snapshot."""
        stock = self.get_stock(symbol)
        return stock.symbol, stock.name

    def get_local_paper_instrument_descriptor(
        self,
        symbol: str,
    ) -> LocalPaperInstrumentDescriptorV1 | None:
        """Return cost-policy admission evidence without guessing by symbol."""

        return None

    def get_market_stocks(self) -> list[StockData]:
        raise NotImplementedError

    def supports_kbars(self) -> bool:
        """是否能提供可用於歷史圖表的 Kbar 資料。"""
        return False

    def get_kbars(self, symbol: str, start: date, end: date) -> list[KBar]:
        """取得一個商品在指定日期區間內的 OHLCV Kbar。"""
        raise NotImplementedError

    def market_data_usage(self) -> MarketDataUsage | None:
        """Return traffic usage when the Provider exposes it."""
        return None

    def supports_premarket_context(self) -> bool:
        """Whether this provider can query a TAIFEX night-session candidate."""
        return False

    def get_taifex_night_session(
        self,
        window: SessionWindow,
        contract_alias: str,
    ) -> SourceObservation | None:
        raise NotImplementedError

    def supports_premarket_qualification(self) -> bool:
        return False

    def capture_taifex_night_qualification(
        self,
        window: SessionWindow,
        contract_alias: str,
    ) -> QualificationCapture:
        raise NotImplementedError

    def supports_streaming_quotes(self) -> bool:
        """是否能推送正規化後的 Tick／BidAsk 行情。"""
        return False

    def start_quote_stream(
        self,
        handler: Callable[[RealtimeQuoteUpdate], None],
    ) -> None:
        """註冊即時行情接收端；不支援串流的 Provider 不會被呼叫。"""
        raise NotImplementedError

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        """使 Tick／BidAsk 訂閱集合與 symbols 一致。"""
        raise NotImplementedError

    def stop_quote_stream(self) -> None:
        """停止本 Provider 建立的行情訂閱。"""

    def close(self) -> None:
        """釋放 Provider 持有的外部連線。"""


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

    def __init__(
        self,
        add_noise: bool = False,
        *,
        history_anchor_date: date | None = None,
    ) -> None:
        """
        Args:
            add_noise: 若為 True，每次取得資料時隨機微幅波動，模擬盤中報價更新。
            history_anchor_date: 可注入的 Kbar 基準日，供可重現測試使用。
        """
        self._add_noise = add_noise
        # 以 dict 儲存原始資料，timestamp 在每次取得時動態注入
        self._raw: dict[str, dict] = {d["symbol"]: d for d in _MOCK_STOCKS}
        self._history_anchor_date = history_anchor_date or datetime.now(
            ZoneInfo("Asia/Taipei")
        ).date()

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

    def get_local_paper_instrument_descriptor(
        self,
        symbol: str,
    ) -> LocalPaperInstrumentDescriptorV1:
        if symbol not in self._raw:
            raise KeyError(f"Symbol not found in mock data: {symbol}")
        raw = self._raw[symbol]
        market = str(raw.get("market") or "").strip().upper()
        product_class = (
            LocalPaperProductClass.COMMON_STOCK
            if market in {"TWSE", "TPEX"}
            else LocalPaperProductClass.UNKNOWN
        )
        return LocalPaperInstrumentDescriptorV1(
            symbol=str(raw["symbol"]),
            exchange_raw=market or "UNKNOWN",
            security_type_raw="MOCK_COMMON_STOCK",
            product_category_raw="MOCK_ORDINARY_SHARE",
            normalized_product_class=product_class,
            source_identity=f"mock-contract-catalog-v1:{market}:{raw['symbol']}",
        )

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

    def supports_premarket_context(self) -> bool:
        return True

    def supports_premarket_qualification(self) -> bool:
        return True

    def capture_taifex_night_qualification(
        self,
        window: SessionWindow,
        contract_alias: str,
    ) -> QualificationCapture:
        observation = self.get_taifex_night_session(window, contract_alias)
        ticks = (
            HistoricalTick(window.start, observation.bars[0].open, 5),
            HistoricalTick(window.start + timedelta(minutes=1), observation.bars[1].high, 5),
            HistoricalTick(window.end - timedelta(minutes=2), observation.bars[0].low, 10),
            HistoricalTick(window.end - timedelta(minutes=1), observation.bars[-1].close, 10),
        )
        raw_source_json = canonical_json(
            {
                "source": "MOCK_KBAR_TICK_QUALIFICATION",
                "trading_date": window.trading_date,
                "contract_alias": contract_alias,
                "context_raw_source_digest": observation.raw_source_digest,
                "ticks": tuple(
                    {
                        "timestamp": tick.timestamp,
                        "close": tick.close,
                        "volume": tick.volume,
                    }
                    for tick in ticks
                ),
            }
        )
        return QualificationCapture(
            trading_date=window.trading_date,
            contract_identity=observation.contract_identity,
            bars=observation.bars,
            ticks=ticks,
            captured_at=datetime.now(ZoneInfo("Asia/Taipei")),
            source="MOCK_KBAR_TICK_QUALIFICATION",
            raw_source_digest=sha256_text_digest(raw_source_json),
            raw_source_json=raw_source_json,
        )

    def get_taifex_night_session(
        self,
        window: SessionWindow,
        contract_alias: str,
    ) -> SourceObservation:
        """Return an explicitly qualified deterministic fixture for local UI/tests."""
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        bars = (
            NightBar(
                timestamp=window.start,
                open=Decimal("24000"),
                high=Decimal("24100"),
                low=Decimal("23910"),
                close=Decimal("24050"),
                volume=10,
            ),
            NightBar(
                timestamp=window.end - timedelta(minutes=1),
                open=Decimal("24050"),
                high=Decimal("24220"),
                low=Decimal("24020"),
                close=Decimal("24180"),
                volume=20,
            ),
        )
        raw_source_json = canonical_json(
            {
                "source": "MOCK_FIXTURE",
                "trading_date": window.trading_date,
                "contract_alias": contract_alias,
                "bars": tuple(
                    {
                        "timestamp": bar.timestamp,
                        "open": bar.open,
                        "high": bar.high,
                        "low": bar.low,
                        "close": bar.close,
                        "volume": bar.volume,
                    }
                    for bar in bars
                ),
            }
        )
        return SourceObservation(
            trading_date=window.trading_date,
            contract_identity=ContractIdentity(
                status=ContractIdentityStatus.RESOLVED_AS_OF_QUERY,
                resolution_method="MOCK_QUERY_TIME_ALIAS",
                resolved_contract_code=f"TXF{window.trading_date:%Y%m}",
                delivery_month=f"{window.trading_date:%Y%m}",
            ),
            bars=bars,
            queried_at=now,
            received_at=now,
            provider_reference_price=Decimal("24000"),
            provider_reference_updated_at=window.start,
            provider_reference_source="MOCK_CONTRACT_INFO",
            completeness_status=CompletenessStatus.COMPLETE,
            completeness_evidence=("MOCK_FIXTURE_SESSION_COMPLETE",),
            source="MOCK_FIXTURE",
            raw_source_digest=sha256_text_digest(raw_source_json),
            raw_source_json=raw_source_json,
        )

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
    MAX_STREAMING_SYMBOLS = 100  # 每檔各占 Tick 與 BidAsk，官方總上限 200。
    KBAR_MAX_CALLS_PER_10_SECONDS = 40
    KBAR_REQUEST_WINDOW_SECONDS = 10.0
    KBAR_MIN_REMAINING_BYTES = 16 * 1024 * 1024
    KBAR_REQUEST_TIMEOUT_MS = 60_000
    KBAR_TIMEOUT_ATTEMPTS = 3
    KBAR_TIMEOUT_BACKOFF_SECONDS = (2.0, 5.0)
    STOCK_CONTRACT_READY_SYMBOL = "2330"
    STOCK_CONTRACT_READY_TIMEOUT_SECONDS = 30.0
    STOCK_CONTRACT_READY_POLL_SECONDS = 0.1

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
        self._environment_identity = (
            f"shioaji:{getattr(sj, '__version__', 'unknown')}:"
            f"simulation={str(simulation).lower()}"
        )

        self._api = sj.Shioaji(simulation=simulation)
        try:
            accounts = self._api.login(
                api_key=api_key,
                secret_key=secret,
                subscribe_trade=False,
            )
            self._wait_for_stock_contracts(self._api)
        except Exception:
            try:
                self._api.logout()
            except Exception:
                pass
            raise

        self._stream_lock = RLock()
        self._stream_handler: Callable[[RealtimeQuoteUpdate], None] | None = None
        self._streaming_symbols: set[str] = set()
        self._kbar_request_limiter = _RollingRequestLimiter(
            max_calls=self.KBAR_MAX_CALLS_PER_10_SECONDS,
            window_seconds=self.KBAR_REQUEST_WINDOW_SECONDS,
        )
        self._kbar_timeout_error = sj.ShioajiTimeoutError
        self._kbar_retry_sleep: Callable[[float], None] = sleep

        mode = "模擬盤" if simulation else "正式環境"
        print(f"  [ShioajiProvider] 登入成功（{mode}），帳號數：{len(accounts)}")

    @classmethod
    def _wait_for_stock_contracts(
        cls,
        api: object,
        *,
        timeout_seconds: float | None = None,
        poll_seconds: float | None = None,
        clock: Callable[[], float] = monotonic,
        wait: Callable[[float], None] = sleep,
    ) -> None:
        """Wait for Shioaji's post-login automatic stock catalog load."""

        timeout = (
            cls.STOCK_CONTRACT_READY_TIMEOUT_SECONDS
            if timeout_seconds is None
            else timeout_seconds
        )
        poll = (
            cls.STOCK_CONTRACT_READY_POLL_SECONDS
            if poll_seconds is None
            else poll_seconds
        )
        deadline = clock() + timeout

        while True:
            try:
                stocks = getattr(getattr(api, "Contracts"), "Stocks")
                contract = stocks[cls.STOCK_CONTRACT_READY_SYMBOL]
            except (AttributeError, IndexError, KeyError, TypeError):
                contract = None
            if contract is not None:
                return

            remaining = deadline - clock()
            if remaining <= 0:
                raise RuntimeError(
                    f"Shioaji 股票合約目錄未在 {timeout:g} 秒內就緒"
                )
            wait(min(poll, remaining))

    @property
    def environment_identity(self) -> str:
        """Identify the data environment without exposing credentials."""

        return self._environment_identity

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

    def get_stock_identity(self, symbol: str) -> tuple[str, str]:
        """Resolve a stock from the contract catalog without requiring snapshot I/O."""
        contract = self._stock_contract(symbol)
        return (
            str(getattr(contract, "code", "")).strip().upper(),
            str(getattr(contract, "name", "")).strip(),
        )

    def get_local_paper_instrument_descriptor(
        self,
        symbol: str,
    ) -> LocalPaperInstrumentDescriptorV1:
        """Classify only explicit Shioaji 1.7 stock-catalog raw identities."""

        contract = self._stock_contract(symbol)
        normalized_symbol = str(getattr(contract, "code", "")).strip().upper()
        exchange_raw = self._raw_enum_value(getattr(contract, "exchange", ""))
        security_type_raw = self._raw_enum_value(
            getattr(contract, "security_type", "")
        )
        product_category_raw = str(getattr(contract, "category", "")).strip().upper()
        # Shioaji's STK catalog also contains ETFs.  Admission therefore
        # requires an ordinary-share code plus a reviewed TWSE/TPEX industry
        # category; every unreviewed raw value stays fail-closed.
        ordinary_share_code = len(normalized_symbol) == 4 and normalized_symbol.isdigit()
        twse_common_stock_categories = {
            "01", "02", "03", "04", "05", "06", "08", "09", "10", "11",
            "12", "14", "15", "16", "17", "18", "19", "20", "21", "22",
            "23", "24", "25", "26", "27", "28", "29", "30", "31", "35",
            "36", "37", "38",
        }
        tpex_common_stock_categories = {
            "02", "03", "04", "05", "06", "08", "10", "11", "14", "15",
            "16", "17", "20", "21", "22", "23", "24", "25", "26", "27",
            "28", "29", "30", "31", "32", "33", "35", "36", "37", "38",
        }
        common_stock_category = (
            exchange_raw == "TSE"
            and product_category_raw in twse_common_stock_categories
        ) or (
            exchange_raw == "OTC"
            and product_category_raw in tpex_common_stock_categories
        )
        if (
            security_type_raw == "STK"
            and ordinary_share_code
            and common_stock_category
        ):
            product_class = LocalPaperProductClass.COMMON_STOCK
        elif exchange_raw in {"TSE", "OTC"} and (
            security_type_raw == "WRT"
            or product_category_raw in {"00", "80"}
            or not ordinary_share_code
        ):
            product_class = LocalPaperProductClass.UNSUPPORTED
        else:
            product_class = LocalPaperProductClass.UNKNOWN
        provider_identity = getattr(
            self,
            "_environment_identity",
            "shioaji:contract-catalog",
        )
        return LocalPaperInstrumentDescriptorV1(
            symbol=normalized_symbol,
            exchange_raw=exchange_raw or "UNKNOWN",
            security_type_raw=security_type_raw or "UNKNOWN",
            product_category_raw=product_category_raw or "UNKNOWN",
            normalized_product_class=product_class,
            source_identity=(
                f"{provider_identity}:contracts:{exchange_raw}:"
                f"{security_type_raw}:{product_category_raw}:{normalized_symbol}"
            ),
        )

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

    def supports_streaming_quotes(self) -> bool:
        return True

    def start_quote_stream(
        self,
        handler: Callable[[RealtimeQuoteUpdate], None],
    ) -> None:
        """安裝一次 Tick／BidAsk callback；callback 只做正規化與轉交。"""
        with self._stream_lock:
            if self._stream_handler is not None and self._stream_handler is not handler:
                raise RuntimeError("Shioaji 即時行情接收端已經啟動")
            self._stream_handler = handler

        try:
            self._api.set_on_tick_stk_v1_callback(self._on_tick_stk_v1)
            self._api.set_on_bidask_stk_v1_callback(self._on_bidask_stk_v1)
        except Exception:
            with self._stream_lock:
                self._stream_handler = None
            raise

    def sync_quote_subscriptions(self, symbols: set[str]) -> set[str]:
        """只對持倉／掛單需要的股票維持成對 Tick 與 BidAsk 訂閱。"""
        normalized = {str(symbol).strip().upper() for symbol in symbols if str(symbol).strip()}
        if len(normalized) > self.MAX_STREAMING_SYMBOLS:
            raise ValueError(
                f"Tick＋BidAsk 最多可同時監控 {self.MAX_STREAMING_SYMBOLS} 檔股票"
            )

        with self._stream_lock:
            current = set(self._streaming_symbols)

        for symbol in sorted(current - normalized):
            contract = self._stock_contract(symbol)
            errors: list[Exception] = []
            for quote_type in ("tick", "bid_ask"):
                try:
                    self._api.unsubscribe(contract, quote_type=quote_type)
                except Exception as error:
                    errors.append(error)
            if errors:
                raise RuntimeError(f"無法取消 {symbol} 即時行情訂閱") from errors[0]
            with self._stream_lock:
                self._streaming_symbols.discard(symbol)

        for symbol in sorted(normalized - current):
            contract = self._stock_contract(symbol)
            tick_subscribed = False
            try:
                self._api.subscribe(contract, quote_type="tick")
                tick_subscribed = True
                self._api.subscribe(contract, quote_type="bid_ask")
            except Exception:
                if tick_subscribed:
                    try:
                        self._api.unsubscribe(contract, quote_type="tick")
                    except Exception:
                        pass
                raise
            with self._stream_lock:
                self._streaming_symbols.add(symbol)

        with self._stream_lock:
            return set(self._streaming_symbols)

    def stop_quote_stream(self) -> None:
        """盡力取消本服務建立的訂閱並移除 callbacks。"""
        try:
            self.sync_quote_subscriptions(set())
        finally:
            for clear_callback in (
                self._api.clear_on_tick_stk_v1_callback,
                self._api.clear_on_bidask_stk_v1_callback,
            ):
                try:
                    clear_callback()
                except Exception:
                    pass
            with self._stream_lock:
                self._stream_handler = None

    def close(self) -> None:
        """取消行情 callback 並明確登出，避免 native threads 留到 interpreter 關閉。"""
        try:
            self.stop_quote_stream()
        finally:
            self._api.logout()

    def _stock_contract(self, symbol: str) -> object:
        contract = self._api.Contracts.Stocks[symbol]
        if contract is None:
            raise KeyError(f"Contract not found: {symbol}")
        return contract

    @staticmethod
    def _raw_enum_value(value: object) -> str:
        raw = getattr(value, "value", value)
        return str(raw).strip().upper()

    def _on_tick_stk_v1(self, *callback_args: object) -> None:
        event = callback_args[-1] if callback_args else None
        if event is None or bool(getattr(event, "intraday_odd", False)):
            return
        price = self._positive_float(getattr(event, "close", None))
        if price is None:
            return
        self._dispatch_stream_update(
            RealtimeQuoteUpdate(
                symbol=str(getattr(event, "code", "")).strip().upper(),
                kind="TICK",
                exchange_timestamp=self._stream_timestamp(event),
                received_at=datetime.now(ZoneInfo("Asia/Taipei")),
                last_price=price,
            )
        )

    def _on_bidask_stk_v1(self, *callback_args: object) -> None:
        event = callback_args[-1] if callback_args else None
        if event is None or bool(getattr(event, "intraday_odd", False)):
            return
        raw_suspended = getattr(
            event,
            "suspend",
            getattr(event, "suspended", None),
        )
        bid_price = self._first_positive(getattr(event, "bid_price", None))
        ask_price = self._first_positive(getattr(event, "ask_price", None))
        bid_volume_lots = self._first_non_negative_int(
            getattr(event, "bid_volume", None)
        )
        ask_volume_lots = self._first_non_negative_int(
            getattr(event, "ask_volume", None)
        )
        if bid_price is None and ask_price is None:
            return
        self._dispatch_stream_update(
            RealtimeQuoteUpdate(
                symbol=str(getattr(event, "code", "")).strip().upper(),
                kind="BIDASK",
                exchange_timestamp=self._stream_timestamp(event),
                received_at=datetime.now(ZoneInfo("Asia/Taipei")),
                bid_price=bid_price,
                ask_price=ask_price,
                bid_volume_lots=bid_volume_lots,
                ask_volume_lots=ask_volume_lots,
                suspended=(
                    bool(raw_suspended) if raw_suspended is not None else None
                ),
            )
        )

    def _dispatch_stream_update(self, update: RealtimeQuoteUpdate) -> None:
        if not update.symbol:
            return
        with self._stream_lock:
            handler = self._stream_handler
        if handler is not None:
            handler(update)

    @staticmethod
    def _stream_timestamp(event: object) -> datetime:
        taipei = ZoneInfo("Asia/Taipei")
        value = getattr(event, "datetime", None)
        if isinstance(value, datetime):
            return value.replace(tzinfo=taipei) if value.tzinfo is None else value.astimezone(taipei)
        if isinstance(value, (list, tuple)) and len(value) >= 6:
            parts = [int(part) for part in value[:7]]
            return datetime(*parts, tzinfo=taipei)

        event_date = getattr(event, "date", None)
        event_time = getattr(event, "time", None)
        if isinstance(event_date, date) and isinstance(event_time, time):
            combined = datetime.combine(event_date, event_time)
            return combined.replace(tzinfo=taipei) if combined.tzinfo is None else combined.astimezone(taipei)
        return datetime.now(taipei)

    @classmethod
    def _first_positive(cls, values: object) -> float | None:
        if values is None:
            return None
        try:
            iterator = iter(values)  # type: ignore[arg-type]
        except TypeError:
            return None
        for value in iterator:
            price = cls._positive_float(value)
            if price is not None:
                return price
        return None

    @staticmethod
    def _positive_float(value: object) -> float | None:
        try:
            number = float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return None
        return number if number > 0 else None

    @staticmethod
    def _first_non_negative_int(values: object) -> int | None:
        if values is None:
            return None
        try:
            iterator = iter(values)  # type: ignore[arg-type]
        except TypeError:
            return None
        for value in iterator:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number >= 0:
                return number
        return None

    def supports_kbars(self) -> bool:
        return True

    def supports_premarket_context(self) -> bool:
        return True

    def supports_premarket_qualification(self) -> bool:
        return True

    def capture_taifex_night_qualification(
        self,
        window: SessionWindow,
        contract_alias: str,
    ) -> QualificationCapture:
        observation = self.get_taifex_night_session(window, contract_alias)
        if observation is None:
            raise RuntimeError("TAIFEX qualification contract is unavailable")
        contract, _ = self._futures_contract_and_info(contract_alias)
        if contract is None:
            raise RuntimeError("TAIFEX qualification contract is unavailable")
        self._wait_for_kbar_slot()
        self._guard_kbar_capacity()
        raw_ticks = self._api.ticks(
            contract=contract,
            date=window.trading_date.isoformat(),
            timeout=self.KBAR_REQUEST_TIMEOUT_MS,
        )
        ticks: list[HistoricalTick] = []
        for timestamp, close, volume in zip(
            self._kbar_values(raw_ticks, "ts"),
            self._kbar_values(raw_ticks, "close"),
            self._kbar_values(raw_ticks, "volume"),
        ):
            try:
                tick = HistoricalTick(
                    timestamp=self._kbar_timestamp(timestamp),
                    close=Decimal(str(close)),
                    volume=int(volume),
                )
            except (InvalidOperation, OverflowError, TypeError, ValueError):
                continue
            if window.start <= tick.timestamp < window.end:
                ticks.append(tick)
        ticks.sort(key=lambda item: item.timestamp)
        raw_source_json = canonical_json(
            {
                "source": "SHIOAJI_KBAR_TICK_QUALIFICATION",
                "trading_date": window.trading_date,
                "contract_alias": contract_alias,
                "contract_identity": {
                    "status": observation.contract_identity.status,
                    "resolution_method": observation.contract_identity.resolution_method,
                    "resolved_contract_code": observation.contract_identity.resolved_contract_code,
                    "delivery_month": observation.contract_identity.delivery_month,
                    "last_trading_date": observation.contract_identity.last_trading_date,
                },
                "kbar_payload": (
                    json.loads(observation.raw_source_json)
                    if observation.raw_source_json is not None
                    else None
                ),
                "tick_payload": {
                    field: self._kbar_values(raw_ticks, field)
                    for field in (
                        "ts",
                        "close",
                        "volume",
                        "bid_price",
                        "bid_volume",
                        "ask_price",
                        "ask_volume",
                        "tick_type",
                    )
                },
            }
        )
        return QualificationCapture(
            trading_date=window.trading_date,
            contract_identity=observation.contract_identity,
            bars=observation.bars,
            ticks=tuple(ticks),
            captured_at=datetime.now(ZoneInfo("Asia/Taipei")),
            source="SHIOAJI_KBAR_TICK_QUALIFICATION",
            raw_source_digest=sha256_text_digest(raw_source_json),
            raw_source_json=raw_source_json,
        )

    def get_taifex_night_session(
        self,
        window: SessionWindow,
        contract_alias: str,
    ) -> SourceObservation | None:
        """Query a source candidate without claiming Shioaji Kbars are finalized."""
        contract, info = self._futures_contract_and_info(contract_alias)
        if contract is None:
            return None
        raw_kbars = self._query_contract_kbars(
            contract=contract,
            label=contract_alias,
            start=window.start.date(),
            end=window.end.date(),
        )
        bars = tuple(
            NightBar(
                timestamp=bar.timestamp - timedelta(minutes=1),
                open=Decimal(str(bar.open)),
                high=Decimal(str(bar.high)),
                low=Decimal(str(bar.low)),
                close=Decimal(str(bar.close)),
                volume=bar.volume,
            )
            for bar in self._map_kbars(raw_kbars)
            if window.start < bar.timestamp <= window.end
        )
        now = datetime.now(ZoneInfo("Asia/Taipei"))
        target_code = str(
            getattr(contract, "target_code", "")
            or getattr(info, "target_code", "")
            or ""
        ).strip()
        identity = ContractIdentity(
            status=(
                ContractIdentityStatus.RESOLVED_AS_OF_QUERY
                if target_code
                else ContractIdentityStatus.UNRESOLVED
            ),
            resolution_method=(
                "QUERY_TIME_ALIAS" if target_code else "QUERY_TIME_ALIAS_TARGET_MISSING"
            ),
            resolved_contract_code=target_code or None,
            delivery_month=str(getattr(info, "delivery_month", "") or "") or None,
            last_trading_date=self._contract_date(
                getattr(info, "last_trading_date", None)
            ),
        )
        reference = self._positive_decimal(getattr(info, "reference", None))
        update_date = self._contract_date(getattr(info, "update_date", None))
        updated_at = (
            datetime.combine(update_date, time.min, tzinfo=ZoneInfo("Asia/Taipei"))
            if update_date is not None
            else None
        )
        raw_source_json = canonical_json(
            {
                "source": "SHIOAJI_KBAR",
                "contract_alias": contract_alias,
                "target_code": target_code or None,
                "delivery_month": identity.delivery_month,
                "last_trading_date": identity.last_trading_date,
                "provider_reference": reference,
                "provider_reference_update_date": update_date,
                "query_start": window.start.date(),
                "query_end": window.end.date(),
                "kbars": {
                    field: self._kbar_values(raw_kbars, field)
                    for field in ("ts", "Open", "High", "Low", "Close", "Volume")
                },
            }
        )
        return SourceObservation(
            trading_date=window.trading_date,
            contract_identity=identity,
            bars=bars,
            queried_at=now,
            received_at=now,
            provider_reference_price=reference,
            provider_reference_updated_at=updated_at,
            provider_reference_source="SHIOAJI_CONTRACT_INFO" if reference is not None else None,
            completeness_status=CompletenessStatus.UNKNOWN,
            completeness_evidence=("SHIOAJI_KBAR_FINALIZATION_UNQUALIFIED",),
            source="SHIOAJI_KBAR",
            raw_source_digest=sha256_text_digest(raw_source_json),
            raw_source_json=raw_source_json,
        )

    def _futures_contract_and_info(self, contract_alias: str) -> tuple[object | None, object | None]:
        contracts_api = getattr(self._api, "contracts", None)
        get_contract = getattr(contracts_api, "get", None)
        if callable(get_contract):
            contract = get_contract(contract_alias)
            if contract is None:
                return None, None
            get_info = getattr(contracts_api, "info", None)
            return contract, get_info(contract) if callable(get_info) else contract

        futures = getattr(getattr(self._api, "Contracts", None), "Futures", None)
        if futures is None:
            return None, None
        try:
            contract = futures[contract_alias]
        except (KeyError, TypeError):
            contract = None
        return contract, contract

    @staticmethod
    def _contract_date(value: object) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if isinstance(value, str) and value.strip():
            normalized = value.strip().replace("/", "-")
            try:
                return date.fromisoformat(normalized)
            except ValueError:
                return None
        return None

    @staticmethod
    def _positive_decimal(value: object) -> Decimal | None:
        try:
            number = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return number if number > 0 else None

    def market_data_usage(self) -> MarketDataUsage | None:
        """Normalize Shioaji's usage object without exposing SDK types."""
        raw = self._api.usage()

        def value(field: str) -> int:
            if isinstance(raw, dict):
                return int(raw.get(field, 0) or 0)
            return int(getattr(raw, field, 0) or 0)

        return MarketDataUsage(
            connections=value("connections"),
            bytes_used=value("bytes"),
            limit_bytes=value("limit_bytes"),
            remaining_bytes=value("remaining_bytes"),
        )

    def _wait_for_kbar_slot(self) -> None:
        limiter = getattr(self, "_kbar_request_limiter", None)
        if limiter is None:
            limiter = _RollingRequestLimiter(
                max_calls=self.KBAR_MAX_CALLS_PER_10_SECONDS,
                window_seconds=self.KBAR_REQUEST_WINDOW_SECONDS,
            )
            self._kbar_request_limiter = limiter
        limiter.wait()

    def _guard_kbar_capacity(self) -> None:
        usage = self.market_data_usage()
        if usage is None or usage.limit_bytes <= 0:
            return
        if usage.remaining_bytes <= self.KBAR_MIN_REMAINING_BYTES:
            remaining_mib = usage.remaining_bytes / 1024 / 1024
            limit_mib = usage.limit_bytes / 1024 / 1024
            raise MarketDataLimitReached(
                "Shioaji 歷史行情剩餘流量不足："
                f"剩餘 {remaining_mib:.1f} MiB／上限 {limit_mib:.0f} MiB；"
                "已保留安全緩衝並停止查詢"
            )

    def _is_kbar_timeout(self, error: Exception) -> bool:
        timeout_type = getattr(self, "_kbar_timeout_error", None)
        if isinstance(timeout_type, type) and isinstance(error, timeout_type):
            return True
        # Object-created test providers do not run __init__. Keeping this
        # narrow name fallback also avoids importing the optional SDK globally.
        return type(error).__name__ == "ShioajiTimeoutError"

    def get_kbars(self, symbol: str, start: date, end: date) -> list[KBar]:
        """取得 Shioaji 的原始 Kbar，並維持 SDK 與系統模型的隔離。"""
        if end < start:
            raise ValueError("Kbar 結束日期不可早於開始日期")
        if (end - start).days > 29:
            raise ValueError("Shioaji Kbar 單次查詢最多 30 個日曆日")

        contract = self._api.Contracts.Stocks[symbol]
        if contract is None:
            raise KeyError(f"Contract not found: {symbol}")

        raw_kbars = self._query_contract_kbars(
            contract=contract,
            label=symbol,
            start=start,
            end=end,
        )
        bars = self._map_kbars(raw_kbars)
        if not bars:
            # Shioaji documents empty market-data responses after traffic
            # exhaustion. Recheck immediately so callers cannot persist the
            # response as a successfully completed historical partition.
            self._guard_kbar_capacity()
        return bars

    def _query_contract_kbars(
        self,
        *,
        contract: object,
        label: str,
        start: date,
        end: date,
    ) -> object:
        raw_kbars: object | None = None
        for attempt in range(1, self.KBAR_TIMEOUT_ATTEMPTS + 1):
            self._wait_for_kbar_slot()
            self._guard_kbar_capacity()
            try:
                raw_kbars = self._api.kbars(
                    contract=contract,
                    start=start.isoformat(),
                    end=end.isoformat(),
                    timeout=self.KBAR_REQUEST_TIMEOUT_MS,
                )
                break
            except Exception as error:
                if not self._is_kbar_timeout(error):
                    raise
                if attempt >= self.KBAR_TIMEOUT_ATTEMPTS:
                    raise MarketDataTemporarilyUnavailable(
                        "Shioaji Kbar 查詢逾時："
                        f"{label} {start.isoformat()} 至 {end.isoformat()} "
                        f"已重試 {self.KBAR_TIMEOUT_ATTEMPTS} 次；工作可安全接續"
                    ) from error
                retry_sleep = getattr(self, "_kbar_retry_sleep", sleep)
                retry_sleep(self.KBAR_TIMEOUT_BACKOFF_SECONDS[attempt - 1])

        assert raw_kbars is not None
        return raw_kbars

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
