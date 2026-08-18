"""Bounded, data-only Shioaji capture for Quote parity qualification.

The capture subscribes one symbol to Quote, Tick, and BidAsk simultaneously,
normalizes market-data fields, writes a credential-free JSON artifact, and
always unsubscribes/logs out.  It never imports or calls any order API.
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field, replace
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation
from enum import Enum
from pathlib import Path
from threading import Event, Lock
from typing import Any
from zoneinfo import ZoneInfo

from config.momentum import QuoteSubscriptionMode
from market_data.quote_qualification import (
    ObservationKind,
    QuoteParityReport,
    StreamCapture,
    StreamObservation,
    evaluate_quote_parity,
)


TAIPEI = ZoneInfo("Asia/Taipei")
CAPTURE_SCHEMA_VERSION = "quote_parity_capture_v0"


def _first_present(event: object, *field_names: str) -> object | None:
    for field_name in field_names:
        value = getattr(event, field_name, None)
        if value is not None:
            return value
    return None


def _decimal(value: object | None) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _integer(value: object | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _event_time(event: object, received_at: datetime) -> datetime:
    value = getattr(event, "datetime", None)
    if isinstance(value, datetime):
        return value.replace(tzinfo=TAIPEI) if value.tzinfo is None else value.astimezone(TAIPEI)
    if isinstance(value, (list, tuple)) and len(value) >= 6:
        parts = [int(part) for part in value[:7]]
        return datetime(*parts, tzinfo=TAIPEI)

    event_date = getattr(event, "date", None)
    event_time = getattr(event, "time", None)
    if isinstance(event_date, date) and isinstance(event_time, time):
        combined = datetime.combine(event_date, event_time)
        return combined.replace(tzinfo=TAIPEI) if combined.tzinfo is None else combined.astimezone(TAIPEI)
    return received_at


def _book_side(event: object, side: str) -> tuple[tuple[Decimal, ...], tuple[int, ...]]:
    raw_prices = getattr(event, f"{side}_price", None)
    raw_volumes = getattr(event, f"{side}_volume", None)
    prices = list(raw_prices) if raw_prices is not None else []
    volumes = list(raw_volumes) if raw_volumes is not None else []
    normalized: list[tuple[Decimal, int]] = []
    for raw_price, raw_volume in zip(prices[:5], volumes[:5]):
        price = _decimal(raw_price)
        volume = _integer(raw_volume)
        if price is None or price <= 0 or volume is None or volume < 0:
            continue
        normalized.append((price, volume))
    return (
        tuple(price for price, _ in normalized),
        tuple(volume for _, volume in normalized),
    )


def _trade_observation(
    event: object,
    received_at: datetime,
    source_mode: QuoteSubscriptionMode,
) -> StreamObservation | None:
    symbol = str(getattr(event, "code", "")).strip().upper()
    last_price = _decimal(getattr(event, "close", None))
    if not symbol or last_price is None or last_price <= 0:
        return None
    return StreamObservation(
        source_mode=source_mode,
        symbol=symbol,
        kind=ObservationKind.TRADE,
        event_time=_event_time(event, received_at),
        received_at=received_at,
        total_volume_lots=_integer(
            _first_present(event, "total_volume", "vol_sum")
        ),
        total_amount=_decimal(
            _first_present(event, "total_amount", "amount_sum")
        ),
        last_price=last_price,
        average_price=_decimal(
            _first_present(event, "avg_price", "average_price")
        ),
        raw_tick_type=_integer(getattr(event, "tick_type", None)),
        # Keep SDK side names neutral until labeled capture freezes mapping.
        bid_side_total_lots=_integer(
            _first_present(event, "bid_side_total_vol", "trade_bid_vol_sum")
        ),
        ask_side_total_lots=_integer(
            _first_present(event, "ask_side_total_vol", "trade_ask_vol_sum")
        ),
    )


def _book_observation(
    event: object,
    received_at: datetime,
    source_mode: QuoteSubscriptionMode,
) -> StreamObservation | None:
    symbol = str(getattr(event, "code", "")).strip().upper()
    if not symbol:
        return None
    bid_prices, bid_volumes = _book_side(event, "bid")
    ask_prices, ask_volumes = _book_side(event, "ask")
    if not bid_prices and not ask_prices:
        return None
    return StreamObservation(
        source_mode=source_mode,
        symbol=symbol,
        kind=ObservationKind.BOOK,
        event_time=_event_time(event, received_at),
        received_at=received_at,
        bid_prices=bid_prices,
        bid_volume_lots=bid_volumes,
        ask_prices=ask_prices,
        ask_volume_lots=ask_volumes,
    )


def tick_event_to_observations(
    event: object,
    received_at: datetime,
) -> tuple[StreamObservation, ...]:
    if bool(getattr(event, "intraday_odd", False)):
        return ()
    trade = _trade_observation(
        event,
        received_at,
        QuoteSubscriptionMode.TICK_BIDASK,
    )
    return () if trade is None else (trade,)


def bidask_event_to_observations(
    event: object,
    received_at: datetime,
) -> tuple[StreamObservation, ...]:
    if bool(getattr(event, "intraday_odd", False)):
        return ()
    book = _book_observation(
        event,
        received_at,
        QuoteSubscriptionMode.TICK_BIDASK,
    )
    return () if book is None else (book,)


@dataclass
class QuoteProjectionTracker:
    """Project combined Quote callbacks into de-duplicated trade/book changes."""

    _fingerprints: dict[ObservationKind, tuple[object, ...]] = field(
        default_factory=dict
    )

    def project(
        self,
        event: object,
        received_at: datetime,
    ) -> tuple[StreamObservation, ...]:
        candidates = tuple(
            observation
            for observation in (
                _trade_observation(
                    event,
                    received_at,
                    QuoteSubscriptionMode.QUOTE,
                ),
                _book_observation(
                    event,
                    received_at,
                    QuoteSubscriptionMode.QUOTE,
                ),
            )
            if observation is not None
        )
        projected: list[StreamObservation] = []
        for observation in candidates:
            fingerprint = self._fingerprint(observation)
            previous = self._fingerprints.get(observation.kind)
            if previous == fingerprint:
                continue
            self._fingerprints[observation.kind] = fingerprint
            projected.append(
                replace(observation, is_baseline=previous is None)
            )
        return tuple(projected)

    @staticmethod
    def _fingerprint(observation: StreamObservation) -> tuple[object, ...]:
        if observation.kind is ObservationKind.TRADE:
            return (
                observation.total_volume_lots,
                observation.total_amount,
                observation.last_price,
                observation.average_price,
                observation.raw_tick_type,
                observation.bid_side_total_lots,
                observation.ask_side_total_lots,
            )
        return (
            observation.bid_prices,
            observation.bid_volume_lots,
            observation.ask_prices,
            observation.ask_volume_lots,
        )


@dataclass
class LiveQuoteCaptureBuffer:
    symbol: str
    quote_tracker: QuoteProjectionTracker = field(default_factory=QuoteProjectionTracker)
    quote_observations: list[StreamObservation] = field(default_factory=list)
    tick_bidask_observations: list[StreamObservation] = field(default_factory=list)
    callback_counts: dict[str, int] = field(
        default_factory=lambda: {"quote": 0, "tick": 0, "bidask": 0}
    )
    callback_errors: list[str] = field(default_factory=list)
    lock: Lock = field(default_factory=Lock)

    def on_quote(self, *callback_args: object) -> None:
        self._record("quote", callback_args, self.quote_tracker.project)

    def on_tick(self, *callback_args: object) -> None:
        self._record("tick", callback_args, tick_event_to_observations)

    def on_bidask(self, *callback_args: object) -> None:
        self._record("bidask", callback_args, bidask_event_to_observations)

    def _record(self, callback_name: str, callback_args: tuple[object, ...], mapper) -> None:
        event = callback_args[-1] if callback_args else None
        if event is None:
            return
        received_at = datetime.now(TAIPEI)
        try:
            observations = mapper(event, received_at)
            with self.lock:
                self.callback_counts[callback_name] += 1
                target = (
                    self.quote_observations
                    if callback_name == "quote"
                    else self.tick_bidask_observations
                )
                target.extend(
                    observation
                    for observation in observations
                    if observation.symbol == self.symbol
                )
        except Exception as error:  # callback must not terminate the feed
            with self.lock:
                self.callback_errors.append(
                    f"{callback_name}:{type(error).__name__}:{error}"
                )

    def captures(self) -> tuple[StreamCapture, StreamCapture]:
        with self.lock:
            quote = tuple(self.quote_observations)
            paired = tuple(self.tick_bidask_observations)
        return (
            StreamCapture(
                source_mode=QuoteSubscriptionMode.QUOTE,
                symbol=self.symbol,
                observations=quote,
            ),
            StreamCapture(
                source_mode=QuoteSubscriptionMode.TICK_BIDASK,
                symbol=self.symbol,
                observations=paired,
            ),
        )


def run_live_quote_capture(
    symbol: str,
    duration_seconds: int,
    output_directory: Path,
) -> tuple[Path, QuoteParityReport]:
    """Run one bounded market-data-only A/B capture and persist its evidence."""
    if duration_seconds <= 0 or duration_seconds > 60:
        raise ValueError("duration_seconds must be between 1 and 60")
    symbol = symbol.strip().upper()
    if not symbol:
        raise ValueError("symbol must not be empty")

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
    subscribed: list[object] = []
    buffer = LiveQuoteCaptureBuffer(symbol=symbol)
    started_at = datetime.now(TAIPEI)
    contract = None
    try:
        api.login(
            api_key=api_key,
            secret_key=secret,
            subscribe_trade=False,
        )
        # SDK 1.7.2 warns that this collection is deprecated, but its v2
        # ``api.contracts`` object is not a drop-in replacement.  Keep the
        # proven lookup until a separate v2 contract migration is qualified.
        contract = api.Contracts.Stocks[symbol]
        if contract is None:
            raise KeyError(f"Contract not found: {symbol}")

        api.set_on_quote_stk_v1_callback(buffer.on_quote)
        api.set_on_tick_stk_v1_callback(buffer.on_tick)
        api.set_on_bidask_stk_v1_callback(buffer.on_bidask)

        for quote_type in (
            sj.QuoteType.Quote,
            sj.QuoteType.Tick,
            sj.QuoteType.BidAsk,
        ):
            api.subscribe(
                contract,
                quote_type=quote_type,
                version=sj.QuoteVersion.v1,
            )
            subscribed.append(quote_type)
        Event().wait(duration_seconds)
    finally:
        if contract is not None:
            for quote_type in reversed(subscribed):
                try:
                    api.unsubscribe(
                        contract,
                        quote_type=quote_type,
                        version=sj.QuoteVersion.v1,
                    )
                except Exception:
                    pass
        for clear_name in (
            "clear_on_quote_stk_v1_callback",
            "clear_on_tick_stk_v1_callback",
            "clear_on_bidask_stk_v1_callback",
        ):
            try:
                getattr(api, clear_name)()
            except Exception:
                pass
        try:
            api.logout()
        except Exception:
            pass

    ended_at = datetime.now(TAIPEI)
    quote_capture, paired_capture = buffer.captures()
    report = evaluate_quote_parity(
        quote_capture,
        paired_capture,
        criteria=None,
    )
    payload = {
        "schema_version": CAPTURE_SCHEMA_VERSION,
        "sdk_version": getattr(sj, "__version__", "unknown"),
        "symbol": symbol,
        "simulation": simulation,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": duration_seconds,
        "callback_counts": dict(buffer.callback_counts),
        "callback_errors": tuple(buffer.callback_errors),
        "quote_capture": quote_capture,
        "tick_bidask_capture": paired_capture,
        "preliminary_report": report,
        "qualification_note": (
            "INCOMPLETE until reviewed criteria, reconnect test, and derived "
            "feature/signal/stage/alert digests are supplied"
        ),
    }
    output_directory.mkdir(parents=True, exist_ok=True)
    filename = f"{symbol}_{started_at.strftime('%Y%m%dT%H%M%S%z')}.json"
    output_path = output_directory / filename
    with output_path.open("x", encoding="utf-8") as file:
        json.dump(payload, file, default=_json_default, ensure_ascii=False, indent=2)
        file.write("\n")
    return output_path, report


def _json_default(value: Any) -> object:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if hasattr(value, "__dataclass_fields__"):
        return asdict(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")
