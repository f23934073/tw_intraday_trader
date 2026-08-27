from __future__ import annotations

from dataclasses import replace
from datetime import timedelta
from decimal import Context, Decimal, localcontext

import pytest

from market_data.provider import MockProvider
from runtime.in_memory import InMemoryJournalRepository
from runtime.trade_management_operational_composition import (
    ExistingPaperFillObserver,
    PaperFillNotObservedError,
    PaperFillObservationConflictError,
)
from simulation.application import LocalPaperCommandService
from simulation.execution_costs import (
    cumulative_commission_for,
    is_valid_common_stock_tick,
)
from simulation.service import SimulationService
from tests.test_live_entry_thesis_draft import decision, policy
from tests.test_trade_management_operational_composition import shadow_policy
from trading.canonical_values import canonical_decimal_string
from trading.journal import JournalAppendResult, JournalRecord, JournalSession
from trading.live_entry_thesis_draft import LiveTradeThesisDraftBuilder
from trading.local_paper import (
    LOCAL_PAPER_FILL_V2_KIND,
    LOCAL_PAPER_FILL_V3_KIND,
    LocalPaperFill,
    ProjectionRecoveryError,
    order_state_record_from_simulation_order,
)
from trading.paper_thesis_activation import (
    PaperFillThesisBuilder,
    paper_thesis_entry_idempotency_key,
)


SETTINGS_DIGEST = "a" * 64


class FixedClock:
    def __init__(self, current) -> None:
        self.current = current

    def now(self):
        return self.current

    def session_date(self):
        return self.current.date()


class StaticJournal:
    """Read-only fixture for impossible-in-a-valid-adapter duplicate rows."""

    def __init__(self, results: tuple[JournalAppendResult, ...]) -> None:
        self._results = results

    def records(self, session_id: str, *, after_sequence: int = 0):
        return tuple(
            result
            for result in self._results
            if result.record.session_id == session_id
            and result.sequence > after_sequence
        )


class ChangingJournal:
    """Expose a different tail on a second read to detect snapshot mixing."""

    def __init__(
        self,
        first: tuple[JournalAppendResult, ...],
        second: tuple[JournalAppendResult, ...],
    ) -> None:
        self._snapshots = (first, second)
        self.read_count = 0

    def records(self, session_id: str, *, after_sequence: int = 0):
        snapshot = self._snapshots[min(self.read_count, 1)]
        self.read_count += 1
        return tuple(
            result
            for result in snapshot
            if result.record.session_id == session_id
            and result.sequence > after_sequence
        )


def _settings_bound_entry(*, v3: bool):
    entry = decision()
    draft = LiveTradeThesisDraftBuilder().build(entry, policy())
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=draft.session_id,
            started_at=draft.signal_at.value,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={
                "execution_boundary": "LOCAL_ONLY",
                "settings_digest": SETTINGS_DIGEST,
            },
        )
    )
    clock = FixedClock(draft.created_at.value)
    simulation = SimulationService(
        MockProvider(),
        starting_cash=Decimal("2000000"),
        slippage_bps=Decimal("0"),
        cost_policy_enabled=v3,
        clock=clock,
    )
    service = LocalPaperCommandService(
        simulation=simulation,
        journal=journal,
        session_id=draft.session_id,
        clock=clock,
        settings_digest=SETTINGS_DIGEST,
    )
    order, _idempotent = service.submit_order(
        symbol=draft.symbol,
        side="BUY",
        lots=1,
        limit_price="1000",
        idempotency_key=paper_thesis_entry_idempotency_key(draft),
    )
    assert order["status"] == "FILLED"
    expected_kind = LOCAL_PAPER_FILL_V3_KIND if v3 else LOCAL_PAPER_FILL_V2_KIND
    fill = next(
        result.record
        for result in journal.records(draft.session_id)
        if result.record.kind == expected_kind
    )
    simulation.close()
    return draft, journal, order, fill


