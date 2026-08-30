"""Sealed Taiwan Local Paper execution adapter parity and fail-closed tests."""

from datetime import date, datetime, time
from decimal import Decimal

from backtest.cost_policy_tw import build_cost_policy_snapshot, calculate_costs
from backtest.execution_policy_tw import build_execution_policy_snapshot
from market_data.session_evidence import (
    BidAskEvidence,
    GuardHealth,
    InstrumentStatus,
    ServerExecutionEvidenceSnapshot,
    SessionPhase,
    SpecialSessionRegime,
)
from simulation.execution_policy_tw import (
    LocalPaperAllocationSource,
    TwLocalPaperExecutionPolicyAdapter,
)
from trading.exposure import (
    ExecutionReasonCategory,
    HoldingHorizon,
    PositionAction,
    build_exposure_identity,
    build_semantic_action_key,
)
from trading.no_overnight import NoOvernightReason, NoOvernightState
from trading.no_overnight_admission import FinalExecutionAdmissionPolicy
from trading.risk import CommandOrigin, CommandSide, OrderCommand


AT = datetime.fromisoformat("2026-08-24T13:30:00+08:00")


def _sealed_inputs():
    execution = build_execution_policy_snapshot(
        max_participation_rate="1",
        participation_calibration_digest="a" * 64,
        bar_volume_unit="SHARES",
    )
    cost = build_cost_policy_snapshot(
        commission_rate="0.001425",
        min_commission_twd="20",
        slippage_bps="0",
        slippage_calibration_digest="b" * 64,
    )
    policy = FinalExecutionAdmissionPolicy(
        calendar_schema_version="tw-calendar-v1",
        calendar_digest="c" * 64,
        executable_book_policy_id="book-v1",
        book_staleness_policy_id="age-v1",
        execution_policy_digest=str(execution["snapshot_digest"]),
        cost_policy_digest=str(cost["snapshot_digest"]),
        guard_identity="guard-v1",
        reviewed_closing_auction_at=time(13, 30),
    )
    return execution, cost, policy


def _evidence(**overrides: object) -> ServerExecutionEvidenceSnapshot:
    execution, cost, _ = _sealed_inputs()
    values: dict[str, object] = {
        "captured_at": AT,
        "received_at": AT,
        "calendar_schema_version": "tw-calendar-v1",
        "calendar_digest": "c" * 64,
        "calendar_coverage_start": date(2026, 1, 1),
        "calendar_coverage_end": date(2026, 12, 31),
        "session_date": AT.date(),
        "session_phase": SessionPhase.CLOSING_AUCTION,
        "symbol": "3231",
        "instrument_status": InstrumentStatus.TRADING,
        "tradable": True,
        "pit_reference_price": Decimal("100"),
        "pit_lower_limit_price": Decimal("90"),
        "pit_upper_limit_price": Decimal("110"),
        "pit_price_as_of": AT,
        "special_session_regime": SpecialSessionRegime.NORMAL,
        "bid_ask": None,
        "executable_book_policy_id": None,
        "book_staleness_policy_id": None,
        "max_book_age_milliseconds": None,
        "isolated_auction_event_id": "auction:3231:2026-08-24:13:30",
        "isolated_auction_event_at": AT,
        "isolated_auction_price": Decimal("100"),
        "isolated_auction_matchable_volume": 1_000,
        "isolated_auction_volume_unit": "SHARES",
        "isolated_auction_event_digest": "d" * 64,
        "execution_policy_digest": execution["snapshot_digest"],
        "cost_policy_digest": cost["snapshot_digest"],
        "no_overnight_state": NoOvernightState.AGGRESSIVE_EXIT,
        "no_overnight_revision": 4,
        "breach_latched": False,
        "guard_identity": "guard-v1",
        "guard_health": GuardHealth.HEALTHY,
    }
    values.update(overrides)
    return ServerExecutionEvidenceSnapshot(**values)


def _command() -> OrderCommand:
    exposure = build_exposure_identity(
        account_scope_id="local-paper-main-v1",
        policy_family_id="no-overnight-equity-v1",
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
        holding_horizon=HoldingHorizon.INTRADAY,
        entry_session_date=AT.date(),
        entry_policy_version="entry-v1",
        entry_policy_digest="e" * 64,
        entry_identity="manual-entry-3231",
    )
    key = build_semantic_action_key(
        account_scope_id=exposure.account_scope_id,
        policy_family_id=exposure.policy_family_id,
        session_date=AT.date(),
        exposure_id=exposure.exposure_id,
        action=PositionAction.CLOSE_LONG.value,
        attempt=1,
    )
    return OrderCommand(
        command_id="auction-close-1",
        session_id="local-paper-k3-auction",
        origin=CommandOrigin.MANUAL_WEB,
        symbol="3231",
        side=CommandSide.SELL,
        quantity_shares=1_000,
        limit_price=Decimal("90"),
        idempotency_key=key,
        requested_at=AT,
        exposure=exposure,
        position_action=PositionAction.CLOSE_LONG,
        target_exposure_id=exposure.exposure_id,
        execution_reason_category=ExecutionReasonCategory.OPERATIONAL_RISK,
        execution_reason_code="NO_OVERNIGHT_EXIT",
    )


