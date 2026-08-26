"""Evidence-only live composition for Trade Management Shadow.

This outer-layer orchestrator consumes results from the canonical market-data
pipeline, injects event-time risk evidence, and persists Shadow observations.
It deliberately has no order, position, simulation, or broker capability.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from market_data.events import EventEnvelope
from market_data.ingestion import IngestResult
from market_data.ingress import (
    AdmissionResult,
    LifecycleMessageFactory,
    MarketMessageFactory,
)
from market_data.pipeline import (
    CanonicalMarketDataPipeline,
    DecisionGateState,
    PipelineProcessResult,
    PipelineProcessStatus,
)
from trading.journal import JournalRepository, JournalSession
from trading.risk import RiskSnapshot
from trading.shadow_evidence_journal import (
    ShadowEvidenceProjection,
    journal_record_for_shadow_decision,
    journal_record_for_shadow_session,
    rebuild_shadow_evidence_projection,
    write_shadow_evidence_checkpoint,
)
from trading.trade_management_shadow import (
    ShadowDecisionConfig,
    ShadowDecisionPipeline,
    ShadowDecisionRecord,
    ShadowDecisionSession,
    ShadowDecisionSnapshot,
)
from runtime.trade_management_shadow_observability import (
    SHADOW_OBSERVABILITY_VERSION,
    ShadowOperationHealth,
    ShadowOperationMetrics,
)


LIVE_SHADOW_OPERATION_VERSION = "trade-management-live-shadow-operation-v1"
LIVE_SHADOW_JOURNAL_MODE = "TRADE_MANAGEMENT_SHADOW"

RiskSnapshotProvider = Callable[[EventEnvelope, IngestResult], RiskSnapshot]


@dataclass(frozen=True)
class LiveShadowFinalization:
    session: ShadowDecisionSession
    projection: ShadowEvidenceProjection


class LiveTradeManagementShadowOperation:
    """Compose canonical ingestion, decision-only Shadow, and evidence Journal."""

    def __init__(
        self,
        *,
        market_pipeline: CanonicalMarketDataPipeline,
        shadow_config: ShadowDecisionConfig,
        risk_snapshot_provider: RiskSnapshotProvider,
        journal: JournalRepository,
        journal_session: JournalSession,
    ) -> None:
        if journal_session.session_id != shadow_config.thesis.draft.session_id:
            raise ValueError("Shadow Journal session must match Thesis session")
        if journal_session.mode != LIVE_SHADOW_JOURNAL_MODE:
            raise ValueError("Shadow Journal session mode is invalid")
        if (
            journal_session.metadata.get("operation_version")
            != LIVE_SHADOW_OPERATION_VERSION
        ):
            raise ValueError("Shadow Journal operation version is invalid")
        if (
            journal_session.metadata.get("execution_authority") is not False
            or journal_session.metadata.get("execution_enabled") is not False
            or journal_session.metadata.get("evidence_only") is not True
        ):
            raise ValueError("live Shadow operation requires evidence-only session")
        self._market_pipeline = market_pipeline
        self._shadow = ShadowDecisionPipeline(shadow_config)
        self._risk_snapshot_provider = risk_snapshot_provider
        self._journal = journal
        self._session_id = journal_session.session_id
        self._started_at = journal_session.started_at
        self._last_observed_at = journal_session.started_at
        self._pending_decisions: list[ShadowDecisionRecord] = []
        self._pending_admissions: deque[tuple[bool, datetime]] = deque()
        self._admitted_message_count = 0
        self._processed_message_count = 0
        self._applied_event_count = 0
        self._rejected_event_count = 0
        self._durable_decision_count = 0
        self._writer_failure_count = 0
        self._recovery_count = 0
        self._last_recovery_seconds: Decimal | None = None
        self._blocked_since: datetime | None = None
        self._health = ShadowOperationHealth.RUNNING
        self._shadow_session: ShadowDecisionSession | None = None
        self._finalization: LiveShadowFinalization | None = None
        journal.start_session(journal_session)

    @property
    def decision_gate(self) -> DecisionGateState:
        return self._market_pipeline.decision_gate

    def submit_market(self, factory: MarketMessageFactory) -> AdmissionResult:
        self._require_open()
        result = self._market_pipeline.submit_market(factory)
        if result.accepted:
            assert isinstance(result.message, EventEnvelope)
            self._pending_admissions.append((True, result.message.received_at))
            self._admitted_message_count += 1
        return result

    def submit_lifecycle(
        self,
        factory: LifecycleMessageFactory,
        *,
        timeout: float = 0,
    ) -> AdmissionResult:
        self._require_open()
        result = self._market_pipeline.submit_lifecycle(factory, timeout=timeout)
        if result.accepted:
            self._pending_admissions.append((False, result.message.occurred_at))
            self._admitted_message_count += 1
        return result

    def process_pending(
        self,
        *,
        occurred_at: datetime,
        max_messages: int | None = None,
    ) -> tuple[PipelineProcessResult, ...]:
        self._require_open()
        if max_messages is not None and max_messages <= 0:
            raise ValueError("max_messages must be positive")
        self._last_observed_at = max(self._last_observed_at, occurred_at)
        self._flush_pending_decisions(observed_at=occurred_at)
        processed: list[PipelineProcessResult] = []
        while max_messages is None or len(processed) < max_messages:
            batch = self._market_pipeline.process_pending(
                occurred_at=occurred_at,
                max_messages=1,
            )
            if not batch:
                break
            result = batch[0]
            if not self._pending_admissions:
                raise RuntimeError("canonical message bypassed live Shadow admission")
            self._pending_admissions.popleft()
            self._processed_message_count += 1
            if result.status is PipelineProcessStatus.MARKET_INGESTED:
                if result.ingest_result is not None and result.ingest_result.projection_applied:
                    self._applied_event_count += 1
                else:
                    self._rejected_event_count += 1
            self._consume_result(result)
            processed.append(result)
            if result.status is PipelineProcessStatus.RECORDER_FAILED:
                break
        return tuple(processed)

    def snapshot(self) -> ShadowDecisionSnapshot:
        return self._shadow.snapshot()

    def observe_applied_market(self, result: PipelineProcessResult) -> None:
        """Consume one result already applied by the owning canonical pipeline.

        Full-session capture owns admission, record-before-ingest, and queue
        ordering.  This seam lets Trade Management observe that exact result
        without creating another market-data pipeline.
        """

        self._require_open()
        if result.status is not PipelineProcessStatus.MARKET_INGESTED:
            raise ValueError("Shadow observation requires a canonical market result")
        if not isinstance(result.message, EventEnvelope):
            raise TypeError("canonical market result requires EventEnvelope")
        if result.ingest_result is None or not result.ingest_result.projection_applied:
            raise ValueError("Shadow observation requires projection-applied evidence")
        observed_at = result.message.received_at
        self._last_observed_at = max(self._last_observed_at, observed_at)
        self._flush_pending_decisions(observed_at=observed_at)
        self._admitted_message_count += 1
        self._processed_message_count += 1
        self._applied_event_count += 1
        self._consume_result(result)

    def retry_pending_evidence(self, *, observed_at: datetime) -> bool:
        """Retry only the current durable append without consuming new input."""

        self._require_open()
        had_pending = bool(self._pending_decisions)
        self._last_observed_at = max(self._last_observed_at, observed_at)
        self._flush_pending_decisions(observed_at=observed_at)
        return had_pending

    def metrics(self, *, observed_at: datetime) -> ShadowOperationMetrics:
        if observed_at.tzinfo is None or observed_at.utcoffset() is None:
            raise ValueError("observed_at must be timezone-aware")
        if observed_at < self._started_at:
            raise ValueError("observed_at cannot precede operation start")
        pending_market_times = tuple(
            admitted_at
            for is_market, admitted_at in self._pending_admissions
            if is_market
        )
        pending_market_age = None
        if pending_market_times:
            if observed_at < pending_market_times[0]:
                raise ValueError("observed_at cannot precede pending market event")
            pending_market_age = _duration_seconds(
                observed_at,
                pending_market_times[0],
            )
        pending_age = None
        if self._pending_decisions:
            pending_at = self._pending_decisions[0].step.market_context.observed_at.value
            if observed_at < pending_at:
                raise ValueError("observed_at cannot precede pending evidence")
            pending_age = _duration_seconds(observed_at, pending_at)
        health = self._health
        if self._finalization is not None:
            health = ShadowOperationHealth.FINALIZED
        elif health is ShadowOperationHealth.RUNNING and self.decision_gate is not DecisionGateState.OPEN:
            health = ShadowOperationHealth.DEGRADED
        shadow = self._shadow.snapshot()
        return ShadowOperationMetrics(
            version=SHADOW_OBSERVABILITY_VERSION,
            session_id=self._session_id,
            observed_at=observed_at,
            health=health,
            admitted_message_count=self._admitted_message_count,
            processed_message_count=self._processed_message_count,
            pending_market_event_count=len(pending_market_times),
            oldest_pending_event_age_seconds=pending_market_age,
            applied_event_count=self._applied_event_count,
            rejected_event_count=self._rejected_event_count,
            decision_record_count=len(shadow.records),
            durable_decision_count=self._durable_decision_count,
            pending_evidence_count=len(self._pending_decisions),
            oldest_pending_age_seconds=pending_age,
            writer_failure_count=self._writer_failure_count,
            recovery_count=self._recovery_count,
            last_recovery_seconds=self._last_recovery_seconds,
            observation_seconds=_duration_seconds(observed_at, self._started_at),
            finalized=self._finalization is not None,
            finalization_persisted=self._finalization is not None,
            parity_status=(
                None
                if self._finalization is None
                else self._finalization.session.parity.status
            ),
            first_divergent_sequence=(
                None
                if self._finalization is None
                else self._finalization.session.parity.first_divergent_sequence
            ),
        )

    def finalize(self, *, observed_at: datetime | None = None) -> LiveShadowFinalization:
        if self._finalization is not None:
            return self._finalization
        if self._pending_admissions:
            raise RuntimeError("cannot finalize with pending canonical messages")
        effective_at = observed_at or self._last_observed_at
        self._flush_pending_decisions(observed_at=effective_at)
        if self._shadow_session is None:
            self._shadow_session = self._shadow.finalize()
        self._begin_writer_attempt(observed_at=effective_at)
        try:
            self._journal.append(
                journal_record_for_shadow_session(self._shadow_session)
            )
            written = write_shadow_evidence_checkpoint(
                self._journal,
                session_id=self._session_id,
            )
            rebuilt = rebuild_shadow_evidence_projection(
                self._journal,
                session_id=self._session_id,
            )
        except Exception:
            self._record_writer_failure(observed_at=effective_at)
            raise
        if rebuilt.digest != written.digest:
            self._record_writer_failure(observed_at=effective_at)
            raise RuntimeError("Shadow evidence checkpoint recovery diverged")
        self._record_writer_recovery(observed_at=effective_at)
        self._finalization = LiveShadowFinalization(
            session=self._shadow_session,
            projection=rebuilt,
        )
        self._health = ShadowOperationHealth.FINALIZED
        return self._finalization

    def _consume_result(self, result: PipelineProcessResult) -> None:
        if result.status is not PipelineProcessStatus.MARKET_INGESTED:
            return
        if not isinstance(result.message, EventEnvelope):
            raise TypeError("MARKET_INGESTED result requires EventEnvelope")
        ingest_result = result.ingest_result
        if ingest_result is None:
            raise ValueError("MARKET_INGESTED result requires IngestResult")
        if not ingest_result.projection_applied:
            return
        risk_snapshot = self._risk_snapshot_provider(result.message, ingest_result)
        if not isinstance(risk_snapshot, RiskSnapshot):
            raise TypeError("risk_snapshot_provider must return RiskSnapshot")
        record = self._shadow.consume(
            result.message,
            risk_snapshot=risk_snapshot,
        )
        if record is not None:
            self._pending_decisions.append(record)
            self._flush_pending_decisions(observed_at=result.message.received_at)

    def _flush_pending_decisions(self, *, observed_at: datetime) -> None:
        while self._pending_decisions:
            record = self._pending_decisions[0]
            self._begin_writer_attempt(observed_at=observed_at)
            try:
                self._journal.append(journal_record_for_shadow_decision(record))
            except Exception:
                self._record_writer_failure(observed_at=observed_at)
                raise
            self._pending_decisions.pop(0)
            self._durable_decision_count += 1
            self._record_writer_recovery(observed_at=observed_at)

    def _begin_writer_attempt(self, *, observed_at: datetime) -> None:
        if self._blocked_since is not None:
            if observed_at < self._blocked_since:
                raise ValueError("writer retry time cannot move backward")
            self._health = ShadowOperationHealth.RECOVERING

    def _record_writer_failure(self, *, observed_at: datetime) -> None:
        self._writer_failure_count += 1
        if self._blocked_since is None:
            self._blocked_since = observed_at
        self._health = ShadowOperationHealth.BLOCKED

    def _record_writer_recovery(self, *, observed_at: datetime) -> None:
        if self._blocked_since is None:
            return
        self._recovery_count += 1
        self._last_recovery_seconds = _duration_seconds(
            observed_at,
            self._blocked_since,
        )
        self._blocked_since = None
        self._health = ShadowOperationHealth.RUNNING

    def _require_open(self) -> None:
        if self._shadow_session is not None:
            raise RuntimeError("live Shadow operation is finalized")


def _duration_seconds(later: datetime, earlier: datetime) -> Decimal:
    delta = later - earlier
    microseconds = (
        delta.days * 86_400_000_000
        + delta.seconds * 1_000_000
        + delta.microseconds
    )
    if microseconds < 0:
        raise ValueError("duration cannot be negative")
    return Decimal(microseconds) / Decimal(1_000_000)