def _fill_record(
    base: JournalRecord,
    *,
    sequence: int,
    quantity_shares: int,
    occurred_at,
    cumulative_gross: Decimal,
    previous_commission: Decimal,
    fill_price: Decimal | None = None,
) -> JournalRecord:
    resolved_fill_price = fill_price or Decimal(str(base.payload["fill_price"]))
    reference_price = (
        resolved_fill_price
        if fill_price is not None
        else Decimal(str(base.payload["reference_price"]))
    )
    gross = resolved_fill_price * quantity_shares
    cumulative_commission = cumulative_commission_for(cumulative_gross)
    commission = cumulative_commission - previous_commission
    slippage_cost = abs(resolved_fill_price - reference_price) * quantity_shares
    payload = {
        **base.payload,
        "quantity_shares": quantity_shares,
        "fill_price": canonical_decimal_string(resolved_fill_price),
        "reference_price": canonical_decimal_string(reference_price),
        "gross_amount": canonical_decimal_string(gross),
        "net_cash_effect": canonical_decimal_string(-(gross + commission)),
        "commission": canonical_decimal_string(commission),
        "tax": "0",
        "slippage_cost": canonical_decimal_string(slippage_cost),
        "realized_slippage_bps": canonical_decimal_string(
            abs(resolved_fill_price - reference_price)
            / reference_price
            * Decimal("10000")
        ),
        "cumulative_order_gross": canonical_decimal_string(cumulative_gross),
        "cumulative_order_commission": canonical_decimal_string(
            cumulative_commission
        ),
        "cumulative_order_tax": "0",
        "fill_sequence": sequence,
    }
    order_id = str(base.payload["order_id"])
    return JournalRecord(
        record_id=f"local-paper-fill:{order_id}:{occurred_at.isoformat()}",
        session_id=base.session_id,
        kind=base.kind,
        occurred_at=occurred_at,
        payload=payload,
        idempotency_scope=base.idempotency_scope,
        idempotency_key=(order_id if sequence == 1 else f"{order_id}:{sequence}"),
        schema_version=base.schema_version,
    )


def _split_v3_fill(base: JournalRecord) -> tuple[JournalRecord, JournalRecord]:
    assert base.kind == LOCAL_PAPER_FILL_V3_KIND
    total_quantity = int(base.payload["quantity_shares"])
    first_quantity = 400
    second_quantity = total_quantity - first_quantity
    fill_price = Decimal(str(base.payload["fill_price"]))
    second_fill_price = fill_price + Decimal("0.01")
    while not is_valid_common_stock_tick(second_fill_price):
        second_fill_price += Decimal("0.01")
    first_gross = fill_price * first_quantity
    total_gross = (
        fill_price * first_quantity + second_fill_price * second_quantity
    )
    first = _fill_record(
        base,
        sequence=1,
        quantity_shares=first_quantity,
        occurred_at=base.occurred_at,
        cumulative_gross=first_gross,
        previous_commission=Decimal("0"),
    )
    second = _fill_record(
        base,
        sequence=2,
        quantity_shares=second_quantity,
        occurred_at=base.occurred_at + timedelta(microseconds=1),
        cumulative_gross=total_gross,
        previous_commission=Decimal(
            str(first.payload["cumulative_order_commission"])
        ),
        fill_price=second_fill_price,
    )
    LocalPaperFill.from_record(first)
    LocalPaperFill.from_record(second)
    return first, second


