"""Deterministic record-before-ingest canonical market-data pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum

from market_data.events import EventEnvelope
from market_data.health import DataHealth, DataHealthReason, DataHealthState
from market_data.ingestion import IngestResult, MarketDataIngestor
from market_data.ingress import (
    AdmissionResult,
    BoundedIngressQueue,
    IngressMessage,
    LifecycleMessageFactory,
    MarketMessageFactory,
)
from market_data.recording import MarketEventRecorder


class DecisionGateState(StrEnum):
    OPEN = "OPEN"
    BLOCK_NEW_ENTRY = "BLOCK_NEW_ENTRY"


class PipelineProcessStatus(StrEnum):
    MARKET_INGESTED = "MARKET_INGESTED"
    LIFECYCLE_RECORDED = "LIFECYCLE_RECORDED"
    RECORDER_FAILED = "RECORDER_FAILED"


@dataclass(frozen=True)
class PipelineProcessResult:
    status: PipelineProcessStatus
    message: IngressMessage
    record_index: int | None
    ingest_result: IngestResult | None = None
    error: str | None = None


class CanonicalMarketDataPipeline:
    """Synchronous slice; runtime ownership and worker wiring come later."""

    def __init__(
        self,
        *,
        queue: BoundedIngressQueue,
        recorder: MarketEventRecorder,
        ingestor: MarketDataIngestor,
        health: DataHealth,
    ) -> None:
        self._queue = queue
        self._recorder = recorder
        self._ingestor = ingestor
        self._health = health
        self._next_record_index = 0

    @property
    def decision_gate(self) -> DecisionGateState:
        return (
            DecisionGateState.OPEN
            if self._health.state is DataHealthState.HEALTHY
            else DecisionGateState.BLOCK_NEW_ENTRY
        )

    def submit_market(self, factory: MarketMessageFactory) -> AdmissionResult:
        return self._queue.admit_market(factory)

    def submit_lifecycle(
        self,
        factory: LifecycleMessageFactory,
        *,
        timeout: float = 0,
    ) -> AdmissionResult:
        return self._queue.admit_lifecycle(factory, timeout=timeout)

    def process_pending(
        self,
        *,
        occurred_at: datetime,
        max_messages: int | None = None,
    ) -> tuple[PipelineProcessResult, ...]:
        if max_messages is not None and max_messages <= 0:
            raise ValueError("max_messages must be positive")
        results: list[PipelineProcessResult] = []
        while max_messages is None or len(results) < max_messages:
            message = self._queue.get(occurred_at=occurred_at)
            if message is None:
                break
            result = self._process_message(message, occurred_at=occurred_at)
            results.append(result)
            if result.status is PipelineProcessStatus.RECORDER_FAILED:
                break
        return tuple(results)

    def _process_message(
        self,
        message: IngressMessage,
        *,
        occurred_at: datetime,
    ) -> PipelineProcessResult:
        record_index = self._next_record_index
        try:
            if isinstance(message, EventEnvelope):
                self._recorder.record_market(
                    record_index=record_index,
                    envelope=message,
                )
            else:
                self._recorder.record_lifecycle(
                    record_index=record_index,
                    message=message,
                )
        except Exception as error:
            return self._recorder_failure(
                message,
                occurred_at=occurred_at,
                record_index=None,
                ingest_result=None,
                error=error,
            )

        self._next_record_index += 1
        if not isinstance(message, EventEnvelope):
            return PipelineProcessResult(
                PipelineProcessStatus.LIFECYCLE_RECORDED,
                message,
                record_index,
            )

        ingest_result = self._ingestor.ingest(message)
        try:
            self._recorder.record_disposition(
                record_index=record_index,
                result=ingest_result,
            )
        except Exception as error:
            return self._recorder_failure(
                message,
                occurred_at=occurred_at,
                record_index=record_index,
                ingest_result=ingest_result,
                error=error,
            )
        return PipelineProcessResult(
            PipelineProcessStatus.MARKET_INGESTED,
            message,
            record_index,
            ingest_result,
        )

    def _recorder_failure(
        self,
        message: IngressMessage,
        *,
        occurred_at: datetime,
        record_index: int | None,
        ingest_result: IngestResult | None,
        error: Exception,
    ) -> PipelineProcessResult:
        self._queue.close_all_admission()
        failure_at = max(occurred_at, self._health.snapshot().as_of)
        self._health.record_invalid(
            DataHealthReason.RECORDER_FAILURE,
            occurred_at=failure_at,
        )
        return PipelineProcessResult(
            PipelineProcessStatus.RECORDER_FAILED,
            message,
            record_index,
            ingest_result,
            f"{type(error).__name__}: {error}",
        )
