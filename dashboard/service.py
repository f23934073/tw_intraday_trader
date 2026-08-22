"""將既有掃描結果轉為瀏覽器可讀的唯讀快照。"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from typing import Any, Callable
from zoneinfo import ZoneInfo

from app import ScanResult, run_scan
from config import settings
from market_data.models import KBar, StockData
from market_data.provider import MarketDataProvider
from premarket.service import PremarketContextService


_TAIPEI = ZoneInfo("Asia/Taipei")
_HISTORY_QUERY_MAX_DAYS = 29
_HISTORY_PERIODS = {
    "1d": {"label": "1日", "calendar_days": 0, "resolution": "5分鐘", "limit": 80},
    "5d": {"label": "5日", "calendar_days": 9, "resolution": "日", "limit": 5},
    "20d": {"label": "20日", "calendar_days": 29, "resolution": "日", "limit": 20},
    "3m": {
        "label": "3月",
        "calendar_days": 190,
        "resolution": "日",
        "limit": 65,
        "moving_average_windows": (5, 20, 60),
    },
}


class DashboardService:
    """保存最近一次掃描快照；只有明確 refresh 才會再次查詢 Provider。"""

    def __init__(
        self,
        provider: MarketDataProvider,
        *,
        premarket_service: PremarketContextService | None = None,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._provider = provider
        self._premarket_service = premarket_service
        self._now = now or (lambda: datetime.now(_TAIPEI))
        self._latest_snapshot: dict[str, Any] | None = None
        self._history_cache: dict[tuple[str, str], dict[str, Any]] = {}

    def snapshot(self) -> dict[str, Any]:
        """取得快取快照；第一次讀取時才建立初始快照。"""
        if self._latest_snapshot is None:
            return self.refresh()
        return self._latest_snapshot

    def refresh(self) -> dict[str, Any]:
        """明確執行一次掃描並更新快照，不含任何交易操作。"""
        self._latest_snapshot = build_dashboard_snapshot(run_scan(self._provider))
        if self._premarket_service is not None:
            self._latest_snapshot["premarket_context"] = (
                self._premarket_service.projection()
            )
        self._history_cache.clear()
        return self._latest_snapshot

    def realtime_candidate_snapshot(self) -> dict[str, Any]:
        """取得即時策略候選池，不變更主畫面快照或盤前 artifact。"""
        return {"candidates": build_dashboard_snapshot(run_scan(self._provider))["candidates"]}

    def provider_usage(self) -> dict[str, Any]:
        """回傳目前 Provider 的行情流量狀態，不額外查詢行情。"""
        usage = self._provider.market_data_usage()
        provider = type(self._provider).__name__
        if usage is None:
            return {
                "provider": provider,
                "supported": False,
                "exhausted": False,
                "connections": None,
                "bytes_used": None,
                "limit_bytes": None,
                "remaining_bytes": None,
            }

        exhausted = usage.limit_bytes > 0 and (
            usage.remaining_bytes <= 0 or usage.bytes_used >= usage.limit_bytes
        )
        return {
            "provider": provider,
            "supported": True,
            "exhausted": exhausted,
            "connections": usage.connections,
            "bytes_used": usage.bytes_used,
            "limit_bytes": usage.limit_bytes,
            "remaining_bytes": usage.remaining_bytes,
        }

    def candidate_history(self, symbol: str, period: str) -> dict[str, Any]:
        """按需取得目前 Candidate 的來源 Kbar，不在全市場掃描時預先查詢。"""
        if period not in _HISTORY_PERIODS:
            raise ValueError(f"不支援的 Kbar 週期：{period}")

        snapshot = self.snapshot()
        if symbol not in {candidate["symbol"] for candidate in snapshot["candidates"]}:
            raise KeyError(f"目前 Candidate 清單沒有：{symbol}")

        cache_key = (symbol, period)
        if cache_key in self._history_cache:
            return self._history_cache[cache_key]

        spec = _HISTORY_PERIODS[period]
        end = self._now().astimezone(_TAIPEI).date()
        start = end - timedelta(days=spec["calendar_days"])
        payload: dict[str, Any] = {
            "symbol": symbol,
            "period": period,
            "label": spec["label"],
            "resolution": spec["resolution"],
            "start": start.isoformat(),
            "end": end.isoformat(),
            "source": type(self._provider).__name__,
            "status": "unavailable",
            "display_start": None,
            "display_end": None,
            "candles": [],
        }

        if self._provider.supports_kbars():
            bars = _fetch_history_bars(self._provider, symbol, start, end)
            aggregated = _aggregate_history(bars, period)
            candles = aggregated[-spec["limit"]:]
            moving_averages = _moving_averages(
                aggregated,
                spec.get("moving_average_windows", ()),
            )
            payload["status"] = "ready" if candles else "empty"
            if candles:
                payload["display_start"] = candles[0].timestamp.date().isoformat()
                payload["display_end"] = candles[-1].timestamp.date().isoformat()
            payload["candles"] = [
                _kbar_payload(bar, moving_averages.get(bar.timestamp))
                for bar in candles
            ]

        self._history_cache[cache_key] = payload
        return payload


def build_dashboard_snapshot(result: ScanResult) -> dict[str, Any]:
    """序列化共享 ScanResult，避免網頁重新計算規則或損益。"""
    return {
        "generated_at": result.generated_at.isoformat(),
        "provider": {
            "name": result.provider_name,
            "mode": "snapshot",
            "streaming": False,
        },
        "market": {
            "loaded_symbols": result.loaded_symbols,
            "missing_candidate_symbols": result.missing_candidate_symbols,
            "missing_position_symbols": result.missing_position_symbols,
        },
        "candidates": [
            {
                "symbol": evaluation.candidate.symbol,
                "sources": sorted(source.value for source in evaluation.candidate.sources),
                "matched_rules": evaluation.candidate.matched_rules,
                "stock": _stock_payload(evaluation.stock),
                "score": {
                    "total": evaluation.score_result.total_score,
                    "max": sum(
                        detail.max_score for detail in evaluation.score_result.details
                    ),
                    "details": [
                        {
                            "rule": detail.rule,
                            "score": detail.score,
                            "max_score": detail.max_score,
                        }
                        for detail in evaluation.score_result.details
                    ],
                },
            }
            for evaluation in result.candidates
        ],
        "positions": [
            {
                "symbol": evaluation.position.symbol,
                "entry_price": evaluation.position.entry_price,
                "quantity": evaluation.position.quantity,
                "current_price": evaluation.stock.price,
                "pnl_pct": evaluation.pnl_pct,
                "pnl_amount": evaluation.pnl_amount,
                "stock": _stock_payload(evaluation.stock),
                "exit": {
                    "decision": (
                        "EXIT" if evaluation.triggered_exit_rules else "HOLD"
                    ),
                    "triggered_rules": evaluation.triggered_exit_rules,
                    "stop_price": round(
                        evaluation.position.entry_price
                        * (1 - settings.STOP_LOSS_PCT),
                        2,
                    ),
                    "take_profit_price": round(
                        evaluation.position.entry_price
                        * (1 + settings.TAKE_PROFIT_PCT),
                        2,
                    ),
                },
            }
            for evaluation in result.positions
        ],
    }


def _stock_payload(stock: StockData) -> dict[str, Any]:
    return {
        "symbol": stock.symbol,
        "name": stock.name,
        "timestamp": stock.timestamp.isoformat(),
        "price": stock.price,
        "open": stock.open,
        "high": stock.high,
        "low": stock.low,
        "previous_close": stock.previous_close,
        "volume": stock.volume,
        "previous_day_volume": stock.previous_day_volume,
        "vwap": stock.vwap,
        "relative_volume": stock.relative_volume,
        "market": stock.market,
    }


def _fetch_history_bars(
    provider: MarketDataProvider,
    symbol: str,
    start: date,
    end: date,
) -> list[KBar]:
    """分段取得來源 Kbar，確保每次呼叫符合 Provider 的區間限制。"""
    cursor = start
    bars_by_timestamp: dict[datetime, KBar] = {}

    while cursor <= end:
        window_end = min(cursor + timedelta(days=_HISTORY_QUERY_MAX_DAYS), end)
        for bar in provider.get_kbars(symbol, cursor, window_end):
            bars_by_timestamp[bar.timestamp] = bar
        cursor = window_end + timedelta(days=1)

    return [bars_by_timestamp[timestamp] for timestamp in sorted(bars_by_timestamp)]


def _aggregate_history(bars: list[KBar], period: str) -> list[KBar]:
    """將 Provider 回傳的 OHLCV 依 UI 週期聚合，保留來源欄位的實際含義。"""
    if period == "1d":
        return _aggregate_kbars(
            bars,
            lambda timestamp: timestamp.replace(
                minute=timestamp.minute - timestamp.minute % 5,
                second=0,
                microsecond=0,
            ),
        )

    return _aggregate_kbars(
        bars,
        lambda timestamp: datetime.combine(
            timestamp.date(),
            time.min,
            tzinfo=timestamp.tzinfo,
        ),
    )


def _aggregate_kbars(
    bars: list[KBar],
    bucket_for_timestamp: Callable[[datetime], datetime],
) -> list[KBar]:
    aggregated: dict[datetime, KBar] = {}
    for bar in sorted(bars, key=lambda item: item.timestamp):
        bucket = bucket_for_timestamp(bar.timestamp)
        existing = aggregated.get(bucket)
        if existing is None:
            aggregated[bucket] = KBar(
                timestamp=bucket,
                open=bar.open,
                high=bar.high,
                low=bar.low,
                close=bar.close,
                volume=bar.volume,
            )
            continue

        aggregated[bucket] = KBar(
            timestamp=bucket,
            open=existing.open,
            high=max(existing.high, bar.high),
            low=min(existing.low, bar.low),
            close=bar.close,
            volume=existing.volume + bar.volume,
        )

    return list(aggregated.values())


def _moving_averages(
    bars: list[KBar],
    windows: tuple[int, ...],
) -> dict[datetime, dict[str, float | None]]:
    """以來源日 K 收盤價計算 SMA；不足窗口時明確回傳空值。"""
    if not windows:
        return {}

    closes = [bar.close for bar in bars]
    values: dict[datetime, dict[str, float | None]] = {}
    for index, bar in enumerate(bars):
        values[bar.timestamp] = {
            f"ma{window}": (
                round(sum(closes[index - window + 1:index + 1]) / window, 4)
                if index >= window - 1
                else None
            )
            for window in windows
        }
    return values


def _kbar_payload(
    bar: KBar,
    moving_averages: dict[str, float | None] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "timestamp": bar.timestamp.isoformat(),
        "open": bar.open,
        "high": bar.high,
        "low": bar.low,
        "close": bar.close,
        "volume": bar.volume,
    }
    if moving_averages:
        payload.update(moving_averages)
    return payload