def _order_state_for_fill_prefix(
    order: dict,
    fills: tuple[JournalRecord, ...],
    *,
    status: str,
) -> JournalRecord:
    last = fills[-1]
    total_quantity = sum(int(fill.payload["quantity_shares"]) for fill in fills)
    total_gross = sum(
        Decimal(str(fill.payload["gross_amount"])) for fill in fills
    )
    total_commission = sum(
        Decimal(str(fill.payload["commission"])) for fill in fills
    )
    total_slippage = sum(
        Decimal(str(fill.payload["slippage_cost"])) for fill in fills
    )
    target_quantity = int(order["quantity_shares"])
    state = {
        **order,
        "status": status,
        "updated_at": last.occurred_at.isoformat(),
        "fill_sequence": len(fills),
        "filled_quantity": total_quantity,
        "remaining_quantity": target_quantity - total_quantity,
        "filled_amount": float(total_gross),
        "filled_amount_decimal": canonical_decimal_string(total_gross),
        "filled_commission": float(total_commission),
        "filled_commission_decimal": canonical_decimal_string(total_commission),
        "filled_tax": "0",
        "filled_slippage_cost": canonical_decimal_string(total_slippage),
        "last_fill_quantity": int(last.payload["quantity_shares"]),
        "last_fill_price": float(Decimal(str(last.payload["fill_price"]))),
        "last_fill_price_decimal": str(last.payload["fill_price"]),
        "last_fill_commission": float(
            Decimal(str(last.payload["commission"]))
        ),
        "last_fill_commission_decimal": str(last.payload["commission"]),
        "last_fill_tax": "0",
        "last_slippage_cost": str(last.payload["slippage_cost"]),
        "last_net_cash_effect": str(last.payload["net_cash_effect"]),
    }
    return order_state_record_from_simulation_order(
        state,
        session_id=last.session_id,
    )


def _journal_with_fill_set(
    source: InMemoryJournalRepository,
    fills: tuple[JournalRecord, ...],
    order_state: JournalRecord,
) -> InMemoryJournalRepository:
    session = source.session(fills[0].session_id)
    assert session is not None
    journal = InMemoryJournalRepository()
    journal.start_session(session)
    for fill in fills:
        journal.append(fill)
    journal.append(order_state)
    return journal


def _replace_payload(record: JournalRecord, **changes: object) -> JournalRecord:
    return JournalRecord(
        record_id=record.record_id,
        session_id=record.session_id,
        kind=record.kind,
        occurred_at=record.occurred_at,
        payload={**record.payload, **changes},
        idempotency_scope=record.idempotency_scope,
        idempotency_key=record.idempotency_key,
        schema_version=record.schema_version,
    )


def test_fill_v3_single_fill_activates_with_complete_record_lineage() -> None:
    draft, journal, _order, fill = _settings_bound_entry(v3=True)

    observed = ExistingPaperFillObserver().observe(draft, journal)
    terminal_evidence = observed.activation.provenance.terminal_evidence
    assert terminal_evidence is not None
    activation = PaperFillThesisBuilder().activate(
        draft,
        fill,
        terminal_evidence=terminal_evidence,
    )

    assert activation.version == "paper-fill-thesis-activation-v2"
    assert activation == observed.activation
    assert activation.provenance.execution_authority is False
    assert activation.provenance.session_id == draft.session_id
    assert activation.provenance.symbol == draft.symbol
    assert activation.provenance.side.value == "BUY"
    assert activation.provenance.quantity_shares == 1_000
    assert [item.fill_record_id for item in activation.provenance.fill_records] == [
        fill.record_id
    ]
    assert [
        item.fill_record_fingerprint for item in activation.provenance.fill_records
    ] == [fill.fingerprint]


def test_fill_v2_remains_an_explicit_settings_bound_compatibility_reader() -> None:
    draft, journal, _order, fill = _settings_bound_entry(v3=False)

    observed = ExistingPaperFillObserver().observe(draft, journal)
    terminal_evidence = observed.activation.provenance.terminal_evidence
    assert terminal_evidence is not None
    activation = PaperFillThesisBuilder().activate(
        draft,
        fill,
        terminal_evidence=terminal_evidence,
    )

    assert fill.kind == LOCAL_PAPER_FILL_V2_KIND
    assert activation == observed.activation
    assert activation.provenance.quantity_shares == 1_000
    assert activation.provenance.fill_records[0].fill_kind == LOCAL_PAPER_FILL_V2_KIND


