"""Shioaji Tick+BidAsk adapter for the market-data-only Momentum runtime."""

from __future__ import annotations

import hashlib
import os
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from threading import Lock, RLock
from typing import Callable
from zoneinfo import ZoneInfo

from market_data.events import (
    AggressorSide,
    BidAskEvent,
    EventEnvelope,
    InstrumentReference,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)
from market_data.momentum_stream import (
    LifecycleEventHandler,
    MarketEventHandler,
    QualificationBootstrapEvidence,
    StreamLifecycleEvent,
    StreamLifecycleEventType,
    StreamQuotePart,
    StreamSubscriptionAction,
)
from runtime.clock import Clock, SystemClock


TAIPEI = ZoneInfo("Asia/Taipei")
SOURCE_MODE = "TICK_BIDASK"


class ShioajiMomentumStream:
    """Normalize SDK callbacks and keep subscription acknowledgement explicit."""

    def __init__(
        self,
        api: object,
        *,
        session_id: str,
        clock: Clock | None = None,
        owns_session: bool = False,
        environment_identity: str = "shioaji:externally-owned-session",
    ) -> None:
        if not session_id.strip():
            raise ValueError("stream session_id must not be empty")
        self._api = api
        self._session_id = session_id
        self._clock = clock or SystemClock()
        self._owns_session = owns_session
        self._environment_identity = environment_identity
        self._lock = RLock()
        self._ingress_lock = Lock()
        self._event_handler: MarketEventHandler | None = None
        self._lifecycle_handler: LifecycleEventHandler | None = None
        self._running = False
        self._stopping = False
        self._sequence = 0
        self._pending: dict[
            tuple[StreamSubscriptionAction, str], set[StreamQuotePart]
        ] = {}
        self._subscribe_requested_parts: dict[str, set[StreamQuotePart]] = {}
        self._subscribe_failures: dict[str, str] = {}
        self._subscribed_symbols: set[str] = set()
        self._callback_errors: list[str] = []

    @classmethod
    def connect_from_env(
        cls,
        *,
        session_id: str,
        clock: Clock | None = None,
    ) -> "ShioajiMomentumStream":
        """Login for market data only; no certificate or trade subscription."""
        from dotenv import load_dotenv
        import shioaji as sj

        load_dotenv()
        api_key = os.getenv("SHIOAJI_API_KEY") or os.getenv("SJ_API_KEY")
        secret = (
            os.getenv("SHIOAJI_SECRET")
            or os.getenv("SJ_SECRET_KEY")
            or os.getenv("SJ_SEC_KEY")
        )
        if not api_key or not secret:
            raise RuntimeError("Shioaji data credentials are not configured")
        simulation = os.getenv("SJ_SIMULATION", "true").lower() != "false"
        api = sj.Shioaji(simulation=simulation)
        api.login(
            api_key=api_key,
            secret_key=secret,
            subscribe_trade=False,
        )
        return cls(
            api,
            session_id=session_id,
            clock=clock,
            owns_session=True,
            environment_identity=(
                f"shioaji:{getattr(sj, '__version__', 'unknown')}:"
                f"simulation={str(simulation).lower()}"
            ),
        )

    @property
    def callback_errors(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(self._callback_errors)

    @property
    def subscribed_symbols(self) -> frozenset[str]:
        with self._lock:
            return frozenset(self._subscribed_symbols)

    @property
    def environment_identity(self) -> str:
        return self._environment_identity

    def scanner_client(self):
        """Build the discovery-only Scanner adapter on the shared login."""
        from market_data.scanner import ShioajiScannerClient

        return ShioajiScannerClient(self._api, clock=self._clock.now)

    def start(
        self,
        event_handler: MarketEventHandler,
        lifecycle_handler: LifecycleEventHandler,
    ) -> None:
        with self._lock:
            if self._running:
                if (
                    self._event_handler is event_handler
                    and self._lifecycle_handler is lifecycle_handler
                ):
                    return
                raise RuntimeError("Momentum market-data stream already started")
            self._event_handler = event_handler
            self._lifecycle_handler = lifecycle_handler
            self._stopping = False
        try:
            self._api.set_on_tick_stk_v1_callback(self._on_tick)
            self._api.set_on_bidask_stk_v1_callback(self._on_bidask)
            self._api.set_event_callback(self._on_lifecycle)
        except Exception:
            with self._lock:
                self._event_handler = None
                self._lifecycle_handler = None
            raise
        with self._lock:
            self._running = True

    def instrument_reference(
        self,
        symbol: str,
        session_date: date,
    ) -> InstrumentReference:
        normalized = self._normalize_symbol(symbol)
        contract = self._stock_contract(normalized)
        reference = self._positive_decimal(getattr(contract, "reference", None))
        if reference is None:
            raise ValueError(f"{normalized} contract reference is unavailable")
        limit_up = self._positive_decimal(getattr(contract, "limit_up", None))
        limit_down = self._positive_decimal(
            getattr(contract, "limit_down", None)
        )
        exchange = getattr(contract, "exchange", "")
        exchange_value = getattr(exchange, "value", exchange)
        update_date = self._parse_date(getattr(contract, "update_date", None))
        unit = self._positive_integer(getattr(contract, "unit", None))
        if unit is None:
            raise ValueError(f"{normalized} contract unit is unavailable")
        return InstrumentReference(
            symbol=normalized,
            exchange=str(exchange_value),
            session_date=session_date,
            reference_price=reference,
            limit_up_price=limit_up,
            limit_down_price=limit_down,
            price_limit_applies=limit_up is not None and limit_down is not None,
            trading_unit_shares=unit,
            source_updated_at=update_date,
        )

    def qualification_bootstrap_evidence(
        self,
        symbol: str,
        session_date: date,
        prior_session_date: date,
    ) -> QualificationBootstrapEvidence:
        """Capture real contract/snapshot context without creating a trade path."""
        normalized = self._normalize_symbol(symbol)
        contract = self._stock_contract(normalized)
        reference = self.instrument_reference(normalized, session_date)
        if reference.source_updated_at != session_date:
            raise ValueError(
                f"{normalized} contract reference is not current-session evidence"
            )
        captured_at = self._clock.now()
        snapshots = self._api.snapshots([contract])
        received_at = self._clock.now()
        if not snapshots:
            raise ValueError(f"{normalized} bootstrap snapshot is unavailable")
        snapshot = snapshots[0]
        name = str(getattr(contract, "name", "")).strip()
        security_type_raw = getattr(contract, "security_type", None)
        security_type = str(
            getattr(security_type_raw, "value", security_type_raw) or ""
        ).strip()
        if not name or not security_type:
            raise ValueError(
                f"{normalized} contract name/security_type is unavailable"
            )
        previous_volume = self._integer(
            getattr(snapshot, "yesterday_volume", None)
        )
        if previous_volume is None or previous_volume < 0:
            raise ValueError(
                f"{normalized} previous-session volume is unavailable"
            )
        exchange = reference.exchange.strip().upper()
        provider_exchange = str(
            getattr(getattr(contract, "exchange", ""), "value", "")
            or exchange
        ).strip().upper()
        return QualificationBootstrapEvidence(
            reference=reference,
            instrument_name=name,
            security_type=security_type,
            instrument_source_identity=f"{provider_exchange}:{normalized}",
            captured_at=captured_at,
            received_at=received_at,
            prior_session_date=prior_session_date,
            previous_close=reference.reference_price,
            previous_session_volume_lots=previous_volume,
            snapshot_source_identity=(
                f"shioaji-snapshot:{provider_exchange}:{normalized}:"
                f"{received_at.isoformat()}"
            ),
        )

    def request_subscribe(self, symbol: str) -> None:
        self._request(symbol, StreamSubscriptionAction.SUBSCRIBE)

    def request_unsubscribe(self, symbol: str) -> None:
        self._request(symbol, StreamSubscriptionAction.UNSUBSCRIBE)

    def _request(
        self,
        symbol: str,
        action: StreamSubscriptionAction,
    ) -> None:
        normalized = self._normalize_symbol(symbol)
        contract = self._stock_contract(normalized)
        key = (action, normalized)
        with self._lock:
            if not self._running:
                raise RuntimeError("Momentum market-data stream is not running")
            if key in self._pending:
                return
            self._pending[key] = {
                StreamQuotePart.TICK,
                StreamQuotePart.BIDASK,
            }
            if action is StreamSubscriptionAction.SUBSCRIBE:
                self._subscribe_requested_parts[normalized] = set()

        method_name = (
            "subscribe"
            if action is StreamSubscriptionAction.SUBSCRIBE
            else "unsubscribe"
        )
        method: Callable[..., object] = getattr(self._api, method_name)
        completed: list[tuple[str, StreamQuotePart]] = []
        try:
            for quote_type, part in (
                ("tick", StreamQuotePart.TICK),
                ("bid_ask", StreamQuotePart.BIDASK),
            ):
                method(contract, quote_type=quote_type, version="v1")
                completed.append((quote_type, part))
                if action is StreamSubscriptionAction.SUBSCRIBE:
                    with self._lock:
                        self._subscribe_requested_parts[normalized].add(part)
        except Exception as error:
            with self._lock:
                self._pending.pop(key, None)
            if action is StreamSubscriptionAction.SUBSCRIBE and completed:
                with self._lock:
                    parts = {part for _, part in completed}
                    self._pending[
                        (StreamSubscriptionAction.SUBSCRIBE, normalized)
                    ] = set(parts)
                    self._subscribe_failures[normalized] = (
                        f"direct_subscribe_failure:{type(error).__name__}:{error}"
                    )
                return
            if action is StreamSubscriptionAction.SUBSCRIBE:
                with self._lock:
                    self._subscribe_requested_parts.pop(normalized, None)
            raise

    def stop(self) -> None:
        with self._lock:
            if not self._running:
                return
            self._stopping = True
            symbols = sorted(
                self._subscribed_symbols
                | {symbol for _, symbol in self._pending}
            )
        for symbol in symbols:
            try:
                contract = self._stock_contract(symbol)
            except Exception:
                continue
            for quote_type in ("tick", "bid_ask"):
                try:
                    self._api.unsubscribe(
                        contract,
                        quote_type=quote_type,
                        version="v1",
                    )
                except Exception:
                    pass
        for clear_name in (
            "clear_on_tick_stk_v1_callback",
            "clear_on_bidask_stk_v1_callback",
            "clear_event_callback",
        ):
            try:
                getattr(self._api, clear_name)()
            except Exception:
                pass
        with self._lock:
            self._running = False
            self._pending.clear()
            self._subscribe_requested_parts.clear()
            self._subscribe_failures.clear()
            self._subscribed_symbols.clear()
            self._event_handler = None
            self._lifecycle_handler = None

    def close(self) -> None:
        self.stop()
        if self._owns_session:
            self._api.logout()

    def _on_tick(self, *callback_args: object) -> None:
        self._record(callback_args, MarketStreamKind.TICK)

    def _on_bidask(self, *callback_args: object) -> None:
        self._record(callback_args, MarketStreamKind.BIDASK)

    def _record(
        self,
        callback_args: tuple[object, ...],
        stream_kind: MarketStreamKind,
    ) -> None:
        raw = callback_args[-1] if callback_args else None
        if raw is None or bool(getattr(raw, "intraday_odd", False)):
            return
        try:
            with self._ingress_lock:
                envelope = self._map_event(raw, stream_kind)
                with self._lock:
                    handler = self._event_handler
                if handler is not None:
                    handler(envelope)
        except Exception as error:
            with self._lock:
                self._callback_errors.append(
                    f"{stream_kind.value}:{type(error).__name__}:{error}"
                )

    def _map_event(
        self,
        raw: object,
        stream_kind: MarketStreamKind,
    ) -> EventEnvelope:
        symbol = self._normalize_symbol(getattr(raw, "code", ""))
        received_at, sequence = self._next_receipt()
        event_at = self._event_time(raw, received_at)
        event_id = hashlib.sha256(
            (
                f"{self._session_id}|{stream_kind.value}|{symbol}|"
                f"{sequence}"
            ).encode()
        ).hexdigest()
        common = {
            "event_id": event_id,
            "symbol": symbol,
            "session_date": event_at.date(),
            "event_time": event_at,
            "received_at": received_at,
            "ingress_sequence": sequence,
            "suspended": bool(
                getattr(raw, "suspend", getattr(raw, "suspended", False))
            ),
            "simulated_trade": bool(getattr(raw, "simtrade", False)),
            "intraday_odd": False,
        }
        if stream_kind is MarketStreamKind.TICK:
            price = self._required_positive_decimal(raw, "close")
            payload = TickEvent(
                source=MarketEventSource.TICK,
                price=price,
                tick_volume_lots=self._required_non_negative_integer(
                    raw,
                    "volume",
                ),
                total_volume_lots=self._required_non_negative_integer(
                    raw,
                    "total_volume",
                    "vol_sum",
                ),
                average_price=self._positive_decimal(
                    self._first_present(raw, "avg_price", "average_price")
                ),
                intraday_high=self._required_positive_decimal(raw, "high"),
                intraday_low=self._required_positive_decimal(raw, "low"),
                raw_tick_type=self._integer(getattr(raw, "tick_type", None)) or 0,
                aggressor_side=AggressorSide.UNKNOWN,
                buy_aggressor_total_lots=None,
                sell_aggressor_total_lots=None,
                **common,
            )
            source = MarketEventSource.TICK
        else:
            bid_prices, bid_volumes = self._book_side(raw, "bid")
            ask_prices, ask_volumes = self._book_side(raw, "ask")
            if not bid_prices and not ask_prices:
                raise ValueError("BidAsk event has no valid price levels")
            payload = BidAskEvent(
                source=MarketEventSource.BIDASK,
                bid_prices=bid_prices,
                bid_volume_lots=bid_volumes,
                ask_prices=ask_prices,
                ask_volume_lots=ask_volumes,
                **common,
            )
            source = MarketEventSource.BIDASK
        return EventEnvelope(
            event_id=event_id,
            schema_version=MARKET_EVENT_SCHEMA_VERSION,
            session_id=self._session_id,
            session_date=event_at.date(),
            source=source,
            source_mode=SOURCE_MODE,
            stream_kind=stream_kind,
            symbol=symbol,
            event_at=event_at,
            received_at=received_at,
            ingress_sequence=sequence,
            source_identity=f"shioaji:{SOURCE_MODE}:{sequence}",
            payload=payload,
        )

    def _on_lifecycle(
        self,
        resp_code: int,
        event_code: int,
        info: str,
        event: str,
    ) -> None:
        with self._lock:
            if self._stopping:
                return
        occurred_at = self._clock.now()
        reason = str(event or info or f"event_code:{event_code}")
        if event_code == 16:
            self._acknowledge_part(str(info), occurred_at)
            return
        if event_code == 4:
            self._fail_pending(str(info), occurred_at, reason)
            return
        lifecycle_type = {
            1: StreamLifecycleEventType.DISCONNECTED,
            2: StreamLifecycleEventType.DISCONNECTED,
            12: StreamLifecycleEventType.RECONNECTING,
            13: StreamLifecycleEventType.RECONNECTED,
        }.get(event_code)
        if lifecycle_type is None:
            return
        self._emit_lifecycle(
            StreamLifecycleEvent(
                event_type=lifecycle_type,
                occurred_at=occurred_at,
                reason=reason,
                raw_event_code=event_code,
                raw_info=str(info),
            )
        )

    def _acknowledge_part(self, info: str, occurred_at: datetime) -> None:
        symbol = self._symbol_from_info(info)
        part = self._part_from_info(info)
        if symbol is None or part is None:
            return
        completed_action = None
        rollback_reason = None
        with self._lock:
            for action in (
                StreamSubscriptionAction.SUBSCRIBE,
                StreamSubscriptionAction.UNSUBSCRIBE,
                StreamSubscriptionAction.ROLLBACK,
            ):
                key = (action, symbol)
                remaining = self._pending.get(key)
                if remaining is None or part not in remaining:
                    continue
                remaining.remove(part)
                if not remaining:
                    self._pending.pop(key, None)
                    completed_action = action
                    if action is StreamSubscriptionAction.SUBSCRIBE:
                        rollback_reason = self._subscribe_failures.get(symbol)
                        if rollback_reason is None:
                            self._subscribed_symbols.add(symbol)
                            self._subscribe_requested_parts.pop(symbol, None)
                    else:
                        self._subscribed_symbols.discard(symbol)
                break
        if completed_action is None:
            return
        if (
            completed_action is StreamSubscriptionAction.SUBSCRIBE
            and rollback_reason is not None
        ):
            self._begin_subscribe_rollback(
                symbol,
                occurred_at,
                rollback_reason,
            )
            return
        event_type = (
            StreamLifecycleEventType.SUBSCRIBE_ACKED
            if completed_action is StreamSubscriptionAction.SUBSCRIBE
            else StreamLifecycleEventType.UNSUBSCRIBE_ACKED
        )
        if completed_action is StreamSubscriptionAction.ROLLBACK:
            with self._lock:
                self._subscribe_requested_parts.pop(symbol, None)
                self._subscribe_failures.pop(symbol, None)
        self._emit_lifecycle(
            StreamLifecycleEvent(
                event_type=event_type,
                occurred_at=occurred_at,
                reason="paired_tick_bidask_ack",
                symbol=symbol,
                raw_event_code=16,
                raw_info=info,
            )
        )

    def _fail_pending(
        self,
        info: str,
        occurred_at: datetime,
        reason: str,
    ) -> None:
        symbol = self._symbol_from_info(info)
        if symbol is None:
            return
        failed_action = None
        failed_part = self._part_from_info(info)
        should_begin_rollback = False
        with self._lock:
            for action in (
                StreamSubscriptionAction.SUBSCRIBE,
                StreamSubscriptionAction.UNSUBSCRIBE,
                StreamSubscriptionAction.ROLLBACK,
            ):
                remaining = self._pending.get((action, symbol))
                if remaining is None:
                    continue
                if action is StreamSubscriptionAction.SUBSCRIBE:
                    if failed_part is None:
                        remaining.clear()
                    else:
                        remaining.discard(failed_part)
                        self._subscribe_requested_parts.setdefault(
                            symbol,
                            set(),
                        ).discard(failed_part)
                    self._subscribe_failures[symbol] = reason
                    if remaining:
                        return
                    self._pending.pop((action, symbol), None)
                    should_begin_rollback = bool(
                        self._subscribe_requested_parts.get(symbol)
                    )
                else:
                    self._pending.pop((action, symbol), None)
                    failed_action = action
                break
        if should_begin_rollback:
            self._begin_subscribe_rollback(symbol, occurred_at, reason)
            return
        if failed_action is None:
            with self._lock:
                no_requested_parts = not self._subscribe_requested_parts.pop(
                    symbol,
                    set(),
                )
                self._subscribe_failures.pop(symbol, None)
            if no_requested_parts:
                self._emit_subscribe_failed(symbol, occurred_at, reason, info)
            return
        event_type = (
            StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_FAILED
            if failed_action is StreamSubscriptionAction.ROLLBACK
            else StreamLifecycleEventType.UNSUBSCRIBE_FAILED
        )
        self._emit_lifecycle(
            StreamLifecycleEvent(
                event_type=event_type,
                occurred_at=occurred_at,
                reason=reason,
                symbol=symbol,
                raw_event_code=4,
                raw_info=info,
            )
        )

    def _begin_subscribe_rollback(
        self,
        symbol: str,
        occurred_at: datetime,
        reason: str,
    ) -> None:
        with self._lock:
            parts = set(self._subscribe_requested_parts.get(symbol, set()))
            self._pending[(StreamSubscriptionAction.ROLLBACK, symbol)] = parts
        self._emit_lifecycle(
            StreamLifecycleEvent(
                event_type=(
                    StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_STARTED
                ),
                occurred_at=occurred_at,
                reason=reason,
                symbol=symbol,
            )
        )
        try:
            contract = self._stock_contract(symbol)
            for part in sorted(parts, key=lambda value: value.value):
                quote_type = (
                    "tick" if part is StreamQuotePart.TICK else "bid_ask"
                )
                self._api.unsubscribe(
                    contract,
                    quote_type=quote_type,
                    version="v1",
                )
        except Exception as error:
            with self._lock:
                self._pending.pop(
                    (StreamSubscriptionAction.ROLLBACK, symbol),
                    None,
                )
            self._emit_lifecycle(
                StreamLifecycleEvent(
                    event_type=(
                        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_FAILED
                    ),
                    occurred_at=occurred_at,
                    reason=(
                        f"rollback_request_failed:{type(error).__name__}:{error}"
                    ),
                    symbol=symbol,
                )
            )

    def _emit_subscribe_failed(
        self,
        symbol: str,
        occurred_at: datetime,
        reason: str,
        info: str,
    ) -> None:
        self._emit_lifecycle(
            StreamLifecycleEvent(
                event_type=StreamLifecycleEventType.SUBSCRIBE_FAILED,
                occurred_at=occurred_at,
                reason=reason,
                symbol=symbol,
                raw_event_code=4,
                raw_info=info,
            )
        )

    def _emit_lifecycle(self, event: StreamLifecycleEvent) -> None:
        with self._lock:
            handler = self._lifecycle_handler
        if handler is not None:
            handler(event)

    def _next_receipt(self) -> tuple[datetime, int]:
        with self._lock:
            received_at = self._clock.now()
            self._sequence += 1
            return received_at, self._sequence

    def _stock_contract(self, symbol: str) -> object:
        contract = self._api.Contracts.Stocks[symbol]
        if contract is None:
            raise KeyError(f"Contract not found: {symbol}")
        return contract

    @staticmethod
    def _normalize_symbol(value: object) -> str:
        normalized = str(value).strip().upper()
        if not normalized:
            raise ValueError("stream symbol must not be empty")
        return normalized

    @staticmethod
    def _first_present(raw: object, *names: str) -> object | None:
        for name in names:
            value = getattr(raw, name, None)
            if value is not None:
                return value
        return None

    @classmethod
    def _required_positive_decimal(
        cls,
        raw: object,
        *names: str,
    ) -> Decimal:
        value = cls._positive_decimal(cls._first_present(raw, *names))
        if value is None:
            raise ValueError(f"positive field unavailable: {'/'.join(names)}")
        return value

    @staticmethod
    def _positive_decimal(value: object | None) -> Decimal | None:
        if value is None:
            return None
        try:
            result = Decimal(str(value))
        except (InvalidOperation, TypeError, ValueError):
            return None
        return result if result > 0 else None

    @classmethod
    def _required_non_negative_integer(
        cls,
        raw: object,
        *names: str,
    ) -> int:
        value = cls._integer(cls._first_present(raw, *names))
        if value is None or value < 0:
            raise ValueError(
                f"non-negative field unavailable: {'/'.join(names)}"
            )
        return value

    @staticmethod
    def _integer(value: object | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    @classmethod
    def _positive_integer(cls, value: object | None) -> int | None:
        result = cls._integer(value)
        return result if result is not None and result > 0 else None

    @classmethod
    def _book_side(
        cls,
        raw: object,
        side: str,
    ) -> tuple[tuple[Decimal, ...], tuple[int, ...]]:
        raw_prices = getattr(raw, f"{side}_price", None)
        raw_volumes = getattr(raw, f"{side}_volume", None)
        prices = list(raw_prices) if raw_prices is not None else []
        volumes = list(raw_volumes) if raw_volumes is not None else []
        normalized: list[tuple[Decimal, int]] = []
        for raw_price, raw_volume in zip(prices[:5], volumes[:5]):
            price = cls._positive_decimal(raw_price)
            volume = cls._integer(raw_volume)
            if price is None or volume is None or volume < 0:
                continue
            normalized.append((price, volume))
        return (
            tuple(price for price, _ in normalized),
            tuple(volume for _, volume in normalized),
        )

    @staticmethod
    def _event_time(raw: object, received_at: datetime) -> datetime:
        value = getattr(raw, "datetime", None)
        if isinstance(value, datetime):
            return (
                value.replace(tzinfo=TAIPEI)
                if value.tzinfo is None
                else value.astimezone(TAIPEI)
            )
        if isinstance(value, (list, tuple)) and len(value) >= 6:
            parts = [int(part) for part in value[:7]]
            return datetime(*parts, tzinfo=TAIPEI)
        event_date = getattr(raw, "date", None)
        event_time = getattr(raw, "time", None)
        if isinstance(event_date, date) and isinstance(event_time, time):
            combined = datetime.combine(event_date, event_time)
            return (
                combined.replace(tzinfo=TAIPEI)
                if combined.tzinfo is None
                else combined.astimezone(TAIPEI)
            )
        return received_at

    @staticmethod
    def _parse_date(value: object | None) -> date | None:
        if isinstance(value, datetime):
            return value.date()
        if isinstance(value, date):
            return value
        if value is None:
            return None
        text = str(value).strip().replace("/", "-")
        try:
            return date.fromisoformat(text)
        except ValueError:
            return None

    @staticmethod
    def _symbol_from_info(info: str) -> str | None:
        parts = [part for part in info.split("/") if part and part != "*"]
        if not parts:
            return None
        symbol = parts[-1].strip().upper()
        return symbol or None

    @staticmethod
    def _part_from_info(info: str) -> StreamQuotePart | None:
        prefix = info.split("/", 1)[0].strip().upper()
        if prefix == "TIC":
            return StreamQuotePart.TICK
        if prefix in {"QUO", "QUT"}:
            return StreamQuotePart.BIDASK
        return None
