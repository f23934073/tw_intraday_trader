"""Journal v2 exposure projection and immutable v1 import contracts."""

from datetime import date, datetime
from decimal import Decimal

import pytest

from market_data.models import (
    LocalPaperInstrumentDescriptorV1,
    LocalPaperProductClass,
)
from market_data.provider import MockProvider
from simulation.service import SimulationService
from trading.exposure import (
    ExecutionReasonCategory,
    HoldingHorizon,
    PositionAction,
    build_exposure_identity,
)
from trading.journal import (
    InMemoryJournalRepository,
    JournalConflictError,
    JournalRecord,
    JournalSession,
    ProjectionCheckpoint,
)
from trading.local_paper import (
    LOCAL_PAPER_FILL_V4_KIND,
    LOCAL_PAPER_V1_IMPORTED_KIND,
    LocalPaperExposureProjection,
    LocalPaperProjection,
    ProjectionRecoveryError,
    build_local_paper_v1_import_record,
    journal_record_from_simulation_order,
    latest_local_paper_order_states,
    order_state_record_from_simulation_order,
    rebuild_local_paper_v2_projection,
)


AT = datetime.fromisoformat("2026-08-23T09:30:00+08:00")
V1_SESSION_ID = "local-paper-runtime-v1"
V2_SESSION_ID = "local-paper-runtime-v2"
ACCOUNT_SCOPE_ID = "local-paper-main-v1"
POLICY_FAMILY_ID = "no-overnight-equity-v1"
SETTINGS_DIGEST = "d" * 64


DESCRIPTOR = LocalPaperInstrumentDescriptorV1(
    symbol="2330",
    exchange_raw="TWSE",
    security_type_raw="STOCK",
    product_category_raw="COMMON_STOCK",
    normalized_product_class=LocalPaperProductClass.COMMON_STOCK,
    source_identity="test.exposure_projection",
)


def _identity(*, horizon: HoldingHorizon, entry_identity: str):
    return build_exposure_identity(
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
        holding_horizon=horizon,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="local-paper-exposure-policy-v1",
        entry_policy_digest="a" * 64,
        entry_identity=entry_identity,
    )


def _order_payload(*, identity, side: str, order_id: str, quantity: int = 100):
    fill_price = Decimal("10") if side == "BUY" else Decimal("12")
    gross = fill_price * quantity
    commission = Decimal("20")
    tax = Decimal("0") if side == "BUY" else Decimal("3")
    return {
        "order_id": order_id,
        "idempotency_key": order_id,
        "origin": "MANUAL_WEB",
        "strategy_id": None,
        "strategy_version": None,
        "symbol": "2330",
        "name": "台積電",
        "side": side,
        "quantity_shares": quantity,
        "filled_quantity": quantity,
        "filled_price": fill_price,
        "filled_amount": gross,
        "filled_amount_decimal": str(gross),
        "filled_commission": commission,
        "filled_commission_decimal": str(commission),
        "filled_tax": str(tax),
        "last_fill_quantity": quantity,
        "last_fill_price": fill_price,
        "last_fill_price_decimal": str(fill_price),
        "last_fill_commission": commission,
        "last_fill_commission_decimal": str(commission),
        "last_fill_tax": str(tax),
        "last_reference_price": str(fill_price),
        "last_reference_source": "SNAPSHOT_COMPATIBILITY",
        "configured_slippage_bps": "0",
        "last_realized_slippage_bps": "0",
        "last_slippage_cost": "0",
        "last_net_cash_effect": str(
            -(gross + commission)
            if side == "BUY"
            else gross - commission - tax
        ),
        "fee_policy_version": "tw_stock_standard_v1",
        "rounding_policy_version": "twd_round_down_v1",
        "slippage_policy_version": "fixed_adverse_bps_v1",
        "price_tick_policy_version": "tw_common_stock_tick_v1",
        "instrument_descriptor_snapshot": DESCRIPTOR.to_dict(),
        "instrument_descriptor_digest": DESCRIPTOR.digest,
        "limit_price": str(fill_price),
        "limit_price_decimal": str(fill_price),
        "fill_sequence": 1,
        "status": "FILLED",
        "updated_at": AT.isoformat(),
        "exposure_identity": identity.to_payload(),
        "position_action": "OPEN_LONG" if side == "BUY" else "CLOSE_LONG",
        "target_exposure_id": identity.exposure_id if side == "SELL" else None,
        "execution_reason_category": "STRATEGY",
        "execution_reason_code": "MANUAL_ORDER",
        "fill_source": "paper_simulation",
        "provider_identity": "market_data.provider.MockProvider",
        "execution_authority": False,
    }