def test_fill_v3_partial_fills_aggregate_vwap_quantity_and_identity() -> None:
    draft, source, order, base = _settings_bound_entry(v3=True)
    fills = _split_v3_fill(base)
    terminal = _order_state_for_fill_prefix(order, fills, status="FILLED")
    journal = _journal_with_fill_set(source, fills, terminal)
    before = journal.records(draft.session_id)

    observed = ExistingPaperFillObserver().observe(draft, journal)

    assert observed.activation.provenance.quantity_shares == 1_000
    expected_vwap = sum(
        Decimal(str(fill.payload["fill_price"]))
        * int(fill.payload["quantity_shares"])
        for fill in fills
    ) / Decimal("1000")
    assert observed.activation.thesis.entry_reference_price == expected_vwap
    assert observed.activation.thesis.entry_reference_price != Decimal(
        str(fills[0].payload["fill_price"])
    )
    assert observed.activation.thesis.filled_at.value == fills[-1].occurred_at
    assert observed.fill_journal_sequences == (1, 2)
    assert observed.fill_record_ids == tuple(fill.record_id for fill in fills)
    assert observed.fill_record_fingerprints == tuple(
        fill.fingerprint for fill in fills
    )
    assert observed.fill_record_id.startswith("local-paper-fill-aggregate:")
    terminal_evidence = observed.activation.provenance.terminal_evidence
    assert terminal_evidence is not None
    assert terminal_evidence.journal_sequence == 3
    assert terminal_evidence.order_state_record_id == terminal.record_id
    assert terminal_evidence.order_state_record_fingerprint == terminal.fingerprint
    assert journal.records(draft.session_id) == before


def test_fill_v3_partial_prefix_waits_for_terminal_fill_without_mutation() -> None:
    draft, source, order, base = _settings_bound_entry(v3=True)
    first, _second = _split_v3_fill(base)
    partial = _order_state_for_fill_prefix(order, (first,), status="PARTIALLY_FILLED")
    journal = _journal_with_fill_set(source, (first,), partial)
    before = journal.records(draft.session_id)

    with pytest.raises(PaperFillNotObservedError, match="terminally filled"):
        ExistingPaperFillObserver().observe(draft, journal)

    assert journal.records(draft.session_id) == before


def test_fill_v3_exact_duplicate_is_idempotent_but_conflict_fails_closed() -> None:
    draft, source, order, base = _settings_bound_entry(v3=True)
    first, second = _split_v3_fill(base)
    terminal = _order_state_for_fill_prefix(order, (first, second), status="FILLED")
    journal = _journal_with_fill_set(source, (first, second), terminal)
    unique = ExistingPaperFillObserver().observe(draft, journal).activation
    terminal_evidence = unique.provenance.terminal_evidence
    assert terminal_evidence is not None

    duplicate = PaperFillThesisBuilder().activate(
        draft,
        (first, first, second),
        terminal_evidence=terminal_evidence,
    )
    assert duplicate == unique

    conflicting_first = JournalRecord(
        record_id=f"{first.record_id}:conflict",
        session_id=first.session_id,
        kind=first.kind,
        occurred_at=first.occurred_at,
        payload=first.payload,
        idempotency_scope=first.idempotency_scope,
        idempotency_key=first.idempotency_key,
        schema_version=first.schema_version,
    )
    static = StaticJournal(
        (
            JournalAppendResult(first, 1, False),
            JournalAppendResult(conflicting_first, 2, False),
            JournalAppendResult(second, 3, False),
            JournalAppendResult(terminal, 4, False),
        )
    )
    with pytest.raises(PaperFillObservationConflictError, match="conflicting"):
        ExistingPaperFillObserver().observe(draft, static)


def test_fill_v3_cumulative_and_terminal_state_tampering_fail_closed() -> None:
    draft, source, order, base = _settings_bound_entry(v3=True)
    first, second = _split_v3_fill(base)
    tampered_fill = _replace_payload(second, cumulative_order_gross="1")
    terminal = _order_state_for_fill_prefix(order, (first, second), status="FILLED")
    valid_journal = _journal_with_fill_set(source, (first, second), terminal)
    valid = ExistingPaperFillObserver().observe(draft, valid_journal).activation
    terminal_evidence = valid.provenance.terminal_evidence
    assert terminal_evidence is not None

    with pytest.raises(ProjectionRecoveryError, match="invalid local-paper fill"):
        PaperFillThesisBuilder().activate(
            draft,
            (first, tampered_fill),
            terminal_evidence=terminal_evidence,
        )

    tampered_state = _replace_payload(terminal, filled_quantity=999)
    journal = _journal_with_fill_set(source, (first, second), tampered_state)
    with pytest.raises(ProjectionRecoveryError, match="integrity digest mismatch"):
        ExistingPaperFillObserver().observe(draft, journal)