def _adapter() -> tuple[TwLocalPaperExecutionPolicyAdapter, dict, dict]:
    execution, cost, policy = _sealed_inputs()
    return (
        TwLocalPaperExecutionPolicyAdapter(
            execution_policy_snapshot=execution,
            cost_policy_snapshot=cost,
            admission_policy=policy,
            allocated_auction_sessions={},
        ),
        execution,
        cost,
    )


def test_one_isolated_1330_event_allocates_once_with_pure_cost_parity() -> None:
    adapter, _, cost = _adapter()
    first = adapter.allocate_close_long(
        command=_command(),
        evidence=_evidence(),
        evaluated_at=AT,
    )

    assert first.allocated is True
    assert first.allocation is not None
    assert first.allocation.source is LocalPaperAllocationSource.ISOLATED_CLOSING_AUCTION
    assert first.allocation.quantity_shares == 1_000
    pure = calculate_costs(
        pre_cost_price="100",
        post_cost_price="100",
        shares=1_000,
        side="EXIT",
        trade_date=AT.date(),
        is_day_trade=True,
        cost_policy_snapshot=cost,
    )
    assert first.allocation.commission == pure.commission
    assert first.allocation.tax == pure.tax
    assert first.allocation.slippage == pure.slippage
    assert first.allocation.total_cost == pure.total

    duplicate = adapter.allocate_close_long(
        command=_command(),
        evidence=_evidence(),
        evaluated_at=AT,
    )
    assert duplicate.allocation is None
    assert duplicate.reason is NoOvernightReason.RECOVERY_REQUIRED


def test_missing_wrong_time_zero_and_generic_close_inputs_never_allocate() -> None:
    command = _command()
    cases = [
        (
            _evidence(
                isolated_auction_event_id=None,
                isolated_auction_event_at=None,
                isolated_auction_price=None,
                isolated_auction_matchable_volume=None,
                isolated_auction_volume_unit=None,
                isolated_auction_event_digest=None,
            ),
            NoOvernightReason.MISSING_AUCTION_EVENT,
        ),
        (
            _evidence(
                isolated_auction_event_at=datetime.fromisoformat("2026-08-24T13:29:59+08:00")
            ),
            NoOvernightReason.MISSING_AUCTION_EVENT,
        ),
        (
            _evidence(isolated_auction_matchable_volume=0),
            NoOvernightReason.ZERO_AUCTION_MATCHABLE_VOLUME,
        ),
    ]
    for evidence, reason in cases:
        adapter, _, _ = _adapter()
        decision = adapter.allocate_close_long(
            command=command,
            evidence=evidence,
            evaluated_at=AT,
        )
        assert decision.allocation is None
        assert decision.reason is reason

    adapter, _, _ = _adapter()
    generic = adapter.allocate_close_long(
        command=command,
        evidence={"close": "100", "volume": 1_000},  # type: ignore[arg-type]
        evaluated_at=AT,
    )
    assert generic.allocation is None
    assert generic.reason is NoOvernightReason.IDENTITY_MISMATCH


def test_continuous_sell_is_side_aware_at_price_limits() -> None:
    no_auction = {
        "isolated_auction_event_id": None,
        "isolated_auction_event_at": None,
        "isolated_auction_price": None,
        "isolated_auction_matchable_volume": None,
        "isolated_auction_volume_unit": None,
        "isolated_auction_event_digest": None,
        "session_phase": SessionPhase.CONTINUOUS,
        "executable_book_policy_id": "book-v1",
        "book_staleness_policy_id": "age-v1",
        "max_book_age_milliseconds": 1_000,
    }
    adapter, _, _ = _adapter()
    limit_down = adapter.allocate_close_long(
        command=_command(),
        evidence=_evidence(
            **no_auction,
            bid_ask=BidAskEvidence(
                source_as_of=AT,
                received_at=AT,
                best_bid_price=None,
                best_bid_quantity=0,
                best_ask_price=Decimal("90"),
                best_ask_quantity=1_000,
            ),
        ),
        evaluated_at=AT,
    )
    assert limit_down.allocation is None
    assert limit_down.reason is NoOvernightReason.LIMIT_DOWN_NO_BID

    adapter, _, _ = _adapter()
    limit_up = adapter.allocate_close_long(
        command=_command(),
        evidence=_evidence(
            **no_auction,
            bid_ask=BidAskEvidence(
                source_as_of=AT,
                received_at=AT,
                best_bid_price=Decimal("110"),
                best_bid_quantity=1_000,
                best_ask_price=None,
                best_ask_quantity=0,
            ),
        ),
        evaluated_at=AT,
    )
    assert limit_up.allocated is True
    assert limit_up.allocation is not None
    assert limit_up.allocation.fill_price == Decimal("110")
