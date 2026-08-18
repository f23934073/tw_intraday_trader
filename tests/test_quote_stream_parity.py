"""Offline Phase 0 tests for Quote versus Tick+BidAsk qualification."""

from dataclasses import replace
from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

from config.momentum import QuoteSubscriptionMode
from market_data.quote_qualification import (
    DerivedOutputDigest,
    ObservationKind,
    QuoteParityCriteria,
    QuoteParityStatus,
    StreamCapture,
    StreamObservation,
    evaluate_quote_parity,
)


TAIPEI = ZoneInfo("Asia/Taipei")
BASE_TIME = datetime(2026, 8, 18, 9, 15, tzinfo=TAIPEI)


def observation(
    mode: QuoteSubscriptionMode,
    kind: ObservationKind,
    seconds: int,
    *,
    total_volume_lots: int | None = None,
    total_amount: Decimal | None = None,
    bid_price: Decimal = Decimal("277.5"),
) -> StreamObservation:
    event_time = BASE_TIME + timedelta(seconds=seconds)
    common = dict(
        source_mode=mode,
        symbol="8039",
        kind=kind,
        event_time=event_time,
        received_at=event_time + timedelta(milliseconds=10),
    )
    if kind is ObservationKind.TRADE:
        return StreamObservation(
            **common,
            total_volume_lots=total_volume_lots,
            total_amount=total_amount,
            last_price=Decimal("278"),
            average_price=Decimal("270.76"),
            raw_tick_type=1,
            bid_side_total_lots=6_919,
            ask_side_total_lots=4_193,
        )
    return StreamObservation(
        **common,
        bid_prices=(bid_price, Decimal("277")),
        bid_volume_lots=(3000, 1200),
        ask_prices=(Decimal("278"), Decimal("278.5")),
        ask_volume_lots=(1000, 800),
    )


def capture(
    mode: QuoteSubscriptionMode,
    *,
    terminal_volume_offset: int = 0,
    final_bid_price: Decimal = Decimal("277.5"),
    reconnect_continuity: bool = True,
) -> StreamCapture:
    return StreamCapture(
        source_mode=mode,
        symbol="8039",
        observations=(
            observation(
                mode,
                ObservationKind.TRADE,
                0,
                total_volume_lots=10_000,
                total_amount=Decimal("275000000"),
            ),
            observation(mode, ObservationKind.BOOK, 1),
            observation(
                mode,
                ObservationKind.TRADE,
                2,
                total_volume_lots=11_112 + terminal_volume_offset,
                total_amount=Decimal("306000000"),
            ),
            observation(
                mode,
                ObservationKind.BOOK,
                3,
                bid_price=final_bid_price,
            ),
        ),
        reconnect_attempted=True,
        continuity_verified_after_reconnect=reconnect_continuity,
    )


def criteria() -> QuoteParityCriteria:
    """Test-only reviewed criteria; production Phase 0 values remain unfrozen."""
    return QuoteParityCriteria(
        version="quote_parity_test_v0",
        max_terminal_volume_delta_lots=0,
        max_terminal_amount_delta=Decimal("0"),
        max_terminal_average_price_delta=Decimal("0"),
        max_terminal_bid_side_volume_delta_lots=0,
        max_terminal_ask_side_volume_delta_lots=0,
        max_latest_trade_time_delta_ms=0,
        max_latest_book_time_delta_ms=0,
        min_trade_event_count_ratio=Decimal("1"),
        min_book_event_count_ratio=Decimal("1"),
        max_p50_latency_delta_ms=0,
        max_p95_latency_delta_ms=0,
        max_p99_latency_delta_ms=0,
        max_gap_delta_ms=0,
        require_latest_book_equal=True,
        require_terminal_tick_type_equal=True,
        require_derived_digest_equal=True,
        require_reconnect_test=True,
        require_non_negative_source_latency=True,
    )


def digest(mode: QuoteSubscriptionMode, suffix: str = "same") -> DerivedOutputDigest:
    return DerivedOutputDigest(
        source_mode=mode,
        feature_digest=f"feature-{suffix}",
        signal_digest=f"signal-{suffix}",
        stage_digest=f"stage-{suffix}",
        alert_digest=f"alert-{suffix}",
    )


def test_missing_reviewed_criteria_is_incomplete():
    report = evaluate_quote_parity(
        capture(QuoteSubscriptionMode.QUOTE),
        capture(QuoteSubscriptionMode.TICK_BIDASK),
        criteria=None,
    )

    assert report.status is QuoteParityStatus.INCOMPLETE
    assert report.qualified_for_quote is False
    assert "criteria_not_frozen" in report.incomplete_reasons