def _journal() -> InMemoryJournalRepository:
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=V2_SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                "account_scope_id": ACCOUNT_SCOPE_ID,
                "policy_family_id": POLICY_FAMILY_ID,
            },
        )
    )
    return journal


def test_v2_fill_reducer_keeps_same_symbol_exposures_independent() -> None:
    journal = _journal()
    long_term = _identity(
        horizon=HoldingHorizon.LONG_TERM,
        entry_identity="manual-long",
    )
    intraday = _identity(
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="manual-day",
    )
    projection = LocalPaperExposureProjection(
        starting_cash=Decimal("10000"),
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        settings_digest=SETTINGS_DIGEST,
    )
    for payload in (
        _order_payload(identity=long_term, side="BUY", order_id="long-buy"),
        _order_payload(identity=intraday, side="BUY", order_id="day-buy"),
        _order_payload(identity=intraday, side="SELL", order_id="day-sell"),
    ):
        record = journal_record_from_simulation_order(
            payload,
            session_id=V2_SESSION_ID,
            settings_digest=SETTINGS_DIGEST,
        )
        assert record is not None
        assert record.kind == LOCAL_PAPER_FILL_V4_KIND
        projection.apply(journal.append(record))

    assert projection.cash == Decimal("9137")
    assert projection.position(long_term.exposure_id).quantity_shares == 100
    assert projection.position(intraday.exposure_id) is None
    assert projection.realized_pnl(intraday.exposure_id) == Decimal("157")
    assert projection.aggregate_quantity("2330") == 100


def test_v2_fill_reader_rejects_scope_or_target_identity_mismatch() -> None:
    identity = _identity(
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="mismatch",
    )
    payload = _order_payload(identity=identity, side="SELL", order_id="bad-sell")
    payload["target_exposure_id"] = "different-exposure"

    with pytest.raises(ProjectionRecoveryError, match="target exposure"):
        journal_record_from_simulation_order(
            payload,
            session_id=V2_SESSION_ID,
            settings_digest=SETTINGS_DIGEST,
        )

    wrong_scope = build_exposure_identity(
        account_scope_id="different-scope",
        policy_family_id=POLICY_FAMILY_ID,
        owner_origin="MANUAL_WEB",
        owner_id="manual-web",
        holding_horizon=HoldingHorizon.INTRADAY,
        entry_session_date=date(2026, 8, 23),
        entry_policy_version="local-paper-exposure-policy-v1",
        entry_policy_digest="a" * 64,
        entry_identity="wrong-scope",
    )
    record = journal_record_from_simulation_order(
        _order_payload(identity=wrong_scope, side="BUY", order_id="wrong-scope"),
        session_id=V2_SESSION_ID,
        settings_digest=SETTINGS_DIGEST,
    )
    assert record is not None
    projection = LocalPaperExposureProjection(
        starting_cash=Decimal("10000"),
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        settings_digest=SETTINGS_DIGEST,
    )
    with pytest.raises(ProjectionRecoveryError, match="account scope mismatch"):
        projection.apply(_journal().append(record))


def test_v2_fill_reader_rejects_boolean_quantity_without_mutation() -> None:
    identity = _identity(
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="strict-fill-quantity",
    )
    valid = journal_record_from_simulation_order(
        _order_payload(identity=identity, side="BUY", order_id="strict-fill"),
        session_id=V2_SESSION_ID,
        settings_digest=SETTINGS_DIGEST,
    )
    assert valid is not None
    malformed = JournalRecord(
        record_id="strict-fill:boolean-quantity",
        session_id=V2_SESSION_ID,
        kind=LOCAL_PAPER_FILL_V4_KIND,
        occurred_at=AT,
        payload={**valid.payload, "quantity_shares": True},
    )
    journal = _journal()
    projection = LocalPaperExposureProjection(
        starting_cash=Decimal("10000"),
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        settings_digest=SETTINGS_DIGEST,
    )

    with pytest.raises(ProjectionRecoveryError, match="quantity_shares"):
        projection.apply(journal.append(malformed))

    assert projection.cash == Decimal("10000")
    assert projection.positions == ()


