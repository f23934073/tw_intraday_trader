"""Application coordinator for one data-only Trade Management C1 session.

The full-session market capture remains the only canonical ingress pipeline.
This coordinator observes its already-recorded, projection-applied results and
activates Trade Management only after an existing correlated local-paper BUY
fill becomes visible.  It has no fill, order, Position, or broker capability.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from threading import Event
from time import monotonic
from typing import Protocol

from market_data.events import MarketStreamKind
from market_data.journal import JournalStatus, verify_market_event_journal
from market_data.pipeline import (
    CanonicalMarketDataPipeline,
    PipelineProcessResult,
    PipelineProcessStatus,
)
from runtime.clock import Clock
from runtime.trade_management_live_capture import (
    LiveShadowCaptureConfig,
    live_shadow_journal_session,
)
from runtime.trade_management_operational_composition import (
    ExistingPaperFillObserver,
    LiveShadowDecisionPolicy,
    ObservedPaperFillActivation,
    PaperFillNotObservedError,
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
from trading.trade_management import LiveEntryDecision, TradeThesisDraft
from trading.trade_management_shadow import ShadowParityStatus


TRADE_MANAGEMENT_C1_SESSION_VERSION = "trade-management-c1-session-v1"


class C1SessionStatus(StrEnum):
    FINALIZED = "FINALIZED"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    BLOCKED = "BLOCKED"


class FullSessionMarketCapture(Protocol):
    def run(self): ...


@dataclass(frozen=True)
class TradeManagementC1Evidence:
    session_id: str
    status: C1SessionStatus
    provider_identity: str
    market_session_dir: Path
    market_classification: str
    market_journal_sha256: str | None
    market_event_count: int
    market_accepted_count: int
    market_rejected_count: int
    full_market_session_covered: bool
    market_exact_replay_passed: bool
    lost_evidence_count: int
    activation_id: str | None
    decision_count: int
    journal_record_count: int
    pending_evidence_count: int
    writer_failure_count: int
    writer_recovery_count: int
    writer_recovery_seconds: str | None
    parity_status: ShadowParityStatus | None
    recovery_verified: bool
    recovery_digest: str | None
    reasons: tuple[str, ...]
    execution_authority: bool = False
    execution_enabled: bool = False
    evidence_only: bool = True
    production_shadow_gate: str = "NOT_PASSED"
    version: str = TRADE_MANAGEMENT_C1_SESSION_VERSION

    def __post_init__(self) -> None:
        if self.version != TRADE_MANAGEMENT_C1_SESSION_VERSION:
            raise ValueError("unsupported C1 session evidence version")
        if not self.session_id.strip() or not self.provider_identity.strip():
            raise ValueError("C1 evidence identity must not be empty")
        if min(
            self.market_event_count,
            self.market_accepted_count,
            self.market_rejected_count,
            self.lost_evidence_count,
            self.decision_count,
            self.journal_record_count,
            self.pending_evidence_count,
            self.writer_failure_count,
            self.writer_recovery_count,
        ) < 0:
            raise ValueError("C1 evidence counts must not be negative")
        if self.execution_authority or self.execution_enabled or not self.evidence_only:
            raise ValueError("C1 evidence must remain decision-only")
        if self.production_shadow_gate != "NOT_PASSED":
            raise ValueError("one C1 session cannot pass the Production Shadow Gate")
        if self.market_journal_sha256 is not None and (
            len(self.market_journal_sha256) != 64
            or any(
                item not in "0123456789abcdef"
                for item in self.market_journal_sha256
            )
        ):
            raise ValueError("market_journal_sha256 must be a SHA-256 digest")
        if self.status is C1SessionStatus.FINALIZED:
            if (
                not self.full_market_session_covered
                or not self.market_exact_replay_passed
                or self.lost_evidence_count
                or self.activation_id is None
                or self.decision_count <= 0
                or self.pending_evidence_count
                or (
                    self.writer_failure_count > 0
                    and self.writer_recovery_count <= 0
                )
                or self.parity_status is not ShadowParityStatus.MATCHED
                or not self.recovery_verified
            ):
                raise ValueError("FINALIZED C1 evidence requires every single-day gate")

    @property
    def digest(self) -> str:
        value = self.to_dict()
        value.pop("market_session_dir")
        return hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "session_id": self.session_id,
            "status": self.status.value,
            "provider_identity": self.provider_identity,
            "market_session_dir": str(self.market_session_dir.resolve()),
            "market_classification": self.market_classification,
            "market_journal_sha256": self.market_journal_sha256,
            "market_event_count": self.market_event_count,
            "market_accepted_count": self.market_accepted_count,
            "market_rejected_count": self.market_rejected_count,
            "full_market_session_covered": self.full_market_session_covered,
            "market_exact_replay_passed": self.market_exact_replay_passed,
            "lost_evidence_count": self.lost_evidence_count,
            "activation_id": self.activation_id,
            "decision_count": self.decision_count,
            "journal_record_count": self.journal_record_count,
            "pending_evidence_count": self.pending_evidence_count,
            "writer_failure_count": self.writer_failure_count,
            "writer_recovery_count": self.writer_recovery_count,
            "writer_recovery_seconds": self.writer_recovery_seconds,
            "parity_status": (
                None if self.parity_status is None else self.parity_status.value
            ),
            "recovery_verified": self.recovery_verified,
            "recovery_digest": self.recovery_digest,
            "reasons": list(self.reasons),
            "execution_authority": self.execution_authority,
            "execution_enabled": self.execution_enabled,
            "evidence_only": self.evidence_only,
            "production_shadow_gate": self.production_shadow_gate,
        }


class TradeManagementC1SessionCoordinator:
    """Observe the canonical session and activate Shadow after an existing fill."""

    def __init__(
        self,
        *,
        decision: LiveEntryDecision,
        draft_policy: LiveThesisDraftPolicy,
        fill_journal: JournalRepository,
        evidence_journal: JournalRepository,
        shadow_policy: LiveShadowDecisionPolicy,
        risk_snapshot_provider: RiskSnapshotProvider,
        capture_config: LiveShadowCaptureConfig,
        clock: Clock,
        draft_builder: LiveTradeThesisDraftBuilder | None = None,
        fill_observer: ExistingPaperFillObserver | None = None,
        journal_recovery_timeout_seconds: float = 30,
        journal_recovery_retry_seconds: float = 0.25,
    ) -> None:
        if fill_journal is evidence_journal:
            raise ValueError(
                "fill observation and Shadow evidence require separate authorities"
            )
        if journal_recovery_timeout_seconds <= 0:
            raise ValueError("journal recovery timeout must be positive")
        if journal_recovery_retry_seconds <= 0:
            raise ValueError("journal recovery retry interval must be positive")
        self._draft = (draft_builder or LiveTradeThesisDraftBuilder()).build(
            decision,
            draft_policy,
        )
        if self._draft.session_id != capture_config.session_id:
            raise ValueError("entry decision session does not match C1 capture")
        if self._draft.symbol != capture_config.symbol:
            raise ValueError("entry decision symbol does not match C1 capture")
        self._fill_journal = fill_journal
        self._evidence_journal = evidence_journal
        self._shadow_policy = shadow_policy
        self._risk_snapshot_provider = risk_snapshot_provider
        self._capture_config = capture_config
        self._clock = clock
        self._fill_observer = fill_observer or ExistingPaperFillObserver()
        self._journal_recovery_timeout_seconds = journal_recovery_timeout_seconds
        self._journal_recovery_retry_seconds = journal_recovery_retry_seconds
        self._market_pipeline: CanonicalMarketDataPipeline | None = None
        self._observed_fill: ObservedPaperFillActivation | None = None
        self._operation: LiveTradeManagementShadowOperation | None = None
        self._last_fill_poll_at: datetime | None = None

    @property
    def draft(self) -> TradeThesisDraft:
        return self._draft

    def bind_market_pipeline(self, pipeline: CanonicalMarketDataPipeline) -> None:
        if self._market_pipeline is not None and self._market_pipeline is not pipeline:
            raise RuntimeError("C1 coordinator cannot change canonical pipelines")
        self._market_pipeline = pipeline

    def observe_canonical_result(self, result: PipelineProcessResult) -> None:
        if (
            result.status is not PipelineProcessStatus.MARKET_INGESTED
            or result.ingest_result is None
            or not result.ingest_result.projection_applied
            or result.message.stream_kind is not MarketStreamKind.TICK
        ):
            return
        if self._operation is not None:
            self._observe_with_backpressure(result)
            return
        if result.message.event_at < self._draft.signal_at.value:
            return
        if (
            self._last_fill_poll_at is not None
            and (
                result.message.received_at - self._last_fill_poll_at
            ).total_seconds() < 0.25
        ):
            return
        self._last_fill_poll_at = result.message.received_at
        try:
            observed = self._fill_observer.observe(
                self._draft,
                self._fill_journal,
            )
        except PaperFillNotObservedError:
            return
        if self._market_pipeline is None:
            raise RuntimeError("canonical market pipeline is not bound")
        activation = observed.activation
        operation = LiveTradeManagementShadowOperation(
            market_pipeline=self._market_pipeline,
            shadow_config=self._shadow_policy.bind(activation),
            risk_snapshot_provider=self._risk_snapshot_provider,
            journal=self._evidence_journal,
            journal_session=live_shadow_journal_session(
                self._capture_config,
                activation,
            ),
        )
        self._observed_fill = observed
        self._operation = operation
        if result.message.event_at >= activation.thesis.filled_at.value:
            self._observe_with_backpressure(result)

    def _observe_with_backpressure(self, result: PipelineProcessResult) -> None:
        assert self._operation is not None
        original_error: Exception | None = None
        try:
            self._operation.observe_applied_market(result)
            return
        except Exception as error:
            original_error = error
            metrics = self._operation.metrics(observed_at=self._clock.now())
            if metrics.pending_evidence_count <= 0:
                raise
        deadline = monotonic() + self._journal_recovery_timeout_seconds
        while monotonic() < deadline:
            Event().wait(self._journal_recovery_retry_seconds)
            try:
                self._operation.retry_pending_evidence(
                    observed_at=self._clock.now()
                )
                return
            except Exception:
                continue
        raise RuntimeError("SHADOW_JOURNAL_RECOVERY_TIMEOUT") from original_error

    def run(self, capture: FullSessionMarketCapture) -> TradeManagementC1Evidence:
        result = capture.run()
        facts = _market_capture_facts(result)
        reasons = list(facts["reasons"])
        if not result.qualified:
            reasons.extend(result.reasons)
        status = C1SessionStatus.BLOCKED
        finalization = None
        if not reasons and self._operation is None:
            status = C1SessionStatus.INSUFFICIENT_EVIDENCE
            reasons.append("LOCAL_PAPER_BUY_FILL_NOT_OBSERVED")
        elif not reasons and not self._operation.snapshot().records:
            status = C1SessionStatus.INSUFFICIENT_EVIDENCE
            reasons.append("NO_POST_FILL_SHADOW_DECISIONS")
        elif not reasons:
            finalization, finalization_error = self._finalize_with_recovery()
            if finalization is None:
                reasons.append(
                    "FINALIZATION_RECOVERY_TIMEOUT:"
                    f"{type(finalization_error).__name__}:{finalization_error}"
                )
            elif finalization.session.parity.status is ShadowParityStatus.MATCHED:
                status = C1SessionStatus.FINALIZED
            else:
                reasons.append("HISTORICAL_REPLAY_DIVERGED")

        activation_id = (
            None
            if self._observed_fill is None
            else self._observed_fill.activation.activation_id
        )
        decision_count = (
            0 if self._operation is None else len(self._operation.snapshot().records)
        )
        metrics = (
            None
            if self._operation is None
            else self._operation.metrics(observed_at=self._clock.now())
        )
        journal_count = (
            0
            if metrics is None
            else metrics.durable_decision_count + (1 if finalization else 0)
        )
        recovery_digest = (
            None if finalization is None else finalization.projection.digest
        )
        recovery_verified = finalization is not None and recovery_digest is not None
        pending_evidence_count = (
            0 if metrics is None else metrics.pending_evidence_count
        )
        writer_failure_count = 0 if metrics is None else metrics.writer_failure_count
        writer_recovery_count = 0 if metrics is None else metrics.recovery_count
        return TradeManagementC1Evidence(
            session_id=self._draft.session_id,
            status=status,
            provider_identity=self._capture_config.provider.environment_identity,
            market_session_dir=result.session_dir,
            market_classification=result.classification,
            market_journal_sha256=facts["market_journal_sha256"],
            market_event_count=int(facts["event_count"]),
            market_accepted_count=int(facts["accepted_count"]),
            market_rejected_count=int(facts["rejected_count"]),
            full_market_session_covered=bool(facts["full_covered"]),
            market_exact_replay_passed=result.exact_replay_passed,
            lost_evidence_count=int(facts["lost_evidence_count"]),
            activation_id=activation_id,
            decision_count=decision_count,
            journal_record_count=journal_count,
            pending_evidence_count=pending_evidence_count,
            writer_failure_count=writer_failure_count,
            writer_recovery_count=writer_recovery_count,
            writer_recovery_seconds=(
                None
                if metrics is None or metrics.last_recovery_seconds is None
                else str(metrics.last_recovery_seconds)
            ),
            parity_status=(
                None if finalization is None else finalization.session.parity.status
            ),
            recovery_verified=recovery_verified,
            recovery_digest=recovery_digest,
            reasons=tuple(sorted(set(reasons))),
        )

    def _finalize_with_recovery(self):
        assert self._operation is not None
        deadline = monotonic() + self._journal_recovery_timeout_seconds
        last_error: Exception | None = None
        while True:
            try:
                return (
                    self._operation.finalize(observed_at=self._clock.now()),
                    None,
                )
            except Exception as error:
                last_error = error
            if monotonic() >= deadline:
                return None, last_error
            Event().wait(self._journal_recovery_retry_seconds)


def _market_capture_facts(result) -> dict[str, object]:
    verification = verify_market_event_journal(result.session_dir)
    reasons: list[str] = []
    if not verification.valid or verification.manifest is None:
        reasons.append("MARKET_JOURNAL_INVALID")
        return {
            "event_count": verification.event_count,
            "accepted_count": verification.accepted_count,
            "rejected_count": verification.rejected_count,
            "lost_evidence_count": 0,
            "market_journal_sha256": None,
            "full_covered": False,
            "reasons": reasons,
        }
    report = {}
    if result.report_path is not None and result.report_path.exists():
        report = json.loads(result.report_path.read_text(encoding="utf-8"))
    bootstrap_path = result.session_dir / "bootstrap_snapshot.json"
    bootstrap = (
        json.loads(bootstrap_path.read_text(encoding="utf-8"))
        if bootstrap_path.exists()
        else {}
    )
    capture = dict(report.get("capture", {}))
    preboundary = int(capture.get("preboundary_event_count", 0))
    calendar = dict(bootstrap.get("calendar", {}))
    subscriptions = tuple(bootstrap.get("subscriptions", ()))
    shutdown = dict(verification.manifest.get("shutdown", {}))
    try:
        scheduled_open = datetime.fromisoformat(str(calendar["scheduled_open"]))
        scheduled_close = datetime.fromisoformat(str(calendar["scheduled_close"]))
        finalized_at = datetime.fromisoformat(str(shutdown["finalized_at"]))
        acked_before_open = bool(subscriptions) and all(
            item.get("state") == "ACKED"
            and datetime.fromisoformat(str(item["effective_at"])) <= scheduled_open
            for item in subscriptions
        )
        full_covered = (
            verification.manifest.get("status") == JournalStatus.FINALIZED.value
            and shutdown.get("queue_drained") is True
            and acked_before_open
            and finalized_at >= scheduled_close
            and preboundary == 0
            and result.exact_replay_passed
        )
    except (KeyError, TypeError, ValueError):
        full_covered = False
    if not full_covered:
        reasons.append("FULL_MARKET_SESSION_NOT_COVERED")
    if preboundary:
        reasons.append("PREBOUNDARY_MARKET_EVENTS_LOST")
    if not result.exact_replay_passed:
        reasons.append("MARKET_EXACT_REPLAY_FAILED")
    return {
        "event_count": verification.event_count,
        "accepted_count": verification.accepted_count,
        "rejected_count": verification.rejected_count,
        "lost_evidence_count": preboundary,
        "market_journal_sha256": verification.manifest.get("sha256"),
        "full_covered": full_covered,
        "reasons": reasons,
    }
