"""Deterministic Quote versus Tick+BidAsk qualification evidence.

This module does not subscribe to Shioaji and does not choose production
thresholds.  It evaluates two labeled captures against explicitly reviewed
criteria.  Missing criteria, source data, derived digests, or reconnect
evidence produces ``INCOMPLETE`` rather than an optimistic pass.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from math import ceil

from config.momentum import QuoteSubscriptionMode


class ObservationKind(StrEnum):
    TRADE = "TRADE"
    BOOK = "BOOK"


class QuoteParityStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    INCOMPLETE = "INCOMPLETE"


def _require_aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


@dataclass(frozen=True)
class StreamObservation:
    source_mode: QuoteSubscriptionMode
    symbol: str
    kind: ObservationKind
    event_time: datetime
    received_at: datetime
    is_baseline: bool = False
    total_volume_lots: int | None = None
    total_amount: Decimal | None = None
    last_price: Decimal | None = None
    average_price: Decimal | None = None
    raw_tick_type: int | None = None
    bid_side_total_lots: int | None = None
    ask_side_total_lots: int | None = None
    bid_prices: tuple[Decimal, ...] = ()
    bid_volume_lots: tuple[int, ...] = ()
    ask_prices: tuple[Decimal, ...] = ()
    ask_volume_lots: tuple[int, ...] = ()

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        _require_aware(self.event_time, "event_time")
        _require_aware(self.received_at, "received_at")
        if self.total_volume_lots is not None and self.total_volume_lots < 0:
            raise ValueError("total_volume_lots must be non-negative")
        if self.total_amount is not None and self.total_amount < 0:
            raise ValueError("total_amount must be non-negative")
        if self.average_price is not None and self.average_price <= 0:
            raise ValueError("average_price must be positive")
        for field_name in ("bid_side_total_lots", "ask_side_total_lots"):
            value = getattr(self, field_name)
            if value is not None and value < 0:
                raise ValueError(f"{field_name} must be non-negative")
        if len(self.bid_prices) != len(self.bid_volume_lots):
            raise ValueError("bid price/volume lengths must match")
        if len(self.ask_prices) != len(self.ask_volume_lots):
            raise ValueError("ask price/volume lengths must match")
        if len(self.bid_prices) > 5 or len(self.ask_prices) > 5:
            raise ValueError("book observations support at most five levels")
        if any(volume < 0 for volume in (*self.bid_volume_lots, *self.ask_volume_lots)):
            raise ValueError("book volumes must be non-negative")

    @property
    def latency_ms(self) -> float:
        return (self.received_at - self.event_time).total_seconds() * 1000.0


@dataclass(frozen=True)
class StreamCapture:
    source_mode: QuoteSubscriptionMode
    symbol: str
    observations: tuple[StreamObservation, ...]
    reconnect_attempted: bool = False
    continuity_verified_after_reconnect: bool | None = None

    def __post_init__(self) -> None:
        if not self.symbol.strip():
            raise ValueError("symbol must not be empty")
        for observation in self.observations:
            if observation.source_mode is not self.source_mode:
                raise ValueError("observation source does not match capture source")
            if observation.symbol != self.symbol:
                raise ValueError("observation symbol does not match capture symbol")
        if not self.reconnect_attempted and self.continuity_verified_after_reconnect is not None:
            raise ValueError("reconnect continuity cannot be set without a reconnect attempt")


@dataclass(frozen=True)
class DerivedOutputDigest:
    source_mode: QuoteSubscriptionMode
    feature_digest: str
    signal_digest: str
    stage_digest: str
    alert_digest: str

    def __post_init__(self) -> None:
        for field_name in (
            "feature_digest",
            "signal_digest",
            "stage_digest",
            "alert_digest",
        ):
            if not getattr(self, field_name).strip():
                raise ValueError(f"{field_name} must not be empty")


@dataclass(frozen=True)
class QuoteParityCriteria:
    version: str
    max_terminal_volume_delta_lots: int
    max_terminal_amount_delta: Decimal
    max_terminal_average_price_delta: Decimal
    max_terminal_bid_side_volume_delta_lots: int
    max_terminal_ask_side_volume_delta_lots: int
    max_latest_trade_time_delta_ms: float
    max_latest_book_time_delta_ms: float
    min_trade_event_count_ratio: Decimal
    min_book_event_count_ratio: Decimal
    max_p50_latency_delta_ms: float
    max_p95_latency_delta_ms: float
    max_p99_latency_delta_ms: float
    max_gap_delta_ms: float
    require_latest_book_equal: bool
    require_terminal_tick_type_equal: bool
    require_derived_digest_equal: bool
    require_reconnect_test: bool
    require_non_negative_source_latency: bool

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("version must not be empty")
        for field_name in (
            "max_terminal_volume_delta_lots",
            "max_terminal_amount_delta",
            "max_terminal_average_price_delta",
            "max_terminal_bid_side_volume_delta_lots",
            "max_terminal_ask_side_volume_delta_lots",
            "max_latest_trade_time_delta_ms",
            "max_latest_book_time_delta_ms",
            "max_p50_latency_delta_ms",
            "max_p95_latency_delta_ms",
            "max_p99_latency_delta_ms",
            "max_gap_delta_ms",
        ):
            if getattr(self, field_name) < 0:
                raise ValueError(f"{field_name} must be non-negative")
        for field_name in (
            "min_trade_event_count_ratio",
            "min_book_event_count_ratio",
        ):
            value = getattr(self, field_name)
            if not Decimal("0") <= value <= Decimal("1"):
                raise ValueError(f"{field_name} must be between 0 and 1")


@dataclass(frozen=True)
class QuoteParityMetrics:
    quote_trade_count: int
    tick_bidask_trade_count: int
    quote_book_count: int
    tick_bidask_book_count: int
    trade_event_count_ratio: Decimal | None
    book_event_count_ratio: Decimal | None
    terminal_volume_delta_lots: int | None
    terminal_amount_delta: Decimal | None
    terminal_average_price_delta: Decimal | None
    terminal_bid_side_volume_delta_lots: int | None
    terminal_ask_side_volume_delta_lots: int | None
    terminal_tick_type_equal: bool | None
    latest_trade_time_delta_ms: float | None
    latest_book_time_delta_ms: float | None
    quote_p50_latency_ms: float | None
    tick_bidask_p50_latency_ms: float | None
    p50_latency_delta_ms: float | None
    quote_p95_latency_ms: float | None
    tick_bidask_p95_latency_ms: float | None
    p95_latency_delta_ms: float | None
    quote_p99_latency_ms: float | None
    tick_bidask_p99_latency_ms: float | None
    p99_latency_delta_ms: float | None
    quote_max_gap_ms: float | None
    tick_bidask_max_gap_ms: float | None
    max_gap_delta_ms: float | None
    latest_book_equal: bool | None
    derived_digest_equal: bool | None
    quote_reconnect_continuity: bool | None
    tick_bidask_reconnect_continuity: bool | None
    quote_negative_latency_count: int
    tick_bidask_negative_latency_count: int


@dataclass(frozen=True)
class QuoteParityReport:
    status: QuoteParityStatus
    symbol: str
    criteria_version: str | None
    metrics: QuoteParityMetrics
    incomplete_reasons: tuple[str, ...]
    failed_checks: tuple[str, ...]

    @property
    def qualified_for_quote(self) -> bool:
        return self.status is QuoteParityStatus.PASS


def evaluate_quote_parity(
    quote_capture: StreamCapture,
    tick_bidask_capture: StreamCapture,
    *,
    criteria: QuoteParityCriteria | None,
    quote_digest: DerivedOutputDigest | None = None,
    tick_bidask_digest: DerivedOutputDigest | None = None,
) -> QuoteParityReport:
    """Compare two labeled captures and fail closed on missing evidence."""
    _validate_capture_pair(quote_capture, tick_bidask_capture)
    quote_trades_all = _observations(quote_capture, ObservationKind.TRADE)
    paired_trades_all = _observations(tick_bidask_capture, ObservationKind.TRADE)
    quote_books_all = _observations(quote_capture, ObservationKind.BOOK)
    paired_books_all = _observations(tick_bidask_capture, ObservationKind.BOOK)
    quote_trades = _without_baseline(quote_trades_all)
    paired_trades = _without_baseline(paired_trades_all)
    quote_books = _without_baseline(quote_books_all)
    paired_books = _without_baseline(paired_books_all)

    quote_terminal_volume = _latest_value(quote_trades_all, "total_volume_lots")
    paired_terminal_volume = _latest_value(paired_trades_all, "total_volume_lots")
    quote_terminal_amount = _latest_value(quote_trades_all, "total_amount")
    paired_terminal_amount = _latest_value(paired_trades_all, "total_amount")
    quote_terminal_average = _latest_value(quote_trades_all, "average_price")
    paired_terminal_average = _latest_value(paired_trades_all, "average_price")
    quote_terminal_bid_side = _latest_value(quote_trades_all, "bid_side_total_lots")
    paired_terminal_bid_side = _latest_value(paired_trades_all, "bid_side_total_lots")
    quote_terminal_ask_side = _latest_value(quote_trades_all, "ask_side_total_lots")
    paired_terminal_ask_side = _latest_value(paired_trades_all, "ask_side_total_lots")
    quote_terminal_tick_type = _latest_value(quote_trades_all, "raw_tick_type")
    paired_terminal_tick_type = _latest_value(paired_trades_all, "raw_tick_type")

    quote_trade_time = _latest_time(quote_trades_all)
    paired_trade_time = _latest_time(paired_trades_all)
    quote_book_time = _latest_time(quote_books_all)
    paired_book_time = _latest_time(paired_books_all)

    quote_latencies = [
        observation.latency_ms for observation in quote_capture.observations
    ]
    paired_latencies = [
        observation.latency_ms for observation in tick_bidask_capture.observations
    ]
    quote_p50_latency = _percentile(quote_latencies, 0.50)
    paired_p50_latency = _percentile(paired_latencies, 0.50)
    quote_p95_latency = _percentile(quote_latencies, 0.95)
    paired_p95_latency = _percentile(paired_latencies, 0.95)
    quote_p99_latency = _percentile(quote_latencies, 0.99)
    paired_p99_latency = _percentile(paired_latencies, 0.99)
    quote_max_gap = _max_gap_ms(quote_capture.observations)
    paired_max_gap = _max_gap_ms(tick_bidask_capture.observations)
    latest_book_equal = _latest_book_equal(quote_books_all, paired_books_all)
    digest_equal = _digest_equal(quote_digest, tick_bidask_digest)

    metrics = QuoteParityMetrics(
        quote_trade_count=len(quote_trades),
        tick_bidask_trade_count=len(paired_trades),
        quote_book_count=len(quote_books),
        tick_bidask_book_count=len(paired_books),
        trade_event_count_ratio=_count_ratio(len(quote_trades), len(paired_trades)),
        book_event_count_ratio=_count_ratio(len(quote_books), len(paired_books)),
        terminal_volume_delta_lots=_absolute_delta(
            quote_terminal_volume,
            paired_terminal_volume,
        ),
        terminal_amount_delta=_absolute_delta(
            quote_terminal_amount,
            paired_terminal_amount,
        ),
        terminal_average_price_delta=_absolute_delta(
            quote_terminal_average,
            paired_terminal_average,
        ),
        terminal_bid_side_volume_delta_lots=_absolute_delta(
            quote_terminal_bid_side,
            paired_terminal_bid_side,
        ),
        terminal_ask_side_volume_delta_lots=_absolute_delta(
            quote_terminal_ask_side,
            paired_terminal_ask_side,
        ),
        terminal_tick_type_equal=_optional_equal(
            quote_terminal_tick_type,
            paired_terminal_tick_type,
        ),
        latest_trade_time_delta_ms=_time_delta_ms(
            quote_trade_time,
            paired_trade_time,
        ),
        latest_book_time_delta_ms=_time_delta_ms(
            quote_book_time,
            paired_book_time,
        ),
        quote_p50_latency_ms=quote_p50_latency,
        tick_bidask_p50_latency_ms=paired_p50_latency,
        p50_latency_delta_ms=_absolute_delta(quote_p50_latency, paired_p50_latency),
        quote_p95_latency_ms=quote_p95_latency,
        tick_bidask_p95_latency_ms=paired_p95_latency,
        p95_latency_delta_ms=_absolute_delta(quote_p95_latency, paired_p95_latency),
        quote_p99_latency_ms=quote_p99_latency,
        tick_bidask_p99_latency_ms=paired_p99_latency,
        p99_latency_delta_ms=_absolute_delta(quote_p99_latency, paired_p99_latency),
        quote_max_gap_ms=quote_max_gap,
        tick_bidask_max_gap_ms=paired_max_gap,
        max_gap_delta_ms=_absolute_delta(quote_max_gap, paired_max_gap),
        latest_book_equal=latest_book_equal,
        derived_digest_equal=digest_equal,
        quote_reconnect_continuity=(
            quote_capture.continuity_verified_after_reconnect
            if quote_capture.reconnect_attempted
            else None
        ),
        tick_bidask_reconnect_continuity=(
            tick_bidask_capture.continuity_verified_after_reconnect
            if tick_bidask_capture.reconnect_attempted
            else None
        ),
        quote_negative_latency_count=sum(
            latency < 0 for latency in quote_latencies
        ),
        tick_bidask_negative_latency_count=sum(
            latency < 0 for latency in paired_latencies
        ),
    )

    incomplete = _incomplete_reasons(
        criteria,
        metrics,
        quote_capture,
        tick_bidask_capture,
        quote_digest,
        tick_bidask_digest,
    )
    failed = () if criteria is None else _failed_checks(criteria, metrics)
    status = (
        QuoteParityStatus.INCOMPLETE
        if incomplete
        else QuoteParityStatus.FAIL
        if failed
        else QuoteParityStatus.PASS
    )
    return QuoteParityReport(
        status=status,
        symbol=quote_capture.symbol,
        criteria_version=None if criteria is None else criteria.version,
        metrics=metrics,
        incomplete_reasons=tuple(incomplete),
        failed_checks=tuple(failed),
    )


def _validate_capture_pair(
    quote_capture: StreamCapture,
    tick_bidask_capture: StreamCapture,
) -> None:
    if quote_capture.source_mode is not QuoteSubscriptionMode.QUOTE:
        raise ValueError("quote_capture must use QUOTE mode")
    if tick_bidask_capture.source_mode is not QuoteSubscriptionMode.TICK_BIDASK:
        raise ValueError("tick_bidask_capture must use TICK_BIDASK mode")
    if quote_capture.symbol != tick_bidask_capture.symbol:
        raise ValueError("capture symbols must match")


def _observations(
    capture: StreamCapture,
    kind: ObservationKind,
) -> tuple[StreamObservation, ...]:
    return tuple(
        sorted(
            (observation for observation in capture.observations if observation.kind is kind),
            key=lambda observation: (observation.event_time, observation.received_at),
        )
    )


def _latest_value(
    observations: tuple[StreamObservation, ...],
    field_name: str,
) -> object | None:
    for observation in reversed(observations):
        value = getattr(observation, field_name)
        if value is not None:
            return value
    return None


def _without_baseline(
    observations: tuple[StreamObservation, ...],
) -> tuple[StreamObservation, ...]:
    return tuple(observation for observation in observations if not observation.is_baseline)


def _latest_time(observations: tuple[StreamObservation, ...]) -> datetime | None:
    return None if not observations else observations[-1].event_time


def _count_ratio(left: int, right: int) -> Decimal | None:
    if left == 0 or right == 0:
        return None
    return Decimal(min(left, right)) / Decimal(max(left, right))


def _absolute_delta(left: object | None, right: object | None):
    if left is None or right is None:
        return None
    return abs(left - right)  # type: ignore[operator]


def _optional_equal(left: object | None, right: object | None) -> bool | None:
    if left is None or right is None:
        return None
    return left == right


def _time_delta_ms(left: datetime | None, right: datetime | None) -> float | None:
    if left is None or right is None:
        return None
    return abs((left - right).total_seconds() * 1000.0)


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, ceil(percentile * len(ordered)) - 1)
    return ordered[index]


def _max_gap_ms(observations: tuple[StreamObservation, ...]) -> float | None:
    if not observations:
        return None
    ordered_times = sorted(observation.event_time for observation in observations)
    if len(ordered_times) == 1:
        return 0.0
    return max(
        (right - left).total_seconds() * 1000.0
        for left, right in zip(ordered_times, ordered_times[1:])
    )


def _latest_book_equal(
    quote_books: tuple[StreamObservation, ...],
    paired_books: tuple[StreamObservation, ...],
) -> bool | None:
    if not quote_books or not paired_books:
        return None
    quote = quote_books[-1]
    paired = paired_books[-1]
    return (
        quote.bid_prices == paired.bid_prices
        and quote.bid_volume_lots == paired.bid_volume_lots
        and quote.ask_prices == paired.ask_prices
        and quote.ask_volume_lots == paired.ask_volume_lots
    )


def _digest_equal(
    quote_digest: DerivedOutputDigest | None,
    tick_bidask_digest: DerivedOutputDigest | None,
) -> bool | None:
    if quote_digest is None or tick_bidask_digest is None:
        return None
    if quote_digest.source_mode is not QuoteSubscriptionMode.QUOTE:
        raise ValueError("quote_digest must use QUOTE mode")
    if tick_bidask_digest.source_mode is not QuoteSubscriptionMode.TICK_BIDASK:
        raise ValueError("tick_bidask_digest must use TICK_BIDASK mode")
    return (
        quote_digest.feature_digest == tick_bidask_digest.feature_digest
        and quote_digest.signal_digest == tick_bidask_digest.signal_digest
        and quote_digest.stage_digest == tick_bidask_digest.stage_digest
        and quote_digest.alert_digest == tick_bidask_digest.alert_digest
    )


def _incomplete_reasons(
    criteria: QuoteParityCriteria | None,
    metrics: QuoteParityMetrics,
    quote_capture: StreamCapture,
    paired_capture: StreamCapture,
    quote_digest: DerivedOutputDigest | None,
    paired_digest: DerivedOutputDigest | None,
) -> list[str]:
    reasons: list[str] = []
    if criteria is None:
        reasons.append("criteria_not_frozen")
    for field_name in (
        "trade_event_count_ratio",
        "book_event_count_ratio",
        "terminal_volume_delta_lots",
        "terminal_amount_delta",
        "terminal_average_price_delta",
        "terminal_bid_side_volume_delta_lots",
        "terminal_ask_side_volume_delta_lots",
        "terminal_tick_type_equal",
        "latest_trade_time_delta_ms",
        "latest_book_time_delta_ms",
        "p50_latency_delta_ms",
        "p95_latency_delta_ms",
        "p99_latency_delta_ms",
        "max_gap_delta_ms",
        "latest_book_equal",
    ):
        if getattr(metrics, field_name) is None:
            reasons.append(f"missing_{field_name}")
    if criteria is not None and criteria.require_derived_digest_equal:
        if quote_digest is None or paired_digest is None:
            reasons.append("missing_derived_digest")
    if criteria is not None and criteria.require_reconnect_test:
        for capture in (quote_capture, paired_capture):
            if not capture.reconnect_attempted:
                reasons.append(f"reconnect_not_tested_{capture.source_mode.value.lower()}")
            elif capture.continuity_verified_after_reconnect is None:
                reasons.append(
                    f"reconnect_continuity_missing_{capture.source_mode.value.lower()}"
                )
    return reasons


def _failed_checks(
    criteria: QuoteParityCriteria,
    metrics: QuoteParityMetrics,
) -> list[str]:
    failed: list[str] = []
    checks = (
        (
            "terminal_volume_delta",
            metrics.terminal_volume_delta_lots,
            criteria.max_terminal_volume_delta_lots,
            "max",
        ),
        (
            "terminal_amount_delta",
            metrics.terminal_amount_delta,
            criteria.max_terminal_amount_delta,
            "max",
        ),
        (
            "terminal_average_price_delta",
            metrics.terminal_average_price_delta,
            criteria.max_terminal_average_price_delta,
            "max",
        ),
        (
            "terminal_bid_side_volume_delta",
            metrics.terminal_bid_side_volume_delta_lots,
            criteria.max_terminal_bid_side_volume_delta_lots,
            "max",
        ),
        (
            "terminal_ask_side_volume_delta",
            metrics.terminal_ask_side_volume_delta_lots,
            criteria.max_terminal_ask_side_volume_delta_lots,
            "max",
        ),
        (
            "latest_trade_time_delta",
            metrics.latest_trade_time_delta_ms,
            criteria.max_latest_trade_time_delta_ms,
            "max",
        ),
        (
            "latest_book_time_delta",
            metrics.latest_book_time_delta_ms,
            criteria.max_latest_book_time_delta_ms,
            "max",
        ),
        (
            "trade_event_count_ratio",
            metrics.trade_event_count_ratio,
            criteria.min_trade_event_count_ratio,
            "min",
        ),
        (
            "book_event_count_ratio",
            metrics.book_event_count_ratio,
            criteria.min_book_event_count_ratio,
            "min",
        ),
        (
            "p50_latency_delta",
            metrics.p50_latency_delta_ms,
            criteria.max_p50_latency_delta_ms,
            "max",
        ),
        (
            "p95_latency_delta",
            metrics.p95_latency_delta_ms,
            criteria.max_p95_latency_delta_ms,
            "max",
        ),
        (
            "p99_latency_delta",
            metrics.p99_latency_delta_ms,
            criteria.max_p99_latency_delta_ms,
            "max",
        ),
        (
            "max_gap_delta",
            metrics.max_gap_delta_ms,
            criteria.max_gap_delta_ms,
            "max",
        ),
    )
    for name, actual, threshold, direction in checks:
        if actual is None:
            continue
        if direction == "max" and actual > threshold:
            failed.append(name)
        if direction == "min" and actual < threshold:
            failed.append(name)
    if criteria.require_latest_book_equal and metrics.latest_book_equal is False:
        failed.append("latest_book_not_equal")
    if criteria.require_terminal_tick_type_equal and metrics.terminal_tick_type_equal is False:
        failed.append("terminal_tick_type_not_equal")
    if criteria.require_derived_digest_equal and metrics.derived_digest_equal is False:
        failed.append("derived_digest_not_equal")
    if criteria.require_reconnect_test:
        if metrics.quote_reconnect_continuity is False:
            failed.append("quote_reconnect_continuity_failed")
        if metrics.tick_bidask_reconnect_continuity is False:
            failed.append("tick_bidask_reconnect_continuity_failed")
    if criteria.require_non_negative_source_latency:
        if metrics.quote_negative_latency_count:
            failed.append("quote_source_clock_ahead")
        if metrics.tick_bidask_negative_latency_count:
            failed.append("tick_bidask_source_clock_ahead")
    return failed
