"""Data-only callback bridge for one activated Trade Management Shadow session.

The runner accepts an already-audited PaperFillThesisActivation and an already
composed live Shadow operation.  It owns market-data callback admission and
session evidence only; it cannot create a Thesis, a fill, an order, or a broker
action.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, replace
from datetime import datetime
from threading import Event, RLock
from typing import Protocol

from market_data.events import EventEnvelope
from market_data.ingress import AdmissionStatus, LifecycleIngressMessage
from market_data.momentum_stream import (
    LifecycleEventHandler,
    MarketEventHandler,
    StreamLifecycleEvent,
    StreamLifecycleEventType,
)
from runtime.clock import Clock
from runtime.trade_management_shadow import (
    LIVE_SHADOW_JOURNAL_MODE,
    LIVE_SHADOW_OPERATION_VERSION,
    LiveShadowFinalization,
    LiveTradeManagementShadowOperation,
)
from trading.journal import JournalSession
from trading.paper_thesis_activation import PaperFillThesisActivation


LIVE_SHADOW_CAPTURE_VERSION = "trade-management-live-capture-v1"


class DataOnlyMarketStream(Protocol):
    @property
    def environment_identity(self) -> str: ...

    @property
    def callback_errors(self) -> tuple[str, ...]: ...

    def start(
        self,
        event_handler: MarketEventHandler,
        lifecycle_handler: LifecycleEventHandler,
    ) -> None: ...

    def request_subscribe(self, symbol: str) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class LiveShadowProviderIdentity:
    provider: str
    sdk_version: str
    simulation: bool
    connection_session_id: str

    def __post_init__(self) -> None:
        for value, field_name in (
            (self.provider, "provider"),
            (self.sdk_version, "sdk_version"),
            (self.connection_session_id, "connection_session_id"),
        ):
            if not value.strip():
                raise ValueError(f"{field_name} must not be empty")

    @property
    def environment_identity(self) -> str:
        return (
            f"{self.provider}:{self.sdk_version}:"
            f"simulation={str(self.simulation).lower()}"
        )


@dataclass(frozen=True)
class LiveShadowCaptureConfig:
    session_id: str
    symbol: str
    provider: LiveShadowProviderIdentity
    scheduled_open: datetime
    scheduled_close: datetime
    subscribe_ack_timeout_seconds: float = 30
    execution_enabled: bool = False
    evidence_only: bool = True

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("session_id must not be empty")
        if self.symbol != self.symbol.strip().upper() or not self.symbol:
            raise ValueError("symbol must be normalized")
        for value, field_name in (
            (self.scheduled_open, "scheduled_open"),
            (self.scheduled_close, "scheduled_close"),
        ):
            if value.tzinfo is None or value.utcoffset() is None:
                raise ValueError(f"{field_name} must be timezone-aware")
        if self.scheduled_close <= self.scheduled_open:
            raise ValueError("scheduled_close must follow scheduled_open")
        if self.scheduled_open.date() != self.scheduled_close.date():
            raise ValueError("capture window must remain within one market date")
        if self.subscribe_ack_timeout_seconds <= 0:
            raise ValueError("subscribe ACK timeout must be positive")
        if self.execution_enabled or not self.evidence_only:
            raise ValueError("live Shadow capture must remain evidence-only")


@dataclass(frozen=True)
class LiveShadowCaptureEvidence:
    version: str
    session_id: str
    activation_id: str
    provider: LiveShadowProviderIdentity
    shadow_started_at: datetime
    shadow_ended_at: datetime
    pre_ack_market_event_count: int
    full_market_session_covered: bool
    finalization: LiveShadowFinalization

    def __post_init__(self) -> None:
        if self.version != LIVE_SHADOW_CAPTURE_VERSION:
            raise ValueError("unsupported live Shadow capture evidence version")
        if self.shadow_ended_at < self.shadow_started_at:
            raise ValueError("Shadow capture end cannot predate start")
        if self.pre_ack_market_event_count < 0:
            raise ValueError("pre-ACK market event count cannot be negative")


def live_shadow_journal_session(
    config: LiveShadowCaptureConfig,
    activation: PaperFillThesisActivation,
) -> JournalSession:
    """Build the evidence session metadata without opening a repository."""

    _validate_activation_binding(config, activation)
    return JournalSession(
        session_id=config.session_id,
        started_at=activation.thesis.filled_at.value,
        mode=LIVE_SHADOW_JOURNAL_MODE,
        metadata={
            "capture_version": LIVE_SHADOW_CAPTURE_VERSION,
            "operation_version": LIVE_SHADOW_OPERATION_VERSION,
            "provider": config.provider.provider,
            "provider_version": config.provider.sdk_version,
            "provider_identity": config.provider.environment_identity,
            "provider_simulation": config.provider.simulation,
            "connection_session_id": config.provider.connection_session_id,
            "paper_fill_activation_id": activation.activation_id,
            "paper_fill_source": activation.provenance.fill_source.value,
            "execution_enabled": False,
            "evidence_only": True,
        },
    )


class LiveShadowCaptureRunner:
    """Admit live data after paired ACK and finalize durable Shadow evidence."""

    def __init__(
        self,
        *,
        config: LiveShadowCaptureConfig,
        activation: PaperFillThesisActivation,
        stream: DataOnlyMarketStream,
        operation: LiveTradeManagementShadowOperation,
        clock: Clock,
    ) -> None:
        _validate_activation_binding(config, activation)
        if stream.environment_identity != config.provider.environment_identity:
            raise ValueError("market stream provider identity does not match capture")
        self._config = config
        self._activation = activation
        self._stream = stream
        self._operation = operation
        self._clock = clock
        self._subscription_ack = Event()
        self._lock = RLock()
        self._started_at: datetime | None = None
        self._ready_at: datetime | None = None
        self._stream_closed = False
        self._evidence: LiveShadowCaptureEvidence | None = None
        self._pre_ack_market_event_count = 0
        self._admission_failures: list[str] = []

    def start(self) -> None:
        with self._lock:
            if self._stream_closed:
                raise RuntimeError("live Shadow market stream is closed")
            if self._started_at is not None:
                return
            now = self._clock.now()
            filled_at = self._activation.thesis.filled_at.value
            if now < filled_at:
                raise RuntimeError("live Shadow capture cannot start before paper fill")
            if now > self._config.scheduled_close:
                raise RuntimeError("live Shadow capture cannot start after market close")
            self._started_at = now
        try:
            self._stream.start(self._on_market, self._on_lifecycle)
            self._stream.request_subscribe(self._config.symbol)
            if not self._subscription_ack.wait(
                self._config.subscribe_ack_timeout_seconds
            ):
                raise RuntimeError("paired market-data subscription ACK timed out")
        except Exception:
            self._stream.close()
            with self._lock:
                self._started_at = None
                self._ready_at = None
                self._stream_closed = True
                self._subscription_ack.clear()
            raise

    def process_pending(self) -> int:
        self._require_ready()
        return len(
            self._operation.process_pending(
                occurred_at=self._clock.now(),
            )
        )

    def finalize(self) -> LiveShadowCaptureEvidence:
        self._require_ready()
        with self._lock:
            if self._evidence is not None:
                return self._evidence
            ready_at = self._ready_at
            close_stream = not self._stream_closed
            self._stream_closed = True
        assert ready_at is not None
        if close_stream:
            self._stream.close()
        while self.process_pending():
            pass
        errors = self._stream.callback_errors
        if errors:
            raise RuntimeError("market-data callback failed: " + "|".join(errors))
        if self._admission_failures:
            raise RuntimeError(
                "canonical admission failed: " + "|".join(self._admission_failures)
            )
        ended_at = self._clock.now()
        finalization = self._operation.finalize(observed_at=ended_at)
        evidence = LiveShadowCaptureEvidence(
            version=LIVE_SHADOW_CAPTURE_VERSION,
            session_id=self._config.session_id,
            activation_id=self._activation.activation_id,
            provider=self._config.provider,
            shadow_started_at=ready_at,
            shadow_ended_at=ended_at,
            pre_ack_market_event_count=self._pre_ack_market_event_count,
            full_market_session_covered=(
                ready_at <= self._config.scheduled_open
                and ended_at >= self._config.scheduled_close
            ),
            finalization=finalization,
        )
        with self._lock:
            self._evidence = evidence
        return evidence

    def _on_market(self, envelope: EventEnvelope) -> None:
        if not self._subscription_ack.is_set():
            with self._lock:
                self._pre_ack_market_event_count += 1
            return
        try:
            result = self._operation.submit_market(
                lambda sequence: _resequence(envelope, sequence)
            )
        except Exception as error:
            with self._lock:
                self._admission_failures.append(
                    f"{type(error).__name__}:{error}"
                )
            return
        if result.status is not AdmissionStatus.ACCEPTED:
            with self._lock:
                self._admission_failures.append(result.status.value)

    def _on_lifecycle(self, event: StreamLifecycleEvent) -> None:
        if (
            event.event_type is StreamLifecycleEventType.SUBSCRIBE_ACKED
            and event.symbol == self._config.symbol
        ):
            if event.occurred_at < self._activation.thesis.filled_at.value:
                with self._lock:
                    self._admission_failures.append("SUBSCRIBE_ACK_PREDATES_FILL")
                return
            with self._lock:
                self._ready_at = event.occurred_at
            self._subscription_ack.set()
            return
        if not self._subscription_ack.is_set():
            return
        result = self._operation.submit_lifecycle(
            lambda sequence: LifecycleIngressMessage(
                event_id=_incident_id(self._config.session_id, sequence, event),
                session_id=self._config.session_id,
                event_type=_incident_type(event.event_type),
                occurred_at=event.occurred_at,
                ingress_sequence=sequence,
                source_identity=(
                    f"{self._config.provider.environment_identity}:lifecycle"
                ),
                reason=event.reason,
                symbol=event.symbol,
                raw_event_code=event.raw_event_code,
                raw_info=event.raw_info,
            )
        )
        if result.status is not AdmissionStatus.ACCEPTED:
            with self._lock:
                self._admission_failures.append(result.status.value)

    def _require_ready(self) -> None:
        if self._started_at is None or not self._subscription_ack.is_set():
            raise RuntimeError("live Shadow capture is not ready")


def _validate_activation_binding(
    config: LiveShadowCaptureConfig,
    activation: PaperFillThesisActivation,
) -> None:
    thesis = activation.thesis
    if activation.provenance.execution_authority:
        raise ValueError("live Shadow capture cannot accept execution authority")
    if thesis.draft.session_id != config.session_id:
        raise ValueError("paper Thesis session does not match live capture")
    if thesis.draft.symbol != config.symbol:
        raise ValueError("paper Thesis symbol does not match live capture")
    if activation.provenance.provider_identity != config.provider.environment_identity:
        raise ValueError("paper fill provider identity does not match live capture")
    if not (
        config.scheduled_open
        <= thesis.filled_at.value
        <= config.scheduled_close
    ):
        raise ValueError("paper fill is outside the configured market session")


def _resequence(envelope: EventEnvelope, sequence: int) -> EventEnvelope:
    return replace(
        envelope,
        ingress_sequence=sequence,
        payload=replace(envelope.payload, ingress_sequence=sequence),
    )


def _incident_type(event_type: StreamLifecycleEventType) -> str:
    if event_type in {
        StreamLifecycleEventType.DISCONNECTED,
        StreamLifecycleEventType.RECONNECTING,
    }:
        return "PROVIDER_DISCONNECTED"
    if event_type in {
        StreamLifecycleEventType.SUBSCRIBE_FAILED,
        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_STARTED,
        StreamLifecycleEventType.SUBSCRIBE_ROLLBACK_FAILED,
        StreamLifecycleEventType.UNSUBSCRIBE_FAILED,
    }:
        return "SUBSCRIPTION_STATE_UNKNOWN"
    return event_type.value


def _incident_id(
    session_id: str,
    sequence: int,
    event: StreamLifecycleEvent,
) -> str:
    return hashlib.sha256(
        (
            f"{session_id}|lifecycle|{sequence}|{event.event_type.value}|"
            f"{event.occurred_at.isoformat()}"
        ).encode()
    ).hexdigest()
