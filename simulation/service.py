"""本機紙上模擬的共用下單指令與投影服務。"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from queue import Full, Queue
from threading import RLock, Thread
from typing import Any, Callable
from uuid import uuid4
from zoneinfo import ZoneInfo

from market_data.models import (
    LocalPaperInstrumentDescriptorV1,
    LocalPaperProductClass,
    RealtimeQuoteUpdate,
    StockData,
)
from market_data.provider import MarketDataProvider
from runtime.clock import Clock, SystemClock
from simulation.execution_policy import EXECUTABLE_BOOK_MAX_AGE_SECONDS
from simulation.execution_costs import (
    COMMISSION_RATE,
    MINIMUM_COMMISSION_TWD,
    ExecutionSide,
    FillAccountingDecision,
    ReferenceSource,
    SlippageDecision,
    adverse_tick_floor,
    cumulative_commission_for,
    decide_fill_accounting,
    decide_fixed_adverse_slippage,
    is_valid_common_stock_tick,
)
from simulation.models import (
    OrderSide,
    OrderStatus,
    SimulationOrder,
    SimulationPosition,
)
from simulation.settings import LocalPaperSettings, SETTINGS_SCHEMA_V1, SETTINGS_SCHEMA_V2
from trading.exposure import (
    ExecutionReasonCategory,
    ExposureIdentity,
    PositionAction,
    build_legacy_exposure_identity,
)
from trading.risk import OrderCommand


_TAIPEI = ZoneInfo("Asia/Taipei")
_DEFAULT_STARTING_CASH = Decimal("10000000")
_DEFAULT_DAILY_BUY_NOTIONAL = Decimal("2000000")
_DEFAULT_QUOTE_QUEUE_CAPACITY = 1_024
_DEFAULT_PENDING_TIMEOUT_SECONDS = 30
_DEFAULT_ORDER_EXPIRY_SECONDS = 120
_DEFAULT_MAX_RETRY_ATTEMPTS = 3
_LEGACY_ACCOUNT_SCOPE_ID = "local-paper-compat-v1"
_LEGACY_POLICY_FAMILY_ID = "no-overnight-legacy-family-v1"
_LEGACY_SOURCE_SESSION_ID = "simulation-service-direct-v1"
_ACTIVE_ORDER_STATUSES = frozenset(
    {
        OrderStatus.SUBMITTED,
        OrderStatus.PENDING,
        OrderStatus.PARTIALLY_FILLED,
    }
)


def _exact_book_freshness(
    *,
    now: datetime,
    received_at: datetime,
    max_age_seconds: int,
) -> tuple[float, bool]:
    age_seconds = (now - received_at).total_seconds()
    return age_seconds, 0 <= age_seconds <= max_age_seconds


@dataclass
class _QuoteState:
    """合併 snapshot、Tick 與 BidAsk，但分開維持兩條 stream 的順序。"""

    snapshot: StockData | None = None
    last_price: Decimal | None = None
    bid_price: Decimal | None = None
    ask_price: Decimal | None = None
    last_trade_at: datetime | None = None
    book_at: datetime | None = None
    received_at: datetime | None = None
    book_received_at: datetime | None = None
    bid_available_quantity: int | None = None
    ask_available_quantity: int | None = None
    instrument_tradable: bool | None = None


@dataclass(frozen=True)
class _ExecutionDecision:
    reference_price: Decimal
    reference_source: ReferenceSource
    fill_price: Decimal
    slippage: SlippageDecision | None = None


class SimulationValidationError(ValueError):
    """不符合本機紙上模擬下單規則。"""


class SimulationStateError(ValueError):
    """目前委託狀態無法執行要求的操作。"""


class SimulationService:
    """提供瀏覽器與未來策略程式共用的本機紙上模擬指令入口。

    服務狀態只存在 Web process 記憶體中。它刻意不連線至券商帳務或下單 API，
    因此不是 Shioaji Simulation 的替代品。
    """

    mode = "LOCAL_PAPER_SIMULATION"
    label = "本機紙上模擬（非 Shioaji）"

    def __init__(
        self,
        provider: MarketDataProvider,
        starting_cash: Decimal | float | int = _DEFAULT_STARTING_CASH,
        *,
        max_daily_buy_notional: Decimal | float | int = _DEFAULT_DAILY_BUY_NOTIONAL,
        commission_rate: Decimal | float | int | str = Decimal("0"),
        minimum_commission: Decimal | float | int | str = Decimal("0"),
        slippage_bps: Decimal | int | str = Decimal("0"),
        cost_policy_enabled: bool = False,
        quote_queue_capacity: int = _DEFAULT_QUOTE_QUEUE_CAPACITY,
        max_book_age_seconds: int = EXECUTABLE_BOOK_MAX_AGE_SECONDS,
        pending_timeout_seconds: int = _DEFAULT_PENDING_TIMEOUT_SECONDS,
        order_expiry_seconds: int = _DEFAULT_ORDER_EXPIRY_SECONDS,
        max_retry_attempts: int = _DEFAULT_MAX_RETRY_ATTEMPTS,
        clock: Clock | None = None,
        start_streaming: bool = True,
    ) -> None:
        if not isinstance(cost_policy_enabled, bool):
            raise ValueError("cost_policy_enabled 必須是布林值")
        normalized_slippage_bps = self._money(slippage_bps, "slippage_bps")
        if normalized_slippage_bps < 0 or normalized_slippage_bps > 100:
            raise ValueError("slippage_bps 必須介於 0 與 100")
        settings = LocalPaperSettings(
            starting_cash_twd=self._money(starting_cash, "starting_cash"),
            max_daily_buy_notional_twd=self._money(
                max_daily_buy_notional,
                "max_daily_buy_notional",
            ),
            commission_rate=(
                COMMISSION_RATE
                if cost_policy_enabled
                else self._money(commission_rate, "commission_rate")
            ),
            minimum_commission_twd=self._money(
                MINIMUM_COMMISSION_TWD if cost_policy_enabled else minimum_commission,
                "minimum_commission",
            ),
            slippage_bps=(
                normalized_slippage_bps if cost_policy_enabled else Decimal("0")
            ),
            schema_version=(
                SETTINGS_SCHEMA_V2 if cost_policy_enabled else SETTINGS_SCHEMA_V1
            ),
        )
        normalized_starting_cash = settings.starting_cash_twd
        if (
            isinstance(quote_queue_capacity, bool)
            or not isinstance(quote_queue_capacity, int)
            or quote_queue_capacity <= 0
        ):
            raise ValueError("quote_queue_capacity 必須是大於 0 的整數")
        if not isinstance(start_streaming, bool):
            raise ValueError("start_streaming 必須是布林值")
        if (
            isinstance(max_book_age_seconds, bool)
            or not isinstance(max_book_age_seconds, int)
            or max_book_age_seconds <= 0
        ):
            raise ValueError("max_book_age_seconds 必須是大於 0 的整數")
        for value, field_name in (
            (pending_timeout_seconds, "pending_timeout_seconds"),
            (order_expiry_seconds, "order_expiry_seconds"),
            (max_retry_attempts, "max_retry_attempts"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{field_name} 必須是大於 0 的整數")

        self._provider = provider
        self._clock = clock or SystemClock()
        provider_identity = getattr(provider, "environment_identity", None)
        self._provider_identity = (
            str(provider_identity).strip()
            if provider_identity is not None
            else f"{type(provider).__module__}.{type(provider).__qualname__}"
        )
        if not self._provider_identity:
            raise ValueError("provider identity must not be empty")
        self._starting_cash = normalized_starting_cash
        self._settings = settings
        self._cost_policy_enabled = cost_policy_enabled
        self._slippage_bps = normalized_slippage_bps
        self._max_daily_buy_notional = settings.max_daily_buy_notional_twd
        self._daily_filled_buy_notional = Decimal("0")
        self._cash = normalized_starting_cash
        self._max_book_age_seconds = max_book_age_seconds
        self._pending_timeout_seconds = pending_timeout_seconds
        self._order_expiry_seconds = order_expiry_seconds
        self._max_retry_attempts = max_retry_attempts
        self._trading_date = self._clock.session_date()
        self._opening_equity = normalized_starting_cash
        self._opening_realized_pnl = Decimal("0")
        self._orders: dict[str, SimulationOrder] = {}
        self._order_ids_by_key: dict[str, str] = {}
        self._cancel_order_ids_by_key: dict[str, str] = {}
        self._reserved_buy_notional_by_order: dict[str, Decimal] = {}
        self._positions: dict[str, SimulationPosition] = {}
        self._exposure_identities: dict[str, ExposureIdentity] = {}
        self._exposure_symbols: dict[str, str] = {}
        self._quotes: dict[str, _QuoteState] = {}
        self._realized_pnl_by_exposure: dict[str, Decimal] = {}
        self._alerts: list[dict[str, Any]] = []
        self._lock = RLock()
        self._mutation_boundary_time: datetime | None = None
        self._subscription_lock = RLock()
        self._stream_capable = provider.supports_streaming_quotes()
        self._streaming_enabled = False
        self._owns_quote_stream = False
        self._stream_error: str | None = None
        self._quote_ingress_blocked = False
        self._subscribed_symbols: set[str] = set()
        self._quote_watch_by_owner: dict[str, str] = {}
        self._quote_queue_capacity = quote_queue_capacity
        self._quote_updates: Queue[RealtimeQuoteUpdate | None] = Queue(
            maxsize=self._quote_queue_capacity
        )
        self._quote_worker: Thread | None = None
        self._terminal_order_handler: Callable[[dict[str, Any]], None] | None = None
        self._daily_baseline_handler: Callable[[dict[str, Any]], None] | None = None
        self._pending_daily_baselines: list[dict[str, Any]] = []

        if self._stream_capable and start_streaming:
            self._activate_streaming(fail_closed=False)

    @property
    def starting_cash(self) -> Decimal:
        """Expose immutable starting cash for the command facade and Journal."""
        return self._starting_cash

    @property
    def max_daily_buy_notional(self) -> Decimal:
        return self._max_daily_buy_notional

    @property
    def settings(self) -> LocalPaperSettings:
        return self._settings

    @property
    def requires_fresh_book(self) -> bool:
        return self._stream_capable

    @property
    def max_book_age_seconds(self) -> int:
        return self._max_book_age_seconds

    @property
    def max_retry_attempts(self) -> int:
        return self._max_retry_attempts

    def validate_order_admission(
        self,
        *,
        symbol: str,
        limit_price: Decimal | float | int | str,
    ) -> None:
        """Fail expected v2 scope/tick errors before command Journal mutation."""

        if not self._cost_policy_enabled:
            return
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_price = self._normalize_price(limit_price)
        if not is_valid_common_stock_tick(normalized_price):
            raise SimulationValidationError(
                "限價不符合 tw_common_stock_tick_v1 升降單位"
            )
        if self._stream_capable:
            canonical_symbol, _ = self._get_stock_identity(normalized_symbol)
        else:
            canonical_symbol = self._get_stock(normalized_symbol).symbol
        self._get_local_paper_instrument_descriptor(canonical_symbol)

    def no_overnight_sell_limit_price(
        self,
        reference_price: Decimal | float | int | str,
    ) -> Decimal:
        """Return the exact policy-compatible SELL limit for a forced local exit."""

        reference = self._normalize_price(reference_price)
        if not self._cost_policy_enabled:
            return reference
        if not is_valid_common_stock_tick(reference):
            raise SimulationValidationError(
                "即時最佳買價不符合 tw_common_stock_tick_v1 升降單位"
            )
        raw_adverse = reference * (
            Decimal("1") - self._slippage_bps / Decimal("10000")
        )
        if raw_adverse <= 0:
            raise SimulationValidationError("No-Overnight SELL 限價必須大於 0")
        return adverse_tick_floor(raw_adverse)

    def set_terminal_order_handler(
        self,
        handler: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        """Register the local Journal bridge for orders completed after submit."""
        with self._lock:
            self._terminal_order_handler = handler

    def mark_persistence_recovery_required(self, reason: str) -> None:
        """Stop new local-paper admission after durable state becomes uncertain."""

        normalized = str(reason).strip()
        if not normalized:
            raise ValueError("recovery reason must not be empty")
        with self._lock:
            self._quote_ingress_blocked = True
            self._stream_error = f"LOCAL_PAPER_RECOVERY_REQUIRED: {normalized}"

    def activate_streaming(self) -> None:
        """Start quote ownership and report Provider handoff failures."""

        self._activate_streaming(fail_closed=True)

    def suspend_streaming(self) -> None:
        """Release Provider ownership while preserving recoverable runtime state."""

        self._deactivate_streaming(clear_runtime_state=False)

    def _activate_streaming(self, *, fail_closed: bool) -> None:
        """Start the worker/callback pair with optional startup degradation."""

        if not self._stream_capable or self._streaming_enabled:
            return
        self._quote_updates = Queue(maxsize=self._quote_queue_capacity)
        worker = Thread(
            target=self._run_quote_worker,
            name="simulation-quote-worker",
            daemon=True,
        )
        self._quote_worker = worker
        worker.start()
        try:
            self._provider.start_quote_stream(self.receive_quote_update)
            self._owns_quote_stream = True
            self._streaming_enabled = True
            self._stream_error = None
            self._sync_quote_subscriptions(fail_closed=True)
        except Exception as error:
            try:
                self._provider.stop_quote_stream()
            except Exception:
                pass
            self._owns_quote_stream = False
            self._streaming_enabled = False
            try:
                self._stop_quote_worker()
            except SimulationStateError:
                pass
            message = f"無法啟動 Shioaji Tick／BidAsk：{error}"
            self._stream_error = message
            if fail_closed:
                raise SimulationStateError(message) from error
            return

    def _stop_quote_worker(self) -> None:
        worker = self._quote_worker
        if worker is None:
            return
        try:
            self._quote_updates.put(None, timeout=2)
        except Full as error:
            message = "即時行情 worker 無法排入關閉訊號"
            self._stream_error = message
            raise SimulationStateError(message) from error
        worker.join(timeout=5)
        if worker.is_alive():
            message = "即時行情 worker 未在關閉期限內排空佇列"
            self._stream_error = message
            raise SimulationStateError(message)
        self._quote_worker = None

    def _deactivate_streaming(self, *, clear_runtime_state: bool) -> None:
        if not self._stream_capable:
            return
        with self._lock:
            self._streaming_enabled = False
        provider_error: Exception | None = None
        try:
            if self._owns_quote_stream:
                self._provider.stop_quote_stream()
        except Exception as error:
            provider_error = error
        finally:
            self._owns_quote_stream = False
            with self._lock:
                self._subscribed_symbols.clear()
                if clear_runtime_state:
                    self._quote_watch_by_owner.clear()
            self._stop_quote_worker()
        if provider_error is not None:
            message = f"無法停止 Shioaji Tick／BidAsk：{provider_error}"
            self._stream_error = message
            raise SimulationStateError(message) from provider_error

    def set_daily_baseline_handler(
        self,
        handler: Callable[[dict[str, Any]], None] | None,
    ) -> None:
        """Register the Journal bridge for a newly frozen trading-day baseline."""
        with self._lock:
            self._daily_baseline_handler = handler

    def daily_baseline(self) -> dict[str, Any]:
        """Return the currently frozen trading-day risk baseline."""
        self._roll_trading_day()
        with self._lock:
            return self._daily_baseline_payload()

    def session(self) -> dict[str, Any]:
        """回傳不會觸發 Provider 或券商呼叫的 session 中繼資料。"""
        self._roll_trading_day()
        with self._lock:
            market_value = self._market_value()
            reserved_cash = self._reserved_cash()
            reserved_buy_notional = self._daily_reserved_buy_notional()
            used_buy_notional = (
                self._daily_filled_buy_notional + reserved_buy_notional
            )
            available_cash = self._cash - reserved_cash
            commission_total = sum(
                (order.filled_commission for order in self._orders.values()),
                Decimal("0"),
            )
            tax_total = sum(
                (order.filled_tax for order in self._orders.values()),
                Decimal("0"),
            )
            slippage_cost_total = sum(
                (order.filled_slippage_cost for order in self._orders.values()),
                Decimal("0"),
            )
            realized_pnl = sum(
                self._realized_pnl_by_exposure.values(),
                Decimal("0"),
            )
            received_times = [
                quote.received_at
                for quote in self._quotes.values()
                if quote.received_at is not None
            ]
            label = (
                "本機紙上模擬（Shioaji 即時行情）"
                if self._stream_capable
                else self.label
            )
            notice = (
                "委託、持倉與交易日風控基準由本機 Journal checkpoint 管理；"
                "行情來自 Shioaji Tick／BidAsk，不會送出 Shioaji 或真實券商委託。"
                if self._stream_capable
                else "委託、持倉與交易日風控基準由本機 Journal checkpoint 管理；"
                "不會送出 Shioaji 或真實券商委託。"
            )
            return {
                "mode": self.mode,
                "label": label,
                "ordering_enabled": True,
                "starting_cash": float(self._starting_cash),
                "max_daily_buy_notional": float(self._max_daily_buy_notional),
                "commission_rate": float(self._settings.commission_rate),
                "minimum_commission": float(
                    self._settings.minimum_commission_twd
                ),
                "cost_policy_enabled": self._cost_policy_enabled,
                "slippage_bps": str(self._slippage_bps),
                "trading_date": self._trading_date.isoformat(),
                "opening_equity": float(self._opening_equity),
                "daily_loss_includes_unrealized": True,
                "available_cash": float(available_cash),
                "reserved_cash": float(reserved_cash),
                "daily_filled_buy_notional": float(
                    self._daily_filled_buy_notional
                ),
                "daily_reserved_buy_notional": float(reserved_buy_notional),
                "daily_used_buy_notional": float(used_buy_notional),
                "daily_remaining_buy_notional": float(
                    max(
                        Decimal("0"),
                        self._max_daily_buy_notional - used_buy_notional,
                    )
                ),
                "market_value": float(market_value),
                "equity": float(self._cash + market_value),
                "realized_pnl": str(realized_pnl),
                "commission_total": str(commission_total),
                "tax_total": str(tax_total),
                "slippage_cost_total": str(slippage_cost_total),
                "quote_mode": (
                    "SHIOAJI_TICK_BIDASK" if self._stream_capable else "SNAPSHOT"
                ),
                "streaming": self._streaming_enabled,
                "stream_health": self._stream_health(),
                "quote_queue_depth": self._quote_updates.qsize(),
                "quote_queue_capacity": self._quote_updates.maxsize,
                "subscribed_symbols": sorted(self._subscribed_symbols),
                "watched_symbols": sorted(set(self._quote_watch_by_owner.values())),
                "last_quote_received_at": (
                    max(received_times).isoformat() if received_times else None
                ),
                "stream_error": self._stream_error,
                "notice": notice,
            }

    def no_overnight_reconciliation_context(self) -> dict[str, object]:
        """Return canonical Local Paper accounting facts without provider I/O."""

        self._roll_trading_day()
        with self._lock:
            return {
                "starting_cash": format(self._starting_cash, "f"),
                "cash": format(self._cash, "f"),
                "realized_pnl_by_exposure": {
                    exposure_id: format(value, "f")
                    for exposure_id, value in sorted(
                        self._realized_pnl_by_exposure.items()
                    )
                },
            }

    def projection(self) -> dict[str, Any]:
        """回傳瀏覽器可直接讀取的本機訂單、持倉與 session 投影。"""
        self.reconcile_orders()
        return {
            "session": self.session(),
            "orders": self.orders(),
            "positions": self.positions(),
            "alerts": self.alerts(),
        }

    def orders(self) -> list[dict[str, Any]]:
        """讀取委託投影，不會呼叫資料來源。"""
        with self._lock:
            orders = sorted(
                self._orders.values(),
                key=lambda order: order.submitted_at,
                reverse=True,
            )
            return [self._order_payload(order) for order in orders]

    def alerts(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(alert) for alert in reversed(self._alerts)]

    def restore_state(
        self,
        *,
        cash: Decimal,
        positions: list[dict[str, Any]],
        realized_pnl_by_symbol: dict[str, Decimal],
        order_states: list[dict[str, Any]],
        realized_pnl_by_exposure: dict[str, Decimal] | None = None,
        daily_baseline: dict[str, Any] | None = None,
        daily_filled_buy_notional: Decimal = Decimal("0"),
    ) -> None:
        """Restore one checkpoint-verified local-paper projection before use."""

        with self._lock:
            if self._orders or self._positions or self._cash != self._starting_cash:
                raise SimulationStateError("本機模擬已有狀態，禁止重複復原")
            self._cash = self._money(cash, "restored.cash")
            self._daily_filled_buy_notional = self._money(
                daily_filled_buy_notional,
                "restored.daily_filled_buy_notional",
            )
            for raw in positions:
                symbol = self._normalize_symbol(str(raw["symbol"]))
                raw_exposure = raw.get("exposure_identity")
                exposure = (
                    ExposureIdentity.from_payload(raw_exposure)
                    if isinstance(raw_exposure, Mapping)
                    else build_legacy_exposure_identity(
                        account_scope_id=_LEGACY_ACCOUNT_SCOPE_ID,
                        policy_family_id=_LEGACY_POLICY_FAMILY_ID,
                        source_session_id=_LEGACY_SOURCE_SESSION_ID,
                        symbol=symbol,
                        owner_origin=str(raw.get("owner_origin") or "MANUAL_WEB"),
                        owner_id=str(
                            raw.get("owner_strategy_id") or "manual-web"
                        ),
                    )
                )
                position = SimulationPosition(
                    symbol=symbol,
                    name=str(raw["name"]),
                    quantity=int(raw["quantity"]),
                    average_price=self._money(raw["average_price"], "restored.average_price"),
                    owner_origin=str(raw.get("owner_origin") or "MANUAL_WEB"),
                    commission_cost=self._money(
                        raw.get("commission_cost") or 0,
                        "restored.commission_cost",
                    ),
                    owner_strategy_id=(
                        str(raw["owner_strategy_id"])
                        if raw.get("owner_strategy_id") is not None
                        else None
                    ),
                    owner_strategy_version=(
                        str(raw["owner_strategy_version"])
                        if raw.get("owner_strategy_version") is not None
                        else None
                    ),
                    exposure=exposure,
                )
                self._exposure_identities[exposure.exposure_id] = exposure
                self._exposure_symbols[exposure.exposure_id] = symbol
                if position.quantity < 0:
                    raise SimulationStateError("restored exposure quantity cannot be negative")
                if position.quantity > 0:
                    self._positions[exposure.exposure_id] = position
                self._quotes.setdefault(symbol, _QuoteState())
            for raw_symbol, raw_value in realized_pnl_by_symbol.items():
                symbol = self._normalize_symbol(raw_symbol)
                candidates = [
                    exposure_id
                    for exposure_id, exposure_symbol in self._exposure_symbols.items()
                    if exposure_symbol == symbol
                ]
                if len(candidates) > 1:
                    raise SimulationStateError(
                        "legacy realized PnL 無法分配到多個 exposure"
                    )
                if candidates:
                    exposure_id = candidates[0]
                else:
                    legacy = build_legacy_exposure_identity(
                        account_scope_id=_LEGACY_ACCOUNT_SCOPE_ID,
                        policy_family_id=_LEGACY_POLICY_FAMILY_ID,
                        source_session_id=_LEGACY_SOURCE_SESSION_ID,
                        symbol=symbol,
                        owner_origin="MANUAL_WEB",
                        owner_id="manual-web",
                    )
                    exposure_id = legacy.exposure_id
                    self._exposure_identities[exposure_id] = legacy
                    self._exposure_symbols[exposure_id] = symbol
                self._realized_pnl_by_exposure[exposure_id] = self._money(
                    raw_value,
                    "restored.realized_pnl",
                )
            for raw in order_states:
                order_symbol = self._normalize_symbol(str(raw["symbol"]))
                raw_exposure = raw.get("exposure_identity")
                order_exposure = (
                    ExposureIdentity.from_payload(raw_exposure)
                    if isinstance(raw_exposure, Mapping)
                    else build_legacy_exposure_identity(
                        account_scope_id=_LEGACY_ACCOUNT_SCOPE_ID,
                        policy_family_id=_LEGACY_POLICY_FAMILY_ID,
                        source_session_id=_LEGACY_SOURCE_SESSION_ID,
                        symbol=order_symbol,
                        owner_origin=str(raw.get("origin") or "MANUAL_WEB"),
                        owner_id=str(raw.get("strategy_id") or "manual-web"),
                    )
                )
                order = SimulationOrder(
                    order_id=str(raw["order_id"]),
                    idempotency_key=str(raw["idempotency_key"]),
                    origin=str(raw["origin"]),
                    strategy_id=(
                        str(raw["strategy_id"])
                        if raw.get("strategy_id") is not None
                        else None
                    ),
                    strategy_version=(
                        str(raw["strategy_version"])
                        if raw.get("strategy_version") is not None
                        else None
                    ),
                    symbol=order_symbol,
                    name=str(raw["name"]),
                    side=OrderSide(str(raw["side"])),
                    quantity_shares=self._restored_quantity_shares(raw),
                    limit_price=self._money(
                        raw.get("limit_price_decimal") or raw["limit_price"],
                        "restored.limit_price",
                    ),
                    status=OrderStatus(str(raw["status"])),
                    submitted_at=datetime.fromisoformat(str(raw["submitted_at"])),
                    updated_at=datetime.fromisoformat(str(raw["updated_at"])),
                    filled_price=(
                        self._money(raw["filled_price"], "restored.filled_price")
                        if raw.get("filled_price") is not None
                        else None
                    ),
                    filled_quantity=int(raw.get("filled_quantity") or 0),
                    filled_notional=self._money(
                        raw.get("filled_amount_decimal")
                        or raw.get("filled_amount")
                        or 0,
                        "restored.filled_amount",
                    ),
                    filled_commission=self._money(
                        raw.get("filled_commission_decimal")
                        or raw.get("filled_commission")
                        or 0,
                        "restored.filled_commission",
                    ),
                    filled_tax=self._money(
                        raw.get("filled_tax") or 0,
                        "restored.filled_tax",
                    ),
                    filled_slippage_cost=self._money(
                        raw.get("filled_slippage_cost") or 0,
                        "restored.filled_slippage_cost",
                    ),
                    last_fill_price=(
                        self._money(
                            raw.get("last_fill_price_decimal")
                            or raw["last_fill_price"],
                            "restored.last_fill_price",
                        )
                        if raw.get("last_fill_price_decimal") is not None
                        or raw.get("last_fill_price") is not None
                        else None
                    ),
                    last_fill_quantity=int(raw.get("last_fill_quantity") or 0),
                    last_fill_commission=self._money(
                        raw.get("last_fill_commission_decimal")
                        or raw.get("last_fill_commission")
                        or 0,
                        "restored.last_fill_commission",
                    ),
                    last_fill_tax=self._money(
                        raw.get("last_fill_tax") or 0,
                        "restored.last_fill_tax",
                    ),
                    last_reference_price=(
                        self._money(
                            raw["last_reference_price"],
                            "restored.last_reference_price",
                        )
                        if raw.get("last_reference_price") is not None
                        else None
                    ),
                    last_reference_source=(
                        str(raw["last_reference_source"])
                        if raw.get("last_reference_source") is not None
                        else None
                    ),
                    configured_slippage_bps=(
                        self._money(
                            raw["configured_slippage_bps"],
                            "restored.configured_slippage_bps",
                        )
                        if raw.get("configured_slippage_bps") is not None
                        else None
                    ),
                    last_realized_slippage_bps=(
                        self._money(
                            raw["last_realized_slippage_bps"],
                            "restored.last_realized_slippage_bps",
                        )
                        if raw.get("last_realized_slippage_bps") is not None
                        else None
                    ),
                    last_slippage_cost=self._money(
                        raw.get("last_slippage_cost") or 0,
                        "restored.last_slippage_cost",
                    ),
                    last_net_cash_effect=(
                        self._money(
                            raw["last_net_cash_effect"],
                            "restored.last_net_cash_effect",
                        )
                        if raw.get("last_net_cash_effect") is not None
                        else None
                    ),
                    fee_policy_version=(
                        str(raw["fee_policy_version"])
                        if raw.get("fee_policy_version") is not None
                        else None
                    ),
                    rounding_policy_version=(
                        str(raw["rounding_policy_version"])
                        if raw.get("rounding_policy_version") is not None
                        else None
                    ),
                    slippage_policy_version=(
                        str(raw["slippage_policy_version"])
                        if raw.get("slippage_policy_version") is not None
                        else None
                    ),
                    price_tick_policy_version=(
                        str(raw["price_tick_policy_version"])
                        if raw.get("price_tick_policy_version") is not None
                        else None
                    ),
                    instrument_descriptor=self._restored_instrument_descriptor(raw),
                    waiting_reason=(
                        str(raw["waiting_reason"])
                        if raw.get("waiting_reason") is not None
                        else None
                    ),
                    fill_sequence=int(raw.get("fill_sequence") or 0),
                    reason=(str(raw["reason"]) if raw.get("reason") is not None else None),
                    attempt=int(raw.get("attempt") or 1),
                    predecessor_order_id=(
                        str(raw["predecessor_order_id"])
                        if raw.get("predecessor_order_id") is not None
                        else None
                    ),
                    timeout_at=(
                        datetime.fromisoformat(str(raw["timeout_at"]))
                        if raw.get("timeout_at") is not None
                        else None
                    ),
                    expires_at=(
                        datetime.fromisoformat(str(raw["expires_at"]))
                        if raw.get("expires_at") is not None
                        else None
                    ),
                    exposure=order_exposure,
                    position_action=PositionAction(
                        str(
                            raw.get("position_action")
                            or (
                                PositionAction.OPEN_LONG.value
                                if str(raw["side"]) == OrderSide.BUY.value
                                else PositionAction.CLOSE_LONG.value
                            )
                        )
                    ),
                    target_exposure_id=(
                        str(raw["target_exposure_id"])
                        if raw.get("target_exposure_id") is not None
                        else (
                            order_exposure.exposure_id
                            if str(raw["side"]) == OrderSide.SELL.value
                            else None
                        )
                    ),
                    execution_reason_category=(
                        ExecutionReasonCategory(
                            str(raw["execution_reason_category"])
                        )
                        if raw.get("execution_reason_category") is not None
                        else None
                    ),
                    execution_reason_code=(
                        str(raw["execution_reason_code"])
                        if raw.get("execution_reason_code") is not None
                        else None
                    ),
                )
                self._exposure_identities.setdefault(
                    order_exposure.exposure_id, order_exposure
                )
                self._exposure_symbols.setdefault(
                    order_exposure.exposure_id, order.symbol
                )
                self._orders[order.order_id] = order
                self._order_ids_by_key[order.idempotency_key] = order.order_id
                self._quotes.setdefault(order.symbol, _QuoteState())
                if order.status in _ACTIVE_ORDER_STATUSES and order.side is OrderSide.BUY:
                    self._reserved_buy_notional_by_order[order.order_id] = (
                        self._order_cash_reservation(order)
                    )
                recovered_alert = {
                    "ORDER_TIMEOUT": "ORDER_TIMEOUT_CANCELLED",
                    "ORDER_EXPIRED": "ORDER_EXPIRED",
                    "COMMAND_ACKNOWLEDGEMENT_MISSING": "RECOVERY_REQUIRED",
                }.get(order.reason or "")
                if recovered_alert is not None:
                    self._alerts.append(
                        {
                            "alert_id": f"{recovered_alert}:{order.order_id}:restored",
                            "code": recovered_alert,
                            "severity": "HIGH",
                            "order_id": order.order_id,
                            "symbol": order.symbol,
                            "message": f"{order.symbol} 委託復原狀態：{order.reason}",
                            "created_at": order.updated_at.isoformat(),
                            "acknowledged": False,
                        }
                    )
            if realized_pnl_by_exposure is not None:
                if realized_pnl_by_symbol:
                    raise SimulationStateError(
                        "cannot restore realized PnL by both symbol and exposure"
                    )
                for exposure_id, raw_value in realized_pnl_by_exposure.items():
                    if exposure_id not in self._exposure_identities:
                        raise SimulationStateError(
                            "restored realized PnL references unknown exposure"
                        )
                    self._realized_pnl_by_exposure[exposure_id] = self._money(
                        raw_value,
                        "restored.realized_pnl",
                    )
            latest = order_states[-1] if order_states else None
            if daily_baseline is not None:
                restored_date = date.fromisoformat(
                    str(daily_baseline["trading_date"])
                )
                if restored_date > self._clock.session_date():
                    raise SimulationStateError("交易日風控基準不可晚於目前交易日")
                if daily_baseline.get("includes_unrealized_pnl") is not True:
                    raise SimulationStateError("交易日風控基準未凍結未實現損益政策")
                self._trading_date = restored_date
                self._opening_equity = self._money(
                    daily_baseline["opening_equity"],
                    "restored.opening_equity",
                )
                self._opening_realized_pnl = self._money(
                    daily_baseline.get("opening_realized_pnl") or 0,
                    "restored.opening_realized_pnl",
                )
            elif latest and latest.get("trading_date") == self._trading_date.isoformat():
                self._opening_equity = self._money(
                    latest.get("opening_equity"),
                    "restored.opening_equity",
                )
                self._opening_realized_pnl = sum(
                    self._realized_pnl_by_exposure.values(),
                    Decimal("0"),
                )
            else:
                self._opening_equity = self._cash + self._market_value()
                self._opening_realized_pnl = sum(
                    self._realized_pnl_by_exposure.values(),
                    Decimal("0"),
                )
        self._sync_quote_subscriptions()

    def reconcile_orders(self) -> None:
        """Apply deterministic timeout/expiry transitions using the injected clock."""

        changed = False
        notifications: list[dict[str, Any]] = []
        with self._lock:
            now = self._now()
            for order in self._orders.values():
                if order.status not in _ACTIVE_ORDER_STATUSES:
                    continue
                if order.expires_at is not None and now >= order.expires_at:
                    self._end_order(
                        order,
                        status=OrderStatus.EXPIRED,
                        reason="ORDER_EXPIRED",
                        alert_code="ORDER_EXPIRED",
                        alert_message=f"{order.symbol} 委託已到期，未成交餘量停止撮合",
                    )
                    notifications.append(self._order_payload(order))
                    changed = True
                elif order.timeout_at is not None and now >= order.timeout_at:
                    self._end_order(
                        order,
                        status=OrderStatus.CANCELLED,
                        reason="ORDER_TIMEOUT",
                        alert_code="ORDER_TIMEOUT_CANCELLED",
                        alert_message=f"{order.symbol} 委託逾時，已取消未成交餘量",
                    )
                    notifications.append(self._order_payload(order))
                    changed = True
        for payload in notifications:
            self._notify_terminal_order(payload)
        if changed:
            self._sync_quote_subscriptions()

    def positions(self) -> list[dict[str, Any]]:
        """Return the legacy symbol aggregate without collapsing mutation keys."""
        self._roll_trading_day()
        with self._lock:
            positions: list[dict[str, Any]] = []
            symbols = sorted({position.symbol for position in self._positions.values()})
            for symbol in symbols:
                members = [
                    position
                    for position in self._positions.values()
                    if position.symbol == symbol
                ]
                quantity = sum(position.quantity for position in members)
                cost = sum(
                    position.average_price * position.quantity for position in members
                )
                commission_cost = sum(
                    (position.commission_cost for position in members),
                    Decimal("0"),
                )
                owner_origins = {position.owner_origin for position in members}
                strategy_ids = {position.owner_strategy_id for position in members}
                strategy_versions = {
                    position.owner_strategy_version for position in members
                }
                aggregate = SimulationPosition(
                    symbol=symbol,
                    name=members[0].name,
                    quantity=quantity,
                    average_price=cost / quantity,
                    commission_cost=commission_cost,
                    owner_origin=(
                        next(iter(owner_origins))
                        if len(owner_origins) == 1
                        else "MIXED"
                    ),
                    owner_strategy_id=(
                        next(iter(strategy_ids)) if len(strategy_ids) == 1 else None
                    ),
                    owner_strategy_version=(
                        next(iter(strategy_versions))
                        if len(strategy_versions) == 1
                        else None
                    ),
                )
                realized = sum(
                    (
                        value
                        for exposure_id, value in self._realized_pnl_by_exposure.items()
                        if self._exposure_symbols.get(exposure_id) == symbol
                    ),
                    Decimal("0"),
                )
                payload = self._position_payload(aggregate, realized_pnl=realized)
                payload["exposure_count"] = len(members)
                payload["exposure_ids"] = sorted(
                    position.exposure.exposure_id
                    for position in members
                    if position.exposure is not None
                )
                positions.append(payload)
            return positions

    def exposures(self) -> list[dict[str, Any]]:
        """Return one independently mutable row per exposure identity."""
        self._roll_trading_day()
        with self._lock:
            return [
                self._position_payload(
                    position,
                    realized_pnl=self._realized_pnl_by_exposure.get(
                        exposure_id, Decimal("0")
                    ),
                    exposure=position.exposure,
                )
                for exposure_id, position in sorted(
                    self._positions.items(),
                    key=lambda item: (item[1].symbol, item[0]),
                )
            ]

    def submit_order(
        self,
        *,
        symbol: str,
        side: str,
        limit_price: Decimal | float | int | str,
        idempotency_key: str,
        quantity_shares: int | None = None,
        lots: int | None = None,
        origin: str = "MANUAL_WEB",
        strategy_id: str | None = None,
        strategy_version: str | None = None,
        attempt: int = 1,
        predecessor_order_id: str | None = None,
        exposure: ExposureIdentity | None = None,
        position_action: PositionAction | None = None,
        target_exposure_id: str | None = None,
        execution_reason_category: ExecutionReasonCategory | None = None,
        execution_reason_code: str | None = None,
    ) -> tuple[dict[str, Any], bool]:
        """接受限價委託；串流模式以賣一／買一，本機模式以 snapshot 撮合。"""
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_side = self._normalize_side(side)
        normalized_quantity_shares = self._resolve_quantity_shares(
            quantity_shares=quantity_shares,
            lots=lots,
        )
        normalized_price = self._normalize_price(limit_price)
        if self._cost_policy_enabled and not is_valid_common_stock_tick(
            normalized_price
        ):
            raise SimulationValidationError(
                "限價不符合 tw_common_stock_tick_v1 升降單位"
            )
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        normalized_origin = str(origin).strip().upper()
        normalized_strategy_id = self._optional_identity(strategy_id)
        normalized_strategy_version = self._optional_identity(strategy_version)
        normalized_target_exposure_id = self._optional_identity(target_exposure_id)
        normalized_reason_code = self._optional_identity(execution_reason_code)
        if isinstance(attempt, bool) or not isinstance(attempt, int) or attempt <= 0:
            raise SimulationValidationError("委託 attempt 必須是大於 0 的整數")
        if attempt > self._max_retry_attempts:
            raise SimulationValidationError("委託重試次數已達上限")
        normalized_predecessor = self._optional_identity(predecessor_order_id)
        if (attempt == 1) != (normalized_predecessor is None):
            raise SimulationValidationError("委託 predecessor 與 attempt 不一致")
        if normalized_origin == "STRATEGY_AUTOMATED":
            if normalized_strategy_id is None or normalized_strategy_version is None:
                raise SimulationValidationError("自動策略委託缺少策略歸屬")
        elif normalized_strategy_id is not None or normalized_strategy_version is not None:
            raise SimulationValidationError("手動委託不可帶入自動策略歸屬")
        if exposure is not None:
            if not isinstance(exposure, ExposureIdentity):
                raise SimulationValidationError("exposure identity 格式錯誤")
            if exposure.owner_origin != normalized_origin:
                raise SimulationValidationError("委託 origin 與 exposure 歸屬不一致")
            expected_owner_id = (
                normalized_strategy_id
                if normalized_origin == "STRATEGY_AUTOMATED"
                else "manual-web"
            )
            if exposure.owner_id != expected_owner_id:
                raise SimulationValidationError("委託 owner 與 exposure 歸屬不一致")
            if not isinstance(position_action, PositionAction):
                raise SimulationValidationError("v2 委託缺少 position_action")
            if not isinstance(execution_reason_category, ExecutionReasonCategory):
                raise SimulationValidationError("v2 委託缺少 execution_reason_category")
            if normalized_reason_code is None:
                raise SimulationValidationError("v2 委託缺少 execution_reason_code")
            if normalized_side is OrderSide.BUY:
                if position_action is not PositionAction.OPEN_LONG:
                    raise SimulationValidationError("BUY 必須使用 OPEN_LONG")
                if normalized_target_exposure_id is not None:
                    raise SimulationValidationError("BUY 不可指定 target_exposure_id")
            elif (
                position_action is not PositionAction.CLOSE_LONG
                or normalized_target_exposure_id != exposure.exposure_id
            ):
                raise SimulationValidationError(
                    "SELL 必須以 CLOSE_LONG 指定相同的 target exposure"
                )
        elif any(
            value is not None
            for value in (
                position_action,
                normalized_target_exposure_id,
                execution_reason_category,
                normalized_reason_code,
            )
        ):
            raise SimulationValidationError("v1 委託不可只帶入部分 exposure 欄位")

        self._roll_trading_day()
        with self._lock:
            existing_order_id = self._order_ids_by_key.get(normalized_key)
            if existing_order_id is not None:
                return self._order_payload(self._orders[existing_order_id]), True

            if self._stream_capable:
                stock_symbol, stock_name = self._get_stock_identity(normalized_symbol)
                self._quotes.setdefault(stock_symbol, _QuoteState())
            else:
                stock = self._get_stock(normalized_symbol)
                stock_symbol, stock_name = stock.symbol, stock.name
                self._quotes.setdefault(
                    stock_symbol,
                    _QuoteState(snapshot=stock),
                ).snapshot = stock
            instrument_descriptor = (
                self._get_local_paper_instrument_descriptor(stock_symbol)
                if self._cost_policy_enabled
                else None
            )
            ambiguous_sell_target = False
            owner_conflict_sell = False
            resolved_exposure = exposure
            resolved_action = position_action
            resolved_target_exposure_id = normalized_target_exposure_id
            if resolved_exposure is None and normalized_side is OrderSide.SELL:
                candidates = [
                    position.exposure
                    for position in self._positions.values()
                    if position.symbol == stock_symbol
                    and position.exposure is not None
                    and self._owner_matches(
                        origin=normalized_origin,
                        strategy_id=normalized_strategy_id,
                        exposure=position.exposure,
                    )
                ]
                if len(candidates) == 1:
                    resolved_exposure = candidates[0]
                    resolved_target_exposure_id = resolved_exposure.exposure_id
                elif len(candidates) > 1:
                    ambiguous_sell_target = True
                elif any(
                    position.symbol == stock_symbol
                    for position in self._positions.values()
                ):
                    owner_conflict_sell = True
            if resolved_exposure is None:
                resolved_exposure = build_legacy_exposure_identity(
                    account_scope_id=_LEGACY_ACCOUNT_SCOPE_ID,
                    policy_family_id=_LEGACY_POLICY_FAMILY_ID,
                    source_session_id=_LEGACY_SOURCE_SESSION_ID,
                    symbol=stock_symbol,
                    owner_origin=normalized_origin,
                    owner_id=normalized_strategy_id or "manual-web",
                )
            if resolved_action is None:
                resolved_action = (
                    PositionAction.OPEN_LONG
                    if normalized_side is OrderSide.BUY
                    else PositionAction.CLOSE_LONG
                )
            if normalized_side is OrderSide.SELL and resolved_target_exposure_id is None:
                resolved_target_exposure_id = resolved_exposure.exposure_id
            now = self._now()
            order = SimulationOrder(
                order_id=uuid4().hex,
                idempotency_key=normalized_key,
                origin=normalized_origin,
                symbol=stock_symbol,
                name=stock_name,
                side=normalized_side,
                quantity_shares=normalized_quantity_shares,
                limit_price=normalized_price,
                status=OrderStatus.SUBMITTED,
                submitted_at=now,
                updated_at=now,
                strategy_id=normalized_strategy_id,
                strategy_version=normalized_strategy_version,
                attempt=attempt,
                predecessor_order_id=normalized_predecessor,
                timeout_at=now + timedelta(seconds=self._pending_timeout_seconds),
                expires_at=now + timedelta(seconds=self._order_expiry_seconds),
                configured_slippage_bps=(
                    self._slippage_bps if self._cost_policy_enabled else None
                ),
                instrument_descriptor=instrument_descriptor,
                exposure=resolved_exposure,
                position_action=resolved_action,
                target_exposure_id=resolved_target_exposure_id,
                execution_reason_category=execution_reason_category,
                execution_reason_code=normalized_reason_code,
            )
            self._orders[order.order_id] = order
            self._order_ids_by_key[normalized_key] = order.order_id

            if normalized_side is OrderSide.BUY:
                known_symbol = self._exposure_symbols.get(
                    resolved_exposure.exposure_id
                )
                if known_symbol is not None and known_symbol != order.symbol:
                    self._reject(order, "exposure identity 已綁定不同股票")
                reserved_buy_notional = order.quantity * order.limit_price
                reserved_cash = self._order_cash_reservation(order)
                daily_used = (
                    self._daily_filled_buy_notional
                    + self._daily_reserved_buy_notional(
                        exclude_order_id=order.order_id
                    )
                    + reserved_buy_notional
                )
                if (
                    order.status is OrderStatus.SUBMITTED
                    and daily_used > self._max_daily_buy_notional
                ):
                    self._reject(order, "每日買入額度不足")
                elif (
                    order.status is OrderStatus.SUBMITTED
                    and reserved_cash > self._available_cash()
                ):
                    self._reject(order, "可用虛擬現金不足")
                elif order.status is OrderStatus.SUBMITTED:
                    self._reserved_buy_notional_by_order[order.order_id] = reserved_cash
            else:
                if ambiguous_sell_target:
                    self._reject(
                        order,
                        "同股票有多個符合歸屬的 exposure，賣出必須指定 target_exposure_id",
                    )
                elif owner_conflict_sell:
                    self._reject(order, "自動策略不可賣出不屬於該策略的持倉")
                elif self._sell_target_conflicts(order):
                    self._reject(order, "target exposure 與委託股票或 identity 不一致")
                elif order.quantity > self._available_to_sell(
                    order,
                    exclude_order_id=order.order_id,
                ):
                    self._reject(order, "可賣出持股不足")

            if order.status is OrderStatus.SUBMITTED:
                reference_price = (
                    self._stream_execution_price(order, self._quotes[stock_symbol])
                    if self._stream_capable
                    else self._stock_price(stock)
                )
                execution = self._execution_decision(
                    order,
                    reference_price,
                    (
                        ReferenceSource.BEST_ASK
                        if order.side is OrderSide.BUY
                        else ReferenceSource.BEST_BID
                    )
                    if self._stream_capable
                    else ReferenceSource.SNAPSHOT_COMPATIBILITY,
                )
                if execution is not None:
                    fill_quantity = (
                        self._book_fill_quantity(order, self._quotes[stock_symbol])
                        if self._stream_capable
                        else order.remaining_quantity
                    )
                    if fill_quantity > 0:
                        executed_quantity = self._fill(
                            order,
                            execution,
                            fill_quantity=fill_quantity,
                        )
                        if self._stream_capable and executed_quantity > 0:
                            self._consume_book_quantity(
                                order,
                                self._quotes[stock_symbol],
                                executed_quantity,
                            )

            if order.status is OrderStatus.SUBMITTED:
                order.status = OrderStatus.PENDING
                order.updated_at = self._now()

            payload = self._order_payload(order)

        self._sync_quote_subscriptions()
        return payload, False

    def execute_order_mutation_boundary(
        self,
        operation: Callable[[datetime], Any],
    ) -> Any:
        """Run final admission and order mutation under one lock and timestamp."""

        with self._lock:
            if self._mutation_boundary_time is not None:
                raise SimulationStateError("order mutation boundary cannot be nested")
            mutation_at = self._now()
            self._mutation_boundary_time = mutation_at
            try:
                return operation(mutation_at)
            finally:
                self._mutation_boundary_time = None

    def cancel_order(
        self,
        order_id: str,
        idempotency_key: str,
    ) -> tuple[dict[str, Any], bool]:
        """取消尚未成交的本機限價委託。"""
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        with self._lock:
            previous_order_id = self._cancel_order_ids_by_key.get(normalized_key)
            if previous_order_id is not None:
                return self._order_payload(self._orders[previous_order_id]), True

            order = self._orders.get(order_id)
            if order is None:
                raise SimulationValidationError("找不到委託")
            if order.status not in _ACTIVE_ORDER_STATUSES:
                raise SimulationStateError("只有已送出的委託可以取消")

            order.status = OrderStatus.CANCELLED
            order.reason = "OPERATOR_CANCELLED"
            order.updated_at = self._now()
            self._reserved_buy_notional_by_order.pop(order.order_id, None)
            self._cancel_order_ids_by_key[normalized_key] = order.order_id
            payload = self._order_payload(order)

        self._sync_quote_subscriptions()
        return payload, False

    def refresh_quotes(self) -> None:
        """Mock fallback 才查 snapshot；Shioaji 串流模式不輪詢行情 API。"""
        if self._stream_capable:
            self._sync_quote_subscriptions()
            return

        notifications: list[dict[str, Any]] = []
        with self._lock:
            symbols = {
                *(position.symbol for position in self._positions.values()),
                *(
                    order.symbol
                    for order in self._orders.values()
                    if order.status in _ACTIVE_ORDER_STATUSES
                ),
            }

        quotes: dict[str, StockData] = {}
        for symbol in symbols:
            try:
                quotes[symbol] = self._get_stock(symbol)
            except SimulationValidationError:
                continue

        with self._lock:
            for symbol, quote in quotes.items():
                self._quotes.setdefault(symbol, _QuoteState(snapshot=quote)).snapshot = quote
            for order in self._orders.values():
                quote = quotes.get(order.symbol)
                execution = (
                    self._execution_decision(
                        order,
                        self._stock_price(quote),
                        ReferenceSource.SNAPSHOT_COMPATIBILITY,
                    )
                    if quote is not None and order.status in _ACTIVE_ORDER_STATUSES
                    else None
                )
                if execution is not None:
                    self._fill(order, execution)
                    notifications.append(self._order_payload(order))
        for payload in notifications:
            self._notify_terminal_order(payload)

    def receive_quote_update(self, update: RealtimeQuoteUpdate) -> None:
        """供 Provider callback 快速排入背景 worker，不在 callback thread 撮合。"""
        with self._lock:
            enabled = self._streaming_enabled and not self._quote_ingress_blocked
        if not enabled:
            return
        try:
            self._quote_updates.put_nowait(update)
        except Full:
            with self._lock:
                self._quote_ingress_blocked = True
                self._stream_error = "即時行情佇列已滿，已停止接受新的模擬委託"

    def watch_quote(self, *, owner_id: str, symbol: str) -> dict[str, Any]:
        """Replace one owner's bounded pre-order quote watch and reconcile streaming.

        The watch only supplies canonical Tick/BidAsk evidence to the existing
        simulation cache. It cannot create an order or bypass Hard Risk.
        """

        normalized_owner = str(owner_id).strip()
        if not normalized_owner:
            raise SimulationValidationError("quote watch owner 不可為空")
        normalized_symbol = self._normalize_symbol(symbol)
        with self._lock:
            self._quote_watch_by_owner[normalized_owner] = normalized_symbol
            self._quotes.setdefault(normalized_symbol, _QuoteState())
        self._sync_quote_subscriptions()
        return self.quote_watch_status(
            owner_id=normalized_owner,
            symbol=normalized_symbol,
        )

    def clear_quote_watch(self, *, owner_id: str) -> None:
        """Release one pre-order watch without affecting order/position owners."""

        normalized_owner = str(owner_id).strip()
        if not normalized_owner:
            raise SimulationValidationError("quote watch owner 不可為空")
        with self._lock:
            self._quote_watch_by_owner.pop(normalized_owner, None)
        self._sync_quote_subscriptions()

    def quote_watch_status(
        self,
        *,
        owner_id: str,
        symbol: str,
        max_book_age_seconds: int | None = None,
    ) -> dict[str, Any]:
        """Read one watch's canonical book readiness without provider I/O."""

        normalized_owner = str(owner_id).strip()
        if not normalized_owner:
            raise SimulationValidationError("quote watch owner 不可為空")
        normalized_symbol = self._normalize_symbol(symbol)
        maximum_age = (
            self._max_book_age_seconds
            if max_book_age_seconds is None
            else max_book_age_seconds
        )
        if (
            isinstance(maximum_age, bool)
            or not isinstance(maximum_age, int)
            or maximum_age <= 0
        ):
            raise SimulationValidationError("max_book_age_seconds 必須是正整數")
        with self._lock:
            watched_symbol = self._quote_watch_by_owner.get(normalized_owner)
            quote = self._quotes.get(normalized_symbol)
            book_age = None
            if quote is not None and quote.book_received_at is not None:
                book_age = max(
                    0,
                    int((self._now() - quote.book_received_at).total_seconds()),
                )
            subscribed = normalized_symbol in self._subscribed_symbols
            healthy = (
                not self._quote_ingress_blocked
                and self._streaming_enabled
                and self._stream_error is None
            )
            book_complete = (
                quote is not None
                and quote.bid_price is not None
                and quote.ask_price is not None
                and quote.bid_price > 0
                and quote.ask_price > 0
            )
            ready = (
                watched_symbol == normalized_symbol
                and subscribed
                and healthy
                and book_complete
                and book_age is not None
                and book_age <= maximum_age
            )
            return {
                "contract_version": "local-paper-quote-watch-v1",
                "owner_id": normalized_owner,
                "symbol": normalized_symbol,
                "watched": watched_symbol == normalized_symbol,
                "subscribed": subscribed,
                "streaming": self._streaming_enabled,
                "data_health_state": "HEALTHY" if healthy else "BLOCKED",
                "bid_price": (
                    str(quote.bid_price)
                    if quote is not None and quote.bid_price is not None
                    else None
                ),
                "ask_price": (
                    str(quote.ask_price)
                    if quote is not None and quote.ask_price is not None
                    else None
                ),
                "book_received_at": (
                    quote.book_received_at.isoformat()
                    if quote is not None and quote.book_received_at is not None
                    else None
                ),
                "book_age_seconds": book_age,
                "max_book_age_seconds": maximum_age,
                "ready": ready,
            }

    def close(self) -> None:
        """停止行情訂閱並依序處理已排入的 quote updates。"""
        self._deactivate_streaming(clear_runtime_state=True)

    def _get_stock(self, symbol: str) -> StockData:
        try:
            stock = self._provider.get_stock(symbol)
        except KeyError as error:
            raise SimulationValidationError(f"找不到股票：{symbol}") from error

        if not math.isfinite(stock.price) or stock.price <= 0:
            raise SimulationValidationError(f"{symbol} 沒有可用的正確報價")
        return stock

    def _get_stock_identity(self, symbol: str) -> tuple[str, str]:
        try:
            canonical_symbol, name = self._provider.get_stock_identity(symbol)
        except KeyError as error:
            raise SimulationValidationError(f"找不到股票：{symbol}") from error
        normalized_symbol = str(canonical_symbol).strip().upper()
        normalized_name = str(name).strip()
        if not normalized_symbol or not normalized_name:
            raise SimulationValidationError(f"找不到股票：{symbol}")
        return normalized_symbol, normalized_name

    def _get_local_paper_instrument_descriptor(
        self,
        symbol: str,
    ) -> LocalPaperInstrumentDescriptorV1:
        try:
            descriptor = self._provider.get_local_paper_instrument_descriptor(symbol)
        except KeyError as error:
            raise SimulationValidationError(f"找不到股票：{symbol}") from error
        if (
            descriptor is None
            or descriptor.symbol != symbol
            or descriptor.normalized_product_class
            is not LocalPaperProductClass.COMMON_STOCK
            or descriptor.exchange_raw not in {"TWSE", "TPEX", "TSE", "OTC"}
        ):
            raise SimulationValidationError("UNSUPPORTED_COST_POLICY_SCOPE")
        return descriptor

    @staticmethod
    def _is_marketable_price(order: SimulationOrder, execution_price: Decimal) -> bool:
        return (
            order.limit_price >= execution_price
            if order.side is OrderSide.BUY
            else order.limit_price <= execution_price
        )

    def _stream_execution_price(
        self,
        order: SimulationOrder,
        quote: _QuoteState,
    ) -> Decimal | None:
        if quote.book_received_at is None or quote.book_at is None:
            return None
        _, fresh = _exact_book_freshness(
            now=self._now(),
            received_at=quote.book_received_at,
            max_age_seconds=self._max_book_age_seconds,
        )
        if not fresh:
            return None
        return quote.ask_price if order.side is OrderSide.BUY else quote.bid_price

    def _execution_decision(
        self,
        order: SimulationOrder,
        reference_price: Decimal | None,
        reference_source: ReferenceSource,
    ) -> _ExecutionDecision | None:
        if reference_price is None:
            return None
        if not self._cost_policy_enabled:
            if not self._is_marketable_price(order, reference_price):
                order.waiting_reason = "LIMIT_NOT_REACHED"
                return None
            order.waiting_reason = None
            return _ExecutionDecision(
                reference_price=reference_price,
                reference_source=reference_source,
                fill_price=reference_price,
            )
        try:
            slippage = decide_fixed_adverse_slippage(
                side=ExecutionSide(order.side.value),
                reference_price=reference_price,
                reference_source=reference_source,
                configured_slippage_bps=self._slippage_bps,
                limit_price=order.limit_price,
            )
        except ValueError:
            order.waiting_reason = "EXECUTION_POLICY_INTEGRITY_ERROR"
            return None
        if not slippage.limit_satisfied:
            order.waiting_reason = "SLIPPAGE_ADJUSTED_LIMIT_NOT_REACHED"
            return None
        order.waiting_reason = None
        return _ExecutionDecision(
            reference_price=slippage.reference_price,
            reference_source=slippage.reference_source,
            fill_price=slippage.adjusted_price,
            slippage=slippage,
        )

    @staticmethod
    def _book_fill_quantity(order: SimulationOrder, quote: _QuoteState) -> int:
        available = (
            quote.ask_available_quantity
            if order.side is OrderSide.BUY
            else quote.bid_available_quantity
        )
        if available is None:
            return order.remaining_quantity
        return min(order.remaining_quantity, available)

    @staticmethod
    def _consume_book_quantity(
        order: SimulationOrder,
        quote: _QuoteState,
        quantity: int,
    ) -> None:
        if order.side is OrderSide.BUY and quote.ask_available_quantity is not None:
            quote.ask_available_quantity = max(0, quote.ask_available_quantity - quantity)
        elif order.side is OrderSide.SELL and quote.bid_available_quantity is not None:
            quote.bid_available_quantity = max(0, quote.bid_available_quantity - quantity)

    def _available_to_sell(
        self,
        order: SimulationOrder,
        exclude_order_id: str | None = None,
    ) -> int:
        exposure_id = order.target_exposure_id
        if exposure_id is None:
            return 0
        position = self._positions.get(exposure_id)
        if position is not None and self._sell_target_conflicts(order):
            return 0
        held_quantity = position.quantity if position else 0
        pending_quantity = sum(
            order.remaining_quantity
            for order in self._orders.values()
            if (
                order.target_exposure_id == exposure_id
                and order.side is OrderSide.SELL
                and order.status in _ACTIVE_ORDER_STATUSES
                and order.order_id != exclude_order_id
            )
        )
        return held_quantity - pending_quantity

    def _sell_target_conflicts(self, order: SimulationOrder) -> bool:
        exposure = order.exposure
        exposure_id = order.target_exposure_id
        if exposure is None or exposure_id != exposure.exposure_id:
            return True
        position = self._positions.get(exposure_id)
        return position is not None and (
            position.symbol != order.symbol or position.exposure != exposure
        )

    def _fill(
        self,
        order: SimulationOrder,
        execution: _ExecutionDecision,
        *,
        fill_quantity: int | None = None,
    ) -> int:
        """在 lock 內以已驗證的 snapshot／買一／賣一完成本機紙上成交。"""
        quantity = min(fill_quantity or order.remaining_quantity, order.remaining_quantity)
        if quantity <= 0:
            return 0
        fill_price = execution.fill_price
        if order.exposure is not None and not self._owner_matches(
            origin=order.origin,
            strategy_id=order.strategy_id,
            exposure=order.exposure,
        ):
            self._reject(order, "成交時 exposure owner 衝突")
            return 0

        accounting: FillAccountingDecision | None = None
        if self._cost_policy_enabled:
            if execution.slippage is None or order.instrument_descriptor is None:
                order.waiting_reason = "EXECUTION_POLICY_INTEGRITY_ERROR"
                return 0
            try:
                accounting = decide_fill_accounting(
                    slippage=execution.slippage,
                    quantity_shares=quantity,
                    cumulative_order_gross_before=order.filled_notional,
                    already_booked_commission=order.filled_commission,
                    cumulative_order_tax_before=order.filled_tax,
                    instrument_descriptor=order.instrument_descriptor,
                )
            except ValueError:
                order.waiting_reason = "EXECUTION_POLICY_INTEGRITY_ERROR"
                return 0
            fill_amount = accounting.gross_amount
            incremental_commission = accounting.commission
            fill_tax = accounting.tax
            net_cash_effect = accounting.net_cash_effect
        else:
            fill_amount = quantity * fill_price
            cumulative_gross = order.filled_notional + fill_amount
            cumulative_commission = self._settings.commission_for(cumulative_gross)
            incremental_commission = cumulative_commission - order.filled_commission
            fill_tax = Decimal("0")
            net_cash_effect = (
                -(fill_amount + incremental_commission)
                if order.side is OrderSide.BUY
                else fill_amount - incremental_commission
            )

        if order.side is OrderSide.BUY:
            cash_debit = -net_cash_effect
            if cash_debit > self._cash:
                self._reject(
                    order,
                    "目前報價造成可用虛擬現金不足",
                )
                return 0
            if order.exposure is None:
                self._reject(order, "委託缺少 exposure identity")
                return 0
            exposure_id = order.exposure.exposure_id
            position = self._positions.get(exposure_id)
            if position is None:
                self._positions[exposure_id] = SimulationPosition(
                    symbol=order.symbol,
                    name=order.name,
                    quantity=quantity,
                    average_price=fill_price,
                    owner_origin=order.origin,
                    commission_cost=incremental_commission,
                    owner_strategy_id=order.strategy_id,
                    owner_strategy_version=order.strategy_version,
                    exposure=order.exposure,
                )
                self._exposure_identities[exposure_id] = order.exposure
                self._exposure_symbols[exposure_id] = order.symbol
            else:
                if position.symbol != order.symbol or position.exposure != order.exposure:
                    self._reject(order, "成交時 exposure identity 衝突")
                    return 0
                total_quantity = position.quantity + quantity
                position.average_price = (
                    position.average_price * position.quantity
                    + fill_price * quantity
                ) / total_quantity
                position.commission_cost += incremental_commission
                position.quantity = total_quantity
            self._cash += net_cash_effect
            self._daily_filled_buy_notional += fill_amount
        else:
            exposure_id = order.target_exposure_id
            position = self._positions.get(exposure_id or "")
            if self._sell_target_conflicts(order):
                self._reject(
                    order,
                    "成交時 target exposure 與委託股票或 identity 不一致",
                )
                return 0
            if position is None or position.quantity < quantity:
                self._reject(
                    order,
                    "可賣出持股不足",
                )
                return 0

            allocated_buy_commission = (
                position.commission_cost * quantity / position.quantity
            )
            realized_pnl = (
                (fill_price - position.average_price) * quantity
                - allocated_buy_commission
                - incremental_commission
                - fill_tax
            )
            self._realized_pnl_by_exposure[exposure_id] = (
                self._realized_pnl_by_exposure.get(exposure_id, Decimal("0"))
                + realized_pnl
            )
            position.quantity -= quantity
            position.commission_cost -= allocated_buy_commission
            self._cash += net_cash_effect
            if position.quantity == 0:
                del self._positions[exposure_id]

        order.filled_notional += fill_price * quantity
        order.filled_commission += incremental_commission
        order.filled_tax += fill_tax
        order.filled_quantity += quantity
        order.filled_price = order.filled_notional / order.filled_quantity
        order.last_fill_price = fill_price
        order.last_fill_quantity = quantity
        order.last_fill_commission = incremental_commission
        order.last_fill_tax = fill_tax
        order.last_reference_price = execution.reference_price
        order.last_reference_source = execution.reference_source.value
        order.last_net_cash_effect = net_cash_effect
        if accounting is not None:
            order.filled_slippage_cost += accounting.slippage_cost
            order.configured_slippage_bps = accounting.configured_slippage_bps
            order.last_realized_slippage_bps = accounting.realized_slippage_bps
            order.last_slippage_cost = accounting.slippage_cost
            order.fee_policy_version = accounting.fee_policy_version
            order.rounding_policy_version = accounting.rounding_policy_version
            order.slippage_policy_version = accounting.slippage_policy_version
            order.price_tick_policy_version = accounting.price_tick_policy_version
        order.fill_sequence += 1
        if order.remaining_quantity == 0:
            order.status = OrderStatus.FILLED
            self._reserved_buy_notional_by_order.pop(order.order_id, None)
        else:
            order.status = OrderStatus.PARTIALLY_FILLED
            if order.side is OrderSide.BUY:
                self._reserved_buy_notional_by_order[order.order_id] = (
                    self._order_cash_reservation(order)
                )
        now = self._now()
        order.updated_at = (
            now
            if now > order.updated_at
            else order.updated_at + timedelta(microseconds=1)
        )
        return quantity

    def _reject(
        self,
        order: SimulationOrder,
        reason: str,
    ) -> None:
        order.status = OrderStatus.REJECTED
        order.reason = reason
        self._reserved_buy_notional_by_order.pop(order.order_id, None)
        order.updated_at = self._now()

    def _end_order(
        self,
        order: SimulationOrder,
        *,
        status: OrderStatus,
        reason: str,
        alert_code: str,
        alert_message: str,
    ) -> None:
        order.status = status
        order.reason = reason
        order.updated_at = self._now()
        self._reserved_buy_notional_by_order.pop(order.order_id, None)
        self._alerts.append(
            {
                "alert_id": f"{alert_code}:{order.order_id}:{order.updated_at.isoformat()}",
                "code": alert_code,
                "severity": "HIGH",
                "order_id": order.order_id,
                "symbol": order.symbol,
                "message": alert_message,
                "created_at": order.updated_at.isoformat(),
                "acknowledged": False,
            }
        )

    def _notify_terminal_order(self, payload: dict[str, Any]) -> None:
        with self._lock:
            handler = self._terminal_order_handler
        if handler is None:
            return
        try:
            handler(payload)
        except Exception as error:
            with self._lock:
                self._quote_ingress_blocked = True
                self._stream_error = (
                    "模擬成交 Journal 寫入失敗，已停止接受新的模擬委託："
                    f"{type(error).__name__}"
                )

    def _quote_for(self, position: SimulationPosition) -> _QuoteState | None:
        return self._quotes.get(position.symbol)

    def _current_price(self, position: SimulationPosition) -> Decimal:
        quote = self._quote_for(position)
        if quote is None:
            return position.average_price
        if quote.last_price is not None:
            return quote.last_price
        if quote.snapshot is not None:
            return self._stock_price(quote.snapshot)
        return position.average_price

    def _run_quote_worker(self) -> None:
        while True:
            update = self._quote_updates.get()
            if update is None:
                return
            subscriptions_changed = self._apply_quote_update(update)
            if subscriptions_changed:
                self._sync_quote_subscriptions()

    def _apply_quote_update(self, update: RealtimeQuoteUpdate) -> bool:
        self._roll_trading_day()
        notifications: list[dict[str, Any]] = []
        with self._lock:
            if self._quote_ingress_blocked:
                return False
            desired_symbols = self._desired_quote_symbols()
            if update.symbol not in desired_symbols:
                return False
            quote = self._quotes.get(update.symbol)
            if quote is None:
                return False

            if update.kind == "TICK":
                if quote.last_trade_at and update.exchange_timestamp < quote.last_trade_at:
                    return False
                quote.last_price = self._optional_money(update.last_price)
                quote.last_trade_at = update.exchange_timestamp
            elif update.kind == "BIDASK":
                # Without an exchange sequence number, an equal timestamp cannot
                # prove a fresh best-level volume tranche. Replaying it would
                # replenish already-consumed liquidity and overfill the order.
                if quote.book_at and update.exchange_timestamp <= quote.book_at:
                    return False
                quote.bid_price = self._optional_money(update.bid_price)
                quote.ask_price = self._optional_money(update.ask_price)
                quote.book_at = update.exchange_timestamp
                quote.book_received_at = update.received_at
                quote.instrument_tradable = (
                    None if update.suspended is None else not update.suspended
                )
                quote.bid_available_quantity = (
                    update.bid_volume_lots * 1_000
                    if update.bid_volume_lots is not None
                    else None
                )
                quote.ask_available_quantity = (
                    update.ask_volume_lots * 1_000
                    if update.ask_volume_lots is not None
                    else None
                )
            else:
                return False

            quote.received_at = max(
                quote.received_at or update.received_at,
                update.received_at,
            )
            filled = False
            if update.kind == "BIDASK":
                for order in self._orders.values():
                    if order.symbol != update.symbol or order.status not in _ACTIVE_ORDER_STATUSES:
                        continue
                    execution = self._execution_decision(
                        order,
                        self._stream_execution_price(order, quote),
                        (
                            ReferenceSource.BEST_ASK
                            if order.side is OrderSide.BUY
                            else ReferenceSource.BEST_BID
                        ),
                    )
                    if execution is not None:
                        fill_quantity = self._book_fill_quantity(order, quote)
                        if fill_quantity > 0:
                            executed_quantity = self._fill(
                                order,
                                execution,
                                fill_quantity=fill_quantity,
                            )
                            if executed_quantity > 0:
                                self._consume_book_quantity(
                                    order,
                                    quote,
                                    executed_quantity,
                                )
                            notifications.append(self._order_payload(order))
                            filled = True
        for payload in notifications:
            self._notify_terminal_order(payload)
        return filled

    def _desired_quote_symbols(self) -> set[str]:
        return {
            *(position.symbol for position in self._positions.values()),
            *self._quote_watch_by_owner.values(),
            *(
                order.symbol
                for order in self._orders.values()
                if order.status in _ACTIVE_ORDER_STATUSES
            ),
        }

    def _sync_quote_subscriptions(self, *, fail_closed: bool = False) -> None:
        if not self._streaming_enabled:
            return
        with self._subscription_lock:
            with self._lock:
                if self._quote_ingress_blocked:
                    return
                desired_symbols = self._desired_quote_symbols()
            try:
                subscribed = self._provider.sync_quote_subscriptions(desired_symbols)
            except Exception as error:
                with self._lock:
                    self._stream_error = f"Shioaji 即時行情訂閱失敗：{error}"
                if fail_closed:
                    raise
                return
            with self._lock:
                self._subscribed_symbols = set(subscribed)
                self._stream_error = None

    @staticmethod
    def _normalize_symbol(symbol: str) -> str:
        normalized = str(symbol).strip().upper()
        if not normalized:
            raise SimulationValidationError("請輸入股票代碼")
        return normalized

    @staticmethod
    def _normalize_side(side: str) -> OrderSide:
        try:
            return OrderSide(str(side).strip().upper())
        except ValueError as error:
            raise SimulationValidationError("交易方向只支援 BUY 或 SELL") from error

    @staticmethod
    def _normalize_lots(lots: int) -> int:
        if isinstance(lots, bool) or not isinstance(lots, int) or lots <= 0:
            raise SimulationValidationError("張數必須是大於 0 的整數")
        return lots

    @staticmethod
    def _normalize_quantity_shares(quantity_shares: int) -> int:
        if (
            isinstance(quantity_shares, bool)
            or not isinstance(quantity_shares, int)
            or quantity_shares <= 0
        ):
            raise SimulationValidationError("股數必須是大於 0 的整數")
        return quantity_shares

    @classmethod
    def _resolve_quantity_shares(
        cls,
        *,
        quantity_shares: int | None,
        lots: int | None,
    ) -> int:
        if quantity_shares is not None and lots is not None:
            raise SimulationValidationError("股數與張數不可同時提供")
        if quantity_shares is not None:
            return cls._normalize_quantity_shares(quantity_shares)
        if lots is not None:
            return cls._normalize_lots(lots) * 1_000
        raise SimulationValidationError("請輸入股數")

    @classmethod
    def _restored_quantity_shares(cls, raw: dict[str, Any]) -> int:
        if raw.get("quantity_shares") is not None:
            quantity = int(raw["quantity_shares"])
        elif raw.get("quantity") is not None:
            quantity = int(raw["quantity"])
        else:
            quantity = int(raw["lots"]) * 1_000
        return cls._normalize_quantity_shares(quantity)

    @staticmethod
    def _restored_instrument_descriptor(
        raw: dict[str, Any],
    ) -> LocalPaperInstrumentDescriptorV1 | None:
        snapshot = raw.get("instrument_descriptor_snapshot")
        if snapshot is None:
            return None
        if not isinstance(snapshot, Mapping):
            raise SimulationStateError("instrument descriptor snapshot 損壞")
        try:
            descriptor = LocalPaperInstrumentDescriptorV1(
                symbol=str(snapshot["symbol"]),
                exchange_raw=str(snapshot["exchange_raw"]),
                security_type_raw=str(snapshot["security_type_raw"]),
                product_category_raw=str(snapshot["product_category_raw"]),
                normalized_product_class=LocalPaperProductClass(
                    str(snapshot["normalized_product_class"])
                ),
                source_identity=str(snapshot["source_identity"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise SimulationStateError("instrument descriptor snapshot 損壞") from error
        expected_digest = raw.get("instrument_descriptor_digest")
        if expected_digest is not None and descriptor.digest != str(expected_digest):
            raise SimulationStateError("instrument descriptor digest 不一致")
        return descriptor

    @staticmethod
    def _normalize_price(limit_price: Decimal | float | int | str) -> Decimal:
        try:
            normalized = Decimal(str(limit_price))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise SimulationValidationError("限價必須是數字") from error
        if not normalized.is_finite() or normalized <= 0:
            raise SimulationValidationError("限價必須是大於 0 的有限數字")
        return normalized

    @staticmethod
    def _normalize_idempotency_key(idempotency_key: str) -> str:
        normalized = str(idempotency_key).strip()
        if not normalized:
            raise SimulationValidationError("缺少冪等識別碼")
        if len(normalized) > 128:
            raise SimulationValidationError("冪等識別碼過長")
        return normalized

    @staticmethod
    def _optional_identity(value: str | None) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            raise SimulationValidationError("策略歸屬識別不可為空")
        return normalized

    @staticmethod
    def _owner_matches(
        *,
        origin: str,
        strategy_id: str | None,
        exposure: ExposureIdentity,
    ) -> bool:
        if origin != exposure.owner_origin:
            return False
        if origin != "STRATEGY_AUTOMATED":
            return True
        return strategy_id == exposure.owner_id

    def _now(self) -> datetime:
        if self._mutation_boundary_time is not None:
            return self._mutation_boundary_time
        return self._clock.now().astimezone(_TAIPEI)

    def _market_value(self) -> Decimal:
        return sum(
            (
                position.quantity * self._current_price(position)
                for position in self._positions.values()
            ),
            Decimal("0"),
        )

    def _ensure_trading_day(self) -> None:
        trading_date = self._clock.session_date()
        if trading_date == self._trading_date:
            return
        self._opening_equity = self._cash + self._market_value()
        self._opening_realized_pnl = sum(
            self._realized_pnl_by_exposure.values(),
            Decimal("0"),
        )
        self._daily_filled_buy_notional = Decimal("0")
        self._trading_date = trading_date
        self._pending_daily_baselines.append(self._daily_baseline_payload())

    def _roll_trading_day(self) -> None:
        with self._lock:
            self._ensure_trading_day()
            notifications = self._pending_daily_baselines
            self._pending_daily_baselines = []
            handler = self._daily_baseline_handler
        if handler is None:
            return
        for payload in notifications:
            try:
                handler(payload)
            except Exception as error:
                with self._lock:
                    self._quote_ingress_blocked = True
                    self._stream_error = (
                        "交易日風控基準 Journal 寫入失敗，已停止接受新的模擬委託："
                        f"{type(error).__name__}"
                    )

    def _daily_baseline_payload(self) -> dict[str, Any]:
        return {
            "trading_date": self._trading_date.isoformat(),
            "opening_equity": str(self._opening_equity),
            "opening_realized_pnl": str(self._opening_realized_pnl),
            "includes_unrealized_pnl": True,
            "created_at": self._now().isoformat(),
        }

    def _position_payload(
        self,
        position: SimulationPosition,
        *,
        realized_pnl: Decimal,
        exposure: ExposureIdentity | None = None,
    ) -> dict[str, Any]:
        quote = self._quote_for(position)
        current_price = self._current_price(position)
        market_value = position.quantity * current_price
        unrealized_pnl = position.quantity * (
            current_price - position.average_price
        ) - position.commission_cost
        quote_at = None
        if quote is not None:
            quote_at = quote.received_at
            if quote_at is None and quote.snapshot is not None:
                quote_at = quote.snapshot.timestamp
        payload = {
            "symbol": position.symbol,
            "name": position.name,
            "quantity": position.quantity,
            "average_price": float(position.average_price),
            "commission_cost": float(position.commission_cost),
            "current_price": float(current_price),
            "market_value": float(market_value),
            "unrealized_pnl": float(unrealized_pnl),
            "unrealized_pnl_pct": float(
                unrealized_pnl
                / (position.quantity * position.average_price)
                * 100
                if position.average_price > 0
                else Decimal("0")
            ),
            "realized_pnl": float(realized_pnl),
            "owner_origin": position.owner_origin,
            "owner_strategy_id": position.owner_strategy_id,
            "owner_strategy_version": position.owner_strategy_version,
            "bid_price": float(quote.bid_price) if quote and quote.bid_price else None,
            "ask_price": float(quote.ask_price) if quote and quote.ask_price else None,
            "last_quote_at": quote_at.isoformat() if quote_at else None,
            "quote_received_at": (
                quote.received_at.isoformat() if quote and quote.received_at else None
            ),
            "book_received_at": (
                quote.book_received_at.isoformat()
                if quote and quote.book_received_at
                else None
            ),
            "quote_source": (
                "SHIOAJI_TICK_BIDASK" if quote and quote.received_at else "SNAPSHOT"
            ),
        }
        if exposure is not None:
            payload.update(
                {
                    "exposure_id": exposure.exposure_id,
                    "exposure_identity": exposure.to_payload(),
                    "holding_horizon": exposure.holding_horizon.value,
                    "no_overnight_managed": exposure.no_overnight_managed,
                }
            )
        return payload

    def _order_payload(self, order: SimulationOrder) -> dict[str, Any]:
        quote = self._quotes.get(order.symbol)
        waiting_reason = None
        if order.status in _ACTIVE_ORDER_STATUSES and self._stream_capable:
            if quote is None or quote.book_received_at is None:
                waiting_reason = "WAITING_FOR_FIRST_BIDASK"
            elif self._stream_execution_price(order, quote) is None:
                waiting_reason = "WAITING_FOR_FRESH_BIDASK"
            else:
                waiting_reason = order.waiting_reason or "LIMIT_NOT_REACHED"
        elif order.status in _ACTIVE_ORDER_STATUSES:
            waiting_reason = order.waiting_reason
        descriptor_snapshot = (
            order.instrument_descriptor.to_dict()
            if order.instrument_descriptor is not None
            else None
        )
        payload = {
            "order_id": order.order_id,
            "idempotency_key": order.idempotency_key,
            "origin": order.origin,
            "strategy_id": order.strategy_id,
            "strategy_version": order.strategy_version,
            "symbol": order.symbol,
            "name": order.name,
            "side": order.side.value,
            "lots": order.lots,
            "quantity_shares": order.quantity_shares,
            "quantity": order.quantity,
            "remaining_quantity": order.remaining_quantity,
            "limit_price": float(order.limit_price),
            "limit_price_decimal": str(order.limit_price),
            "estimated_amount": float(order.quantity * order.limit_price),
            "status": order.status.value,
            "submitted_at": order.submitted_at.isoformat(),
            "updated_at": order.updated_at.isoformat(),
            "filled_price": float(order.filled_price) if order.filled_price is not None else None,
            "filled_quantity": order.filled_quantity,
            "filled_commission": float(order.filled_commission),
            "filled_commission_decimal": str(order.filled_commission),
            "filled_tax": str(order.filled_tax),
            "filled_slippage_cost": str(order.filled_slippage_cost),
            "last_fill_price": (
                float(order.last_fill_price)
                if order.last_fill_price is not None
                else None
            ),
            "last_fill_price_decimal": (
                str(order.last_fill_price)
                if order.last_fill_price is not None
                else None
            ),
            "last_fill_quantity": order.last_fill_quantity,
            "last_fill_commission": float(order.last_fill_commission),
            "last_fill_commission_decimal": str(order.last_fill_commission),
            "last_fill_tax": str(order.last_fill_tax),
            "last_reference_price": (
                str(order.last_reference_price)
                if order.last_reference_price is not None
                else None
            ),
            "last_reference_source": order.last_reference_source,
            "configured_slippage_bps": (
                str(order.configured_slippage_bps)
                if order.configured_slippage_bps is not None
                else None
            ),
            "last_realized_slippage_bps": (
                str(order.last_realized_slippage_bps)
                if order.last_realized_slippage_bps is not None
                else None
            ),
            "last_slippage_cost": str(order.last_slippage_cost),
            "last_net_cash_effect": (
                str(order.last_net_cash_effect)
                if order.last_net_cash_effect is not None
                else None
            ),
            "fee_policy_version": order.fee_policy_version,
            "rounding_policy_version": order.rounding_policy_version,
            "slippage_policy_version": order.slippage_policy_version,
            "price_tick_policy_version": order.price_tick_policy_version,
            "instrument_descriptor_snapshot": descriptor_snapshot,
            "instrument_descriptor_digest": (
                order.instrument_descriptor.digest
                if order.instrument_descriptor is not None
                else None
            ),
            "fill_sequence": order.fill_sequence,
            "filled_amount": (
                float(order.filled_notional)
                if order.filled_quantity > 0
                else None
            ),
            "filled_amount_decimal": (
                str(order.filled_notional)
                if order.filled_quantity > 0
                else None
            ),
            "attempt": order.attempt,
            "predecessor_order_id": order.predecessor_order_id,
            "timeout_at": order.timeout_at.isoformat() if order.timeout_at else None,
            "expires_at": order.expires_at.isoformat() if order.expires_at else None,
            "trading_date": self._trading_date.isoformat(),
            "opening_equity": float(self._opening_equity),
            "reason": order.reason,
            "waiting_reason": waiting_reason,
            "bid_price": (
                float(quote.bid_price)
                if quote is not None and quote.bid_price is not None
                else None
            ),
            "ask_price": (
                float(quote.ask_price)
                if quote is not None and quote.ask_price is not None
                else None
            ),
            "last_quote_at": (
                quote.book_at.isoformat()
                if quote is not None and quote.book_at is not None
                else None
            ),
            "quote_received_at": (
                quote.book_received_at.isoformat()
                if quote is not None and quote.book_received_at is not None
                else None
            ),
            "fill_source": "paper_simulation",
            "provider_identity": self._provider_identity,
            "execution_authority": False,
        }
        if order.exposure is not None:
            payload.update(
                {
                    "exposure_identity": order.exposure.to_payload(),
                    "position_action": (
                        order.position_action.value
                        if order.position_action is not None
                        else None
                    ),
                    "target_exposure_id": order.target_exposure_id,
                    "execution_reason_category": (
                        order.execution_reason_category.value
                        if order.execution_reason_category is not None
                        else None
                    ),
                    "execution_reason_code": order.execution_reason_code,
                }
            )
        return payload

    def risk_snapshot(
        self,
        symbol: str,
        *,
        target_exposure_id: str | None = None,
    ) -> dict[str, Any]:
        """Return local-only evidence for the command facade without provider I/O."""
        normalized_symbol = self._normalize_symbol(symbol)
        normalized_exposure_id = self._optional_identity(target_exposure_id)
        self._roll_trading_day()
        with self._lock:
            matching_positions = [
                position
                for exposure_id, position in self._positions.items()
                if position.symbol == normalized_symbol
                and (
                    normalized_exposure_id is None
                    or exposure_id == normalized_exposure_id
                )
            ]
            pending = [
                order
                for order in self._orders.values()
                if order.symbol == normalized_symbol and order.status in _ACTIVE_ORDER_STATUSES
                and (
                    normalized_exposure_id is None
                    or (
                        order.exposure is not None
                        and order.exposure.exposure_id == normalized_exposure_id
                    )
                    or order.target_exposure_id == normalized_exposure_id
                )
            ]
            quote = self._quotes.get(normalized_symbol)
            book_age = None
            if quote is not None and quote.book_received_at is not None:
                book_age = max(
                    0,
                    int((self._now() - quote.book_received_at).total_seconds()),
                )
            return {
                "data_health_state": (
                    "BLOCKED"
                    if self._quote_ingress_blocked
                    or (self._stream_capable and not self._streaming_enabled)
                    else "HEALTHY"
                ),
                "available_cash": self._available_cash(),
                "current_position_shares": sum(
                    position.quantity for position in matching_positions
                ),
                "pending_buy_shares": sum(
                    order.remaining_quantity
                    for order in pending
                    if order.side is OrderSide.BUY
                ),
                "pending_sell_shares": sum(
                    order.remaining_quantity
                    for order in pending
                    if order.side is OrderSide.SELL
                ),
                "daily_realized_pnl": sum(
                    self._realized_pnl_by_exposure.values(),
                    Decimal("0"),
                )
                - self._opening_realized_pnl,
                "daily_filled_buy_notional": self._daily_filled_buy_notional,
                "pending_buy_notional": self._daily_reserved_buy_notional(),
                "daily_loss": max(
                    Decimal("0"),
                    self._opening_equity - (self._cash + self._market_value()),
                ),
                "book_age_seconds": book_age,
            }

    def execution_admission_context(
        self,
        symbol: str,
        side: str,
        *,
        max_book_age_seconds: int,
    ) -> dict[str, object]:
        """Read tradability and executable-price evidence before order mutation."""

        normalized_symbol = self._normalize_symbol(symbol)
        normalized_side = self._normalize_side(side)
        if (
            isinstance(max_book_age_seconds, bool)
            or not isinstance(max_book_age_seconds, int)
            or max_book_age_seconds < 0
        ):
            raise SimulationValidationError("max_book_age_seconds 必須是非負整數")
        if not self._stream_capable:
            try:
                stock = self._get_stock(normalized_symbol)
            except SimulationValidationError:
                return {
                    "instrument_tradable": False,
                    "executable_book_ready": False,
                    "data_health_state": "BLOCKED",
                    "book_age_seconds": None,
                    "executable_price": None,
                }
            return {
                "instrument_tradable": stock.symbol == normalized_symbol,
                "executable_book_ready": False,
                "data_health_state": "BLOCKED",
                "book_age_seconds": None,
                "executable_price": None,
            }

        try:
            canonical_symbol, _ = self._get_stock_identity(normalized_symbol)
        except SimulationValidationError:
            return {
                "instrument_tradable": False,
                "executable_book_ready": False,
                "data_health_state": "BLOCKED",
                "book_age_seconds": None,
                "executable_price": None,
            }
        with self._lock:
            quote = self._quotes.get(canonical_symbol)
            book_age = None
            book_fresh = False
            if quote is not None and quote.book_received_at is not None:
                book_age, book_fresh = _exact_book_freshness(
                    now=self._now(),
                    received_at=quote.book_received_at,
                    max_age_seconds=max_book_age_seconds,
                )
            price = (
                quote.ask_price
                if quote is not None and normalized_side is OrderSide.BUY
                else quote.bid_price
                if quote is not None
                else None
            )
            healthy = (
                not self._quote_ingress_blocked
                and self._streaming_enabled
                and self._stream_error is None
            )
            return {
                "instrument_tradable": (
                    canonical_symbol == normalized_symbol
                    and quote is not None
                    and quote.instrument_tradable is True
                ),
                "executable_book_ready": (
                    healthy
                    and price is not None
                    and price > 0
                    and book_fresh
                ),
                "data_health_state": "HEALTHY" if healthy else "BLOCKED",
                "book_age_seconds": book_age,
                "executable_price": (
                    format(price, "f") if price is not None and price > 0 else None
                ),
            }

    def order_for_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        with self._lock:
            order_id = self._order_ids_by_key.get(normalized_key)
            return self._order_payload(self._orders[order_id]) if order_id else None

    def cancel_order_for_idempotency_key(
        self,
        idempotency_key: str,
    ) -> dict[str, Any] | None:
        normalized_key = self._normalize_idempotency_key(idempotency_key)
        with self._lock:
            order_id = self._cancel_order_ids_by_key.get(normalized_key)
            return self._order_payload(self._orders[order_id]) if order_id else None

    def record_risk_rejection(
        self,
        *,
        command: OrderCommand,
        reason: str,
    ) -> dict[str, Any]:
        """Project a RiskGate rejection without calling a broker or quote stream."""
        normalized_symbol = self._normalize_symbol(command.symbol)
        normalized_side = self._normalize_side(command.side.value)
        normalized_quantity_shares = self._normalize_quantity_shares(
            command.quantity_shares
        )
        normalized_price = self._normalize_price(command.limit_price)
        normalized_key = self._normalize_idempotency_key(command.idempotency_key)
        with self._lock:
            existing_order_id = self._order_ids_by_key.get(normalized_key)
            if existing_order_id is not None:
                return self._order_payload(self._orders[existing_order_id])
            if self._stream_capable:
                stock_symbol, stock_name = self._get_stock_identity(normalized_symbol)
            else:
                stock = self._get_stock(normalized_symbol)
                stock_symbol, stock_name = stock.symbol, stock.name
            now = self._now()
            order = SimulationOrder(
                order_id=uuid4().hex,
                idempotency_key=normalized_key,
                origin=command.origin.value,
                symbol=stock_symbol,
                name=stock_name,
                side=normalized_side,
                quantity_shares=normalized_quantity_shares,
                limit_price=normalized_price,
                status=OrderStatus.REJECTED,
                submitted_at=now,
                updated_at=now,
                reason=reason,
                strategy_id=command.strategy_id,
                strategy_version=command.strategy_version,
                attempt=command.attempt,
                predecessor_order_id=command.predecessor_order_id,
                exposure=command.exposure,
                position_action=command.position_action,
                target_exposure_id=command.target_exposure_id,
                execution_reason_category=command.execution_reason_category,
                execution_reason_code=command.execution_reason_code,
            )
            self._orders[order.order_id] = order
            self._order_ids_by_key[normalized_key] = order.order_id
            return self._order_payload(order)

    def _reserved_cash(self) -> Decimal:
        return sum(self._reserved_buy_notional_by_order.values(), Decimal("0"))

    def _daily_reserved_buy_notional(
        self,
        *,
        exclude_order_id: str | None = None,
    ) -> Decimal:
        return sum(
            (
                order.remaining_quantity * order.limit_price
                for order in self._orders.values()
                if order.side is OrderSide.BUY
                and order.status in _ACTIVE_ORDER_STATUSES
                and order.order_id != exclude_order_id
            ),
            Decimal("0"),
        )

    def _order_cash_reservation(self, order: SimulationOrder) -> Decimal:
        remaining_gross = order.remaining_quantity * order.limit_price
        cumulative_gross = order.filled_notional + remaining_gross
        projected_commission = (
            cumulative_commission_for(cumulative_gross)
            if self._cost_policy_enabled
            else self._settings.commission_for(cumulative_gross)
        )
        remaining_commission = max(
            Decimal("0"),
            projected_commission - order.filled_commission,
        )
        return remaining_gross + remaining_commission

    def _available_cash(self) -> Decimal:
        return self._cash - self._reserved_cash()

    def _stream_health(self) -> str:
        if self._quote_ingress_blocked:
            return "BLOCKED"
        if self._stream_capable and not self._streaming_enabled:
            return "DEGRADED"
        return "HEALTHY"

    @staticmethod
    def _money(value: Decimal | float | int | str, field_name: str) -> Decimal:
        try:
            normalized = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError) as error:
            raise ValueError(f"{field_name} 必須是數字") from error
        if not normalized.is_finite():
            raise ValueError(f"{field_name} 必須是有限數字")
        return normalized

    @classmethod
    def _optional_money(cls, value: object) -> Decimal | None:
        if value is None:
            return None
        try:
            normalized = cls._money(value, "quote")
        except ValueError:
            return None
        return normalized if normalized > 0 else None

    @classmethod
    def _stock_price(cls, stock: StockData) -> Decimal:
        return cls._money(stock.price, "stock.price")