def test_v2_order_state_reader_rejects_boolean_quantity() -> None:
    identity = _identity(
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="strict-order-state-quantity",
    )
    service = SimulationService(MockProvider(), starting_cash=Decimal("10000"))
    order, _ = service.submit_order(
        symbol="2330",
        side="BUY",
        quantity_shares=1,
        limit_price=1000,
        idempotency_key="strict-state-order",
        exposure=identity,
        position_action=PositionAction.OPEN_LONG,
        execution_reason_category=ExecutionReasonCategory.STRATEGY,
        execution_reason_code="MANUAL_ORDER",
    )
    valid = order_state_record_from_simulation_order(
        order,
        session_id=V2_SESSION_ID,
    )
    unsigned_payload = dict(valid.payload)
    unsigned_payload.pop("order_state_digest")
    malformed = JournalRecord(
        record_id="strict-state:boolean-quantity",
        session_id=V2_SESSION_ID,
        kind=valid.kind,
        occurred_at=valid.occurred_at,
        payload={**unsigned_payload, "quantity_shares": True},
    )
    journal = _journal()
    journal.append(malformed)

    with pytest.raises(ProjectionRecoveryError, match="quantity_shares"):
        latest_local_paper_order_states(journal, session_id=V2_SESSION_ID)


def test_v2_order_state_reader_rejects_unknown_fields() -> None:
    identity = _identity(
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="strict-order-state-fields",
    )
    service = SimulationService(MockProvider(), starting_cash=Decimal("10000"))
    order, _ = service.submit_order(
        symbol="2330",
        side="BUY",
        quantity_shares=1,
        limit_price=1000,
        idempotency_key="strict-state-fields",
        exposure=identity,
        position_action=PositionAction.OPEN_LONG,
        execution_reason_category=ExecutionReasonCategory.STRATEGY,
        execution_reason_code="MANUAL_ORDER",
    )
    valid = order_state_record_from_simulation_order(
        order,
        session_id=V2_SESSION_ID,
    )
    unsigned_payload = dict(valid.payload)
    unsigned_payload.pop("order_state_digest")
    malformed = JournalRecord(
        record_id="strict-state:unknown-field",
        session_id=V2_SESSION_ID,
        kind=valid.kind,
        occurred_at=valid.occurred_at,
        payload={**unsigned_payload, "unexpected_field": "unexpected"},
    )
    journal = _journal()
    journal.append(malformed)

    with pytest.raises(ProjectionRecoveryError, match="fields mismatch"):
        latest_local_paper_order_states(journal, session_id=V2_SESSION_ID)


def test_v1_import_is_unclassified_idempotent_and_source_digest_bound() -> None:
    source = LocalPaperProjection(
        starting_cash=Decimal("10000"),
        settings_digest=SETTINGS_DIGEST,
    )
    source_journal = InMemoryJournalRepository()
    source_journal.start_session(
        JournalSession(
            session_id=V1_SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"starting_cash": "10000"},
        )
    )
    legacy_fill = journal_record_from_simulation_order(
        {
            **_order_payload(
                identity=_identity(
                    horizon=HoldingHorizon.LONG_TERM,
                    entry_identity="ignored-v1-identity",
                ),
                side="BUY",
                order_id="legacy-buy",
            ),
            "execution_reason_category": None,
            "execution_reason_code": None,
        },
        session_id=V1_SESSION_ID,
        settings_digest=SETTINGS_DIGEST,
    )
    assert legacy_fill is not None
    source.apply(source_journal.append(legacy_fill))

    target = _journal()
    manifest = build_local_paper_v1_import_record(
        source_projection=source,
        source_session_id=V1_SESSION_ID,
        target_session_id=V2_SESSION_ID,
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        occurred_at=AT,
    )
    first = target.append(manifest)
    repeated = target.append(manifest)
    assert first.record.kind == LOCAL_PAPER_V1_IMPORTED_KIND
    assert repeated.idempotent is True

    restored = LocalPaperExposureProjection(
        starting_cash=Decimal("10000"),
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
    )
    restored.apply(first)
    exposure = restored.positions[0]
    assert exposure.exposure.holding_horizon is HoldingHorizon.UNCLASSIFIED_LEGACY
    assert exposure.exposure.no_overnight_managed is False
    assert restored.cash == source.cash
    assert (
        restored.aggregate_quantity("2330") == source.position("2330").quantity_shares
    )

    changed = build_local_paper_v1_import_record(
        source_projection=LocalPaperProjection(starting_cash=Decimal("20000")),
        source_session_id=V1_SESSION_ID,
        target_session_id=V2_SESSION_ID,
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        occurred_at=AT,
    )
    with pytest.raises(JournalConflictError):
        target.append(changed)


