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
from trading.journal import JournalRepository
from trading.live_entry_thesis_draft import (
    LiveThesisDraftPolicy,
    LiveTradeThesisDraftBuilder,
)
from trading.local_paper import LOCAL_PAPER_FILL_KIND
from trading.paper_thesis_activation import (
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
    """More than one authoritative fill claims the same Thesis draft."""


@dataclass(frozen=True)
class ObservedPaperFillActivation:
    version: str
    fill_journal_sequence: int
    fill_record_id: str
    fill_record_fingerprint: str
    activation: PaperFillThesisActivation

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
        candidates = tuple(
            result
            for result in journal.records(draft.session_id)
            if result.record.kind == LOCAL_PAPER_FILL_KIND
            and result.record.payload.get("command_idempotency_key")
            == correlation_key
        )
        if not candidates:
            raise PaperFillNotObservedError(
                "correlated local-paper BUY fill has not been observed"
            )
        if len(candidates) != 1:
            raise PaperFillObservationConflictError(
                "multiple local-paper fills correlate to one Thesis draft"
            )
        candidate = candidates[0]
        activation = self._builder.activate(draft, candidate.record)
        return ObservedPaperFillActivation(
            version=OPERATIONAL_COMPOSITION_VERSION,
            fill_journal_sequence=candidate.sequence,
            fill_record_id=candidate.record.record_id,
            fill_record_fingerprint=candidate.record.fingerprint,
            activation=activation,
        )


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