def test_settings_bound_fill_rejects_coerced_monetary_and_provenance_types() -> None:
    draft, journal, _order, v2_fill = _settings_bound_entry(v3=False)
    valid = ExistingPaperFillObserver().observe(draft, journal).activation
    terminal_evidence = valid.provenance.terminal_evidence
    assert terminal_evidence is not None

    for tampered in (
        _replace_payload(v2_fill, provider_identity=123),
        _replace_payload(v2_fill, commission=0),
        _replace_payload(v2_fill, quantity_shares=True),
    ):
        with pytest.raises(ValueError, match="canonical strings|integer"):
            PaperFillThesisBuilder().activate(
                draft,
                tampered,
                terminal_evidence=terminal_evidence,
            )


def test_fill_v3_aggregate_identity_survives_restart_and_exact_replay() -> None:
    draft, source, order, base = _settings_bound_entry(v3=True)
    fills = _split_v3_fill(base)
    terminal = _order_state_for_fill_prefix(order, fills, status="FILLED")
    original_journal = _journal_with_fill_set(source, fills, terminal)
    original = ExistingPaperFillObserver().observe(draft, original_journal)
    with localcontext(Context(prec=6)):
        low_precision = ExistingPaperFillObserver().observe(
            draft,
            original_journal,
        )
    rebuilt = InMemoryJournalRepository()
    session = original_journal.session(draft.session_id)
    assert session is not None
    rebuilt.start_session(session)
    for result in original_journal.records(draft.session_id):
        rebuilt.append(result.record)

    recovered = ExistingPaperFillObserver().observe(draft, rebuilt)

    assert recovered == original
    assert low_precision == original
    assert recovered.activation.activation_id == original.activation.activation_id
    assert recovered.activation.digest == original.activation.digest


def test_settings_bound_builder_rejects_nonterminal_fill_prefix() -> None:
    draft, _source, _order, base = _settings_bound_entry(v3=True)
    first, _second = _split_v3_fill(base)

    with pytest.raises(ValueError, match="terminal completion evidence"):
        PaperFillThesisBuilder().activate(draft, first)


def test_observer_uses_one_immutable_journal_snapshot() -> None:
    draft, _source, order, base = _settings_bound_entry(v3=True)
    fills = _split_v3_fill(base)
    terminal = _order_state_for_fill_prefix(order, fills, status="FILLED")
    first = tuple(
        JournalAppendResult(fill, sequence, False)
        for sequence, fill in enumerate(fills, start=1)
    )
    second = (*first, JournalAppendResult(terminal, 3, False))
    journal = ChangingJournal(first, second)

    with pytest.raises(PaperFillNotObservedError, match="terminally filled"):
        ExistingPaperFillObserver().observe(draft, journal)

    assert journal.read_count == 1


def test_shadow_quantity_must_match_authoritative_fill_aggregate() -> None:
    draft, journal, _order, _fill = _settings_bound_entry(v3=True)
    activation = ExistingPaperFillObserver().observe(draft, journal).activation
    mismatched = replace(shadow_policy(), remaining_quantity_shares=999)

    with pytest.raises(ValueError, match="authoritative fill quantity"):
        mismatched.bind(activation)


def test_terminal_evidence_cannot_diverge_from_aggregate_provenance() -> None:
    draft, journal, _order, _fill = _settings_bound_entry(v3=True)
    provenance = ExistingPaperFillObserver().observe(
        draft,
        journal,
    ).activation.provenance
    terminal = provenance.terminal_evidence
    assert terminal is not None

    with pytest.raises(ValueError, match="Journal sequence must be positive"):
        replace(terminal, journal_sequence=True)

    different_quantity = replace(
        terminal,
        quantity_shares=999,
        filled_quantity_shares=999,
    )
    with pytest.raises(ValueError, match="conflicts with terminal evidence"):
        replace(provenance, terminal_evidence=different_quantity)