def test_v2_rebuild_requires_exactly_one_predecessor_manifest() -> None:
    with pytest.raises(ProjectionRecoveryError, match="exactly one"):
        rebuild_local_paper_v2_projection(
            _journal(),
            session_id=V2_SESSION_ID,
            starting_cash=Decimal("10000"),
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            require_checkpoint=False,
        )


def test_v2_rebuild_rejects_corrupted_checkpoint_digest() -> None:
    source = LocalPaperProjection(starting_cash=Decimal("10000"))
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=V2_SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                "account_scope_id": ACCOUNT_SCOPE_ID,
                "policy_family_id": POLICY_FAMILY_ID,
                "predecessor_session_id": V1_SESSION_ID,
                "predecessor_terminal_sequence": source.last_sequence,
                "predecessor_digest": source.digest,
            },
        )
    )
    appended = journal.append(
        build_local_paper_v1_import_record(
            source_projection=source,
            source_session_id=V1_SESSION_ID,
            target_session_id=V2_SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            occurred_at=AT,
        )
    )
    journal.save_checkpoint(
        ProjectionCheckpoint(
            session_id=V2_SESSION_ID,
            projection_name="local_paper.v2",
            journal_sequence=appended.sequence,
            digest="corrupted",
        )
    )

    with pytest.raises(ProjectionRecoveryError, match="checkpoint digest mismatch"):
        rebuild_local_paper_v2_projection(
            journal,
            session_id=V2_SESSION_ID,
            starting_cash=Decimal("10000"),
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
        )


def test_v2_rebuild_rejects_uncheckpointed_v4_fill_tail() -> None:
    source = LocalPaperProjection(starting_cash=Decimal("10000"))
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=V2_SESSION_ID,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                "account_scope_id": ACCOUNT_SCOPE_ID,
                "policy_family_id": POLICY_FAMILY_ID,
                "predecessor_session_id": V1_SESSION_ID,
                "predecessor_terminal_sequence": source.last_sequence,
                "predecessor_digest": source.digest,
            },
        )
    )
    manifest = journal.append(
        build_local_paper_v1_import_record(
            source_projection=source,
            source_session_id=V1_SESSION_ID,
            target_session_id=V2_SESSION_ID,
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            occurred_at=AT,
        )
    )
    checkpointed = LocalPaperExposureProjection(
        starting_cash=Decimal("10000"),
        account_scope_id=ACCOUNT_SCOPE_ID,
        policy_family_id=POLICY_FAMILY_ID,
        settings_digest=SETTINGS_DIGEST,
    )
    checkpointed.apply(manifest)
    journal.save_checkpoint(
        ProjectionCheckpoint(
            session_id=V2_SESSION_ID,
            projection_name="local_paper.v2",
            journal_sequence=manifest.sequence,
            digest=checkpointed.digest,
        )
    )
    identity = _identity(
        horizon=HoldingHorizon.INTRADAY,
        entry_identity="uncheckpointed-v4-tail",
    )
    fill = journal_record_from_simulation_order(
        _order_payload(identity=identity, side="BUY", order_id="tail-buy"),
        session_id=V2_SESSION_ID,
        settings_digest=SETTINGS_DIGEST,
    )
    assert fill is not None
    journal.append(fill)

    with pytest.raises(
        ProjectionRecoveryError,
        match="local-paper v2 checkpoint does not cover Journal tail",
    ):
        rebuild_local_paper_v2_projection(
            journal,
            session_id=V2_SESSION_ID,
            starting_cash=Decimal("10000"),
            account_scope_id=ACCOUNT_SCOPE_ID,
            policy_family_id=POLICY_FAMILY_ID,
            settings_digest=SETTINGS_DIGEST,
        )