def test_equal_captures_with_all_required_evidence_pass():
    report = evaluate_quote_parity(
        capture(QuoteSubscriptionMode.QUOTE),
        capture(QuoteSubscriptionMode.TICK_BIDASK),
        criteria=criteria(),
        quote_digest=digest(QuoteSubscriptionMode.QUOTE),
        tick_bidask_digest=digest(QuoteSubscriptionMode.TICK_BIDASK),
    )

    assert report.status is QuoteParityStatus.PASS
    assert report.qualified_for_quote is True
    assert report.incomplete_reasons == ()
    assert report.failed_checks == ()
    assert report.metrics.latest_book_equal is True
    assert report.metrics.derived_digest_equal is True
    assert report.metrics.quote_p50_latency_ms == 10.0
    assert report.metrics.quote_p95_latency_ms == 10.0
    assert report.metrics.quote_p99_latency_ms == 10.0


def test_volume_book_and_digest_mismatches_fail_explicit_checks():
    report = evaluate_quote_parity(
        capture(QuoteSubscriptionMode.QUOTE),
        capture(
            QuoteSubscriptionMode.TICK_BIDASK,
            terminal_volume_offset=1,
            final_bid_price=Decimal("277"),
        ),
        criteria=criteria(),
        quote_digest=digest(QuoteSubscriptionMode.QUOTE),
        tick_bidask_digest=digest(QuoteSubscriptionMode.TICK_BIDASK, "different"),
    )

    assert report.status is QuoteParityStatus.FAIL
    assert report.qualified_for_quote is False
    assert report.failed_checks == (
        "terminal_volume_delta",
        "latest_book_not_equal",
        "derived_digest_not_equal",
    )


def test_missing_digest_is_incomplete_when_digest_parity_is_required():
    report = evaluate_quote_parity(
        capture(QuoteSubscriptionMode.QUOTE),
        capture(QuoteSubscriptionMode.TICK_BIDASK),
        criteria=criteria(),
    )

    assert report.status is QuoteParityStatus.INCOMPLETE
    assert report.incomplete_reasons == ("missing_derived_digest",)


def test_reconnect_continuity_failure_cannot_pass():
    quote_capture = capture(
        QuoteSubscriptionMode.QUOTE,
        reconnect_continuity=False,
    )
    report = evaluate_quote_parity(
        quote_capture,
        capture(QuoteSubscriptionMode.TICK_BIDASK),
        criteria=criteria(),
        quote_digest=digest(QuoteSubscriptionMode.QUOTE),
        tick_bidask_digest=digest(QuoteSubscriptionMode.TICK_BIDASK),
    )

    assert report.status is QuoteParityStatus.FAIL
    assert report.failed_checks == ("quote_reconnect_continuity_failed",)


def test_raw_tick_type_mismatch_is_reported_without_mapping_to_buy_or_sell():
    paired = capture(QuoteSubscriptionMode.TICK_BIDASK)
    observations = tuple(
        replace(item, raw_tick_type=2)
        if item.kind is ObservationKind.TRADE and item.total_volume_lots == 11_112
        else item
        for item in paired.observations
    )
    paired = replace(paired, observations=observations)

    report = evaluate_quote_parity(
        capture(QuoteSubscriptionMode.QUOTE),
        paired,
        criteria=criteria(),
        quote_digest=digest(QuoteSubscriptionMode.QUOTE),
        tick_bidask_digest=digest(QuoteSubscriptionMode.TICK_BIDASK),
    )

    assert report.status is QuoteParityStatus.FAIL
    assert report.failed_checks == ("terminal_tick_type_not_equal",)


def test_missing_terminal_volume_is_incomplete_not_zero_delta():
    quote = capture(QuoteSubscriptionMode.QUOTE)
    observations = tuple(
        replace(item, total_volume_lots=None)
        if item.kind is ObservationKind.TRADE
        else item
        for item in quote.observations
    )
    quote = replace(quote, observations=observations)

    report = evaluate_quote_parity(
        quote,
        capture(QuoteSubscriptionMode.TICK_BIDASK),
        criteria=criteria(),
        quote_digest=digest(QuoteSubscriptionMode.QUOTE),
        tick_bidask_digest=digest(QuoteSubscriptionMode.TICK_BIDASK),
    )

    assert report.status is QuoteParityStatus.INCOMPLETE
    assert "missing_terminal_volume_delta_lots" in report.incomplete_reasons


def test_negative_source_latency_is_an_explicit_clock_gate_failure():
    quote = capture(QuoteSubscriptionMode.QUOTE)
    observations = tuple(
        replace(item, received_at=item.event_time - timedelta(milliseconds=1))
        for item in quote.observations
    )
    quote = replace(quote, observations=observations)

    report = evaluate_quote_parity(
        quote,
        capture(QuoteSubscriptionMode.TICK_BIDASK),
        criteria=criteria(),
        quote_digest=digest(QuoteSubscriptionMode.QUOTE),
        tick_bidask_digest=digest(QuoteSubscriptionMode.TICK_BIDASK),
    )

    assert report.status is QuoteParityStatus.FAIL
    assert "quote_source_clock_ahead" in report.failed_checks
