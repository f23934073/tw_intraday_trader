"""Observe/connect/activate composition for live Trade Management Shadow.

The composition observes an existing local-paper BUY fill, reuses the frozen
PaperFillThesisBuilder, and wires the activated Thesis to evidence-only Shadow.
It cannot create a fill, submit an order, mutate a Position, or reach a broker.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from market_data.pipeline import CanonicalMarketDataPipeline
from runtime.clock import Clock
from runtime.trade_management_live_capture import (
    DataOnlyMarketStream,
    LiveShadowCaptureConfig,
    LiveShadowCaptureRunner,
    live_shadow_journal_session,
)
from runtime.trade_management_shadow import (
    LiveTradeManagementShadowOperation,
    RiskSnapshotProvider,
)
from trading.journal import JournalAppendResult, JournalRepository
from trading.live_entry_thesis_draft import (
    LiveThesisDraftPolicy,
    LiveTradeThesisDraftBuilder,
)
from trading.local_paper import (
    LOCAL_PAPER_FILL_KIND,
    LOCAL_PAPER_FILL_V2_KIND,
    LOCAL_PAPER_FILL_V3_KIND,
    LOCAL_PAPER_ORDER_STATE_KIND,
    LocalPaperSide,
    latest_local_paper_order_states,
)
from trading.paper_thesis_activation import (
    PAPER_FILL_TERMINAL_EVIDENCE_VERSION,
    PaperFillAggregationConflictError,
    PaperFillTerminalEvidence,
    PaperFillThesisActivation,
    PaperFillThesisBuilder,
    paper_thesis_entry_idempotency_key,
)
from trading.risk import RiskPolicy
from trading.trade_management import LiveEntryDecision, TradeThesisDraft
from trading.trade_management_shadow import ShadowDecisionConfig


OPERATIONAL_COMPOSITION_VERSION = "trade-management-operational-composition-v1"


class PaperFillNotObservedError(LookupError):
    """No authoritative correlated local-paper BUY fill is available yet."""


class PaperFillObservationConflictError(ValueError):
    """Correlated records cannot prove one authoritative Thesis fill."""


@dataclass(frozen=True)
class _ReadOnlyJournalSnapshot:
    results: tuple[JournalAppendResult, ...]

    def records(
        self,
        session_id: str,
        *,
        after_sequence: int = 0,
    ) -> tuple[JournalAppendResult, ...]:
        return tuple(
            result
            for result in self.results
            if result.record.session_id == session_id
            and result.sequence > after_sequence
        )


@dataclass(frozen=True)
class ObservedPaperFillActivation:
    version: str
    fill_journal_sequence: int
    fill_record_id: str
    fill_record_fingerprint: str
    activation: PaperFillThesisActivation
    fill_journal_sequences: tuple[int, ...] = ()
    fill_record_ids: tuple[str, ...] = ()
    fill_record_fingerprints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.version != OPERATIONAL_COMPOSITION_VERSION:
            raise ValueError("unsupported operational composition version")
        if self.fill_journal_sequence <= 0:
            raise ValueError("fill_journal_sequence must be positive")
        provenance = self.activation.provenance
        if self.fill_record_id != provenance.fill_record_id:
            raise ValueError("observed fill identity does not match activation")
        if self.fill_record_fingerprint != provenance.fill_record_fingerprint:
            raise ValueError("observed fill fingerprint does not match activation")
        if not self.fill_journal_sequences or any(
            sequence <= 0 for sequence in self.fill_journal_sequences
        ):
            raise ValueError("observed fill Journal sequences must be positive")
        if self.fill_journal_sequence != self.fill_journal_sequences[-1]:
            raise ValueError("observed fill Journal head does not match lineage")
        if self.fill_journal_sequences != tuple(sorted(self.fill_journal_sequences)):
            raise ValueError("observed fill Journal sequences are not ordered")
        expected_record_ids = (
            tuple(record.fill_record_id for record in provenance.fill_records)
            if provenance.fill_records
            else (provenance.fill_record_id,)
        )
        expected_fingerprints = (
            tuple(
                record.fill_record_fingerprint
                for record in provenance.fill_records
            )
            if provenance.fill_records
            else (provenance.fill_record_fingerprint,)
        )
        if self.fill_record_ids != expected_record_ids:
            raise ValueError("observed fill record ids do not match activation lineage")
        if self.fill_record_fingerprints != expected_fingerprints:
            raise ValueError(
                "observed fill fingerprints do not match activation lineage"
            )
        if len(self.fill_journal_sequences) != len(expected_record_ids):
            raise ValueError("observed fill Journal lineage is incomplete")
        if (
            provenance.terminal_evidence is not None
            and provenance.terminal_evidence.journal_sequence
            <= self.fill_journal_sequence
        ):
            raise ValueError("terminal order-state evidence must follow fill lineage")


class ExistingPaperFillObserver:
    """Read one immutable correlated fill without creating or modifying facts."""

    __slots__ = ("_builder",)

    def __init__(self, builder: PaperFillThesisBuilder | None = None) -> None:
        self._builder = builder or PaperFillThesisBuilder()

    def observe(
        self,
        draft: TradeThesisDraft,
        journal: JournalRepository,
    ) -> ObservedPaperFillActivation:
        correlation_key = paper_thesis_entry_idempotency_key(draft)
        snapshot = journal.records(draft.session_id)
        candidates = tuple(
            result
            for result in snapshot
            if result.record.kind
            in {
                LOCAL_PAPER_FILL_KIND,
                LOCAL_PAPER_FILL_V2_KIND,
                LOCAL_PAPER_FILL_V3_KIND,
            }
            and result.record.payload.get("command_idempotency_key")
            == correlation_key
        )
        if not candidates:
            raise PaperFillNotObservedError(
                "correlated local-paper BUY fill has not been observed"
            )
        if all(
            candidate.record.kind == LOCAL_PAPER_FILL_KIND
            for candidate in candidates
        ):
            if len(candidates) != 1:
                raise PaperFillObservationConflictError(
                    "multiple legacy local-paper fills correlate to one Thesis draft"
                )
            candidate = candidates[0]
            activation = self._builder.activate(draft, candidate.record)
            return ObservedPaperFillActivation(
                version=OPERATIONAL_COMPOSITION_VERSION,
                fill_journal_sequence=candidate.sequence,
                fill_record_id=candidate.record.record_id,
                fill_record_fingerprint=candidate.record.fingerprint,
                activation=activation,
                fill_journal_sequences=(candidate.sequence,),
                fill_record_ids=(candidate.record.record_id,),
                fill_record_fingerprints=(candidate.record.fingerprint,),
            )
        if any(
            candidate.record.kind == LOCAL_PAPER_FILL_KIND
            for candidate in candidates
        ):
            raise PaperFillObservationConflictError(
                "conflicting legacy and settings-bound local-paper fills"
            )
        order_ids = {
            candidate.record.payload.get("order_id")
            for candidate in candidates
            if isinstance(candidate.record.payload.get("order_id"), str)
            and str(candidate.record.payload["order_id"]).strip()
        }
        if len(order_ids) != 1 or any(
            candidate.record.payload.get("order_id") not in order_ids
            for candidate in candidates
        ):
            raise PaperFillObservationConflictError(
                "conflicting local-paper fill order identity"
            )
        terminal_evidence = self._terminal_evidence(
            draft=draft,
            snapshot=snapshot,
            order_id=str(next(iter(order_ids))),
            correlation_key=correlation_key,
            fill_head_sequence=max(candidate.sequence for candidate in candidates),
        )
        try:
            activation = self._builder.activate(
                draft,
                tuple(candidate.record for candidate in candidates),
                terminal_evidence=terminal_evidence,
            )
        except PaperFillAggregationConflictError as error:
            raise PaperFillObservationConflictError(str(error)) from error
        selected_candidates = tuple(
            min(
                (
                    candidate
                    for candidate in candidates
                    if candidate.record.record_id == lineage.fill_record_id
                    and candidate.record.fingerprint
                    == lineage.fill_record_fingerprint
                ),
                key=lambda candidate: candidate.sequence,
            )
            for lineage in activation.provenance.fill_records
        )
        return ObservedPaperFillActivation(
            version=OPERATIONAL_COMPOSITION_VERSION,
            fill_journal_sequence=selected_candidates[-1].sequence,
            fill_record_id=activation.provenance.fill_record_id,
            fill_record_fingerprint=activation.provenance.fill_record_fingerprint,
            activation=activation,
            fill_journal_sequences=tuple(
                candidate.sequence for candidate in selected_candidates
            ),
            fill_record_ids=tuple(
                candidate.record.record_id for candidate in selected_candidates
            ),
            fill_record_fingerprints=tuple(
                candidate.record.fingerprint for candidate in selected_candidates
            ),
        )

    @staticmethod
    def _terminal_evidence(
        *,
        draft: TradeThesisDraft,
        snapshot: tuple[JournalAppendResult, ...],
        order_id: str,
        correlation_key: str,
        fill_head_sequence: int,
    ) -> PaperFillTerminalEvidence:
        states = tuple(
            state
            for state in latest_local_paper_order_states(
                _ReadOnlyJournalSnapshot(snapshot),
                session_id=draft.session_id,
                require_integrity=True,
            )
            if state.get("order_id") == order_id
        )
        if not states or states[0].get("status") != "FILLED":
            raise PaperFillNotObservedError(
                "correlated local-paper BUY order is not terminally filled"
            )
        state = states[0]
        expected_values = {
            "idempotency_key": correlation_key,
            "symbol": draft.symbol,
            "side": "BUY",
        }
        if any(state.get(field) != value for field, value in expected_values.items()):
            raise PaperFillObservationConflictError(
                "conflicting terminal local-paper order state"
            )
        terminal_result = next(
            (
                result
                for result in reversed(snapshot)
                if result.record.kind == LOCAL_PAPER_ORDER_STATE_KIND
                and result.record.payload.get("order_id") == order_id
            ),
            None,
        )
        if terminal_result is None or terminal_result.sequence <= fill_head_sequence:
            raise PaperFillObservationConflictError(
                "terminal order-state evidence does not follow fill lineage"
            )
        if state.get("updated_at") != terminal_result.record.occurred_at.isoformat():
            raise PaperFillObservationConflictError(
                "conflicting terminal order-state timestamp"
            )
        integers: dict[str, int] = {}
        for field_name in (
            "quantity_shares",
            "filled_quantity",
            "remaining_quantity",
            "fill_sequence",
        ):
            value = state.get(field_name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise PaperFillObservationConflictError(
                    "terminal local-paper order state quantities are not integers"
                )
            integers[field_name] = value
        try:
            return PaperFillTerminalEvidence(
                version=PAPER_FILL_TERMINAL_EVIDENCE_VERSION,
                journal_sequence=terminal_result.sequence,
                order_state_record_id=terminal_result.record.record_id,
                order_state_record_fingerprint=terminal_result.record.fingerprint,
                occurred_at=terminal_result.record.occurred_at.isoformat(),
                session_id=draft.session_id,
                order_id=order_id,
                command_idempotency_key=correlation_key,
                symbol=draft.symbol,
                side=LocalPaperSide(str(state["side"])),
                quantity_shares=integers["quantity_shares"],
                filled_quantity_shares=integers["filled_quantity"],
                remaining_quantity_shares=integers["remaining_quantity"],
                fill_sequence=integers["fill_sequence"],
                status=str(state["status"]),
            )
        except ValueError as error:
            raise PaperFillObservationConflictError(
                "conflicting terminal local-paper order state"
            ) from error


@dataclass(frozen=True)
class LiveShadowDecisionPolicy:
    exit_policy_version: str
    risk_policy: RiskPolicy
    volume_baseline_shares: Decimal
    shares_per_lot: int
    remaining_quantity_shares: int
    fill_model_version: str
    code_identity: str

    def bind(self, activation: PaperFillThesisActivation) -> ShadowDecisionConfig:
        if self.remaining_quantity_shares != activation.provenance.quantity_shares:
            raise ValueError(
                "Shadow remaining quantity must match authoritative fill quantity"
            )
        return ShadowDecisionConfig(
            thesis=activation.thesis,
            exit_policy_version=self.exit_policy_version,
            risk_policy=self.risk_policy,
            volume_baseline_shares=self.volume_baseline_shares,
            shares_per_lot=self.shares_per_lot,
            remaining_quantity_shares=self.remaining_quantity_shares,
            fill_model_version=self.fill_model_version,
            code_identity=self.code_identity,
        )


@dataclass(frozen=True)
class LiveTradeManagementComposition:
    version: str
    decision: LiveEntryDecision
    draft: TradeThesisDraft
    observed_fill: ObservedPaperFillActivation
    shadow_config: ShadowDecisionConfig
    operation: LiveTradeManagementShadowOperation
    runner: LiveShadowCaptureRunner

    def __post_init__(self) -> None:
        if self.version != OPERATIONAL_COMPOSITION_VERSION:
            raise ValueError("unsupported operational composition version")
        if self.draft.decision_id != self.decision.decision_id:
            raise ValueError("composition draft does not match entry decision")
        if self.observed_fill.activation.thesis.draft != self.draft:
            raise ValueError("composition activation does not match Thesis draft")
        if self.shadow_config.thesis != self.observed_fill.activation.thesis:
            raise ValueError("Shadow config does not use activated Thesis")


class LiveTradeManagementOperationalComposer:
    """Wire existing contracts while keeping fill and evidence authorities split."""

    __slots__ = ("_draft_builder", "_fill_observer")

    def __init__(
        self,
        *,
        draft_builder: LiveTradeThesisDraftBuilder | None = None,
        fill_observer: ExistingPaperFillObserver | None = None,
    ) -> None:
        self._draft_builder = draft_builder or LiveTradeThesisDraftBuilder()
        self._fill_observer = fill_observer or ExistingPaperFillObserver()

    def compose(
        self,
        *,
        decision: LiveEntryDecision,
        draft_policy: LiveThesisDraftPolicy,
        fill_journal: JournalRepository,
        evidence_journal: JournalRepository,
        shadow_policy: LiveShadowDecisionPolicy,
        market_pipeline: CanonicalMarketDataPipeline,
        risk_snapshot_provider: RiskSnapshotProvider,
        capture_config: LiveShadowCaptureConfig,
        stream: DataOnlyMarketStream,
        clock: Clock,
    ) -> LiveTradeManagementComposition:
        if fill_journal is evidence_journal:
            raise ValueError(
                "fill observation and Shadow evidence require separate Journal authorities"
            )
        draft = self._draft_builder.build(decision, draft_policy)
        observed = self._fill_observer.observe(draft, fill_journal)
        activation = observed.activation
        shadow_config = shadow_policy.bind(activation)
        operation = LiveTradeManagementShadowOperation(
            market_pipeline=market_pipeline,
            shadow_config=shadow_config,
            risk_snapshot_provider=risk_snapshot_provider,
            journal=evidence_journal,
            journal_session=live_shadow_journal_session(
                capture_config,
                activation,
            ),
        )
        runner = LiveShadowCaptureRunner(
            config=capture_config,
            activation=activation,
            stream=stream,
            operation=operation,
            clock=clock,
        )
        return LiveTradeManagementComposition(
            version=OPERATIONAL_COMPOSITION_VERSION,
            decision=decision,
            draft=draft,
            observed_fill=observed,
            shadow_config=shadow_config,
            operation=operation,
            runner=runner,
        )
