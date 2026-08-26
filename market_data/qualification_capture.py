"""Flags-off, data-only historical qualification capture application."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, replace
from datetime import date, datetime, time, timedelta
from pathlib import Path
from threading import Event, Lock, Thread
from typing import Mapping, Protocol
from uuid import uuid4
from zoneinfo import ZoneInfo

from config.foundation import FOUNDATION_FEATURE_FLAGS
from market_data.events import EventEnvelope, MarketStreamKind
from market_data.exact_replay import (
    BOOTSTRAP_SNAPSHOT_SCHEMA,
    EXACT_REPLAY_ENGINE_VERSION,
    INSTRUMENT_REFERENCE_SCHEMA,
    PROJECTION_STATE_SCHEMA,
    build_live_projection_digest_set,
    verify_exact_projection_replay,
)
from market_data.health import DataHealth, DataHealthState
from market_data.ingestion import MarketDataIngestor
from market_data.ingress import (
    AdmissionStatus,
    BoundedIngressQueue,
    LifecycleIngressMessage,
)
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.journal import (
    JsonlMarketEventRecorder,
    MarketEventJournalSummary,
    verify_market_event_journal,
)
from market_data.momentum_stream import (
    QualificationBootstrapEvidence,
    StreamLifecycleEvent,
    StreamLifecycleEventType,
)
from market_data.order_book_store import OrderBookStore
from market_data.pipeline import (
    CanonicalMarketDataPipeline,
    PipelineProcessResult,
    PipelineProcessStatus,
)
from runtime.clock import Clock, SystemClock


TAIPEI = ZoneInfo("Asia/Taipei")
QUALIFICATION_REPORT_SCHEMA = "historical-qualification-report-v1"


def require_qualification_flags_off() -> None:
    """Fail before any provider connection if foundation authority is enabled."""
    enabled = [
        name
        for name, value in vars(FOUNDATION_FEATURE_FLAGS).items()
        if value
    ]
    if enabled:
        raise RuntimeError("FOUNDATION_FLAGS_MUST_BE_OFF:" + ",".join(enabled))


class QualificationCaptureStream(Protocol):
    def start(self, event_handler, lifecycle_handler) -> None: ...

    def qualification_bootstrap_evidence(
        self,
        symbol: str,
        session_date: date,
        prior_session_date: date,
    ) -> QualificationBootstrapEvidence: ...

    def request_subscribe(self, symbol: str) -> None: ...

    def close(self) -> None: ...


class CanonicalProcessObserver(Protocol):
    """Optional application hook for the already-recorded canonical stream."""

    def bind_market_pipeline(self, pipeline: CanonicalMarketDataPipeline) -> None: ...

    def observe_canonical_result(self, result: PipelineProcessResult) -> None: ...


@dataclass(frozen=True)
class QualificationCaptureConfig:
    symbol: str
    session_id: str
    records_root: Path
    duration_seconds: int = 30
    subscribe_ack_timeout_seconds: int = 30
    preopen_wait_timeout_seconds: int = 600
    queue_capacity: int = 4096
    control_reserve: int = 64
    retention_seconds: int = 1200
    qualification_case: str = "A"

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValueError("qualification symbol must not be empty")
        object.__setattr__(self, "symbol", symbol)
        if not self.session_id.strip():
            raise ValueError("qualification session_id must not be empty")
        if not 1 <= self.duration_seconds <= 21600:
            raise ValueError("duration_seconds must be between 1 and 21600")
        if self.subscribe_ack_timeout_seconds <= 0:
            raise ValueError("subscribe ACK timeout must be positive")
        if self.preopen_wait_timeout_seconds < 0:
            raise ValueError("pre-open wait timeout cannot be negative")
        if self.control_reserve <= 0 or self.control_reserve >= self.queue_capacity:
            raise ValueError("queue control reserve must fit within capacity")
        if self.retention_seconds < 1200:
            raise ValueError("retention_seconds must be at least 1200")
        if self.qualification_case not in {"A", "B"}:
            raise ValueError("qualification_case must be A or B")


@dataclass(frozen=True)
class QualificationCaptureResult:
    session_dir: Path
    qualified: bool
    classification: str
    reasons: tuple[str, ...]
    report_path: Path | None
    exact_replay_passed: bool


class HistoricalQualificationCapture:
    """Own one bounded capture; callbacks only admit immutable messages."""

    def __init__(
        self,
        stream: QualificationCaptureStream,
        config: QualificationCaptureConfig,
        *,
        prior_session_date: date,
        calendar_version: str,
        clock: Clock | None = None,
        process_observer: CanonicalProcessObserver | None = None,
    ) -> None:
        self._stream = stream
        self._config = config
        self._prior_session_date = prior_session_date
        self._calendar_version = calendar_version
        self._clock = clock or SystemClock()
        self._process_observer = process_observer
        self._subscription_ack = Event()
        self._capture_gate = Event()
        self._stop_worker = Event()
        self._lock = Lock()
        self._pipeline: CanonicalMarketDataPipeline | None = None
        self._queue: BoundedIngressQueue | None = None
        self._lifecycle_events: list[StreamLifecycleEvent] = []
        self._preboundary_event_count = 0
        self._admission_failures: list[str] = []
        self._stream_counts = {kind: 0 for kind in MarketStreamKind}

    def run(self) -> QualificationCaptureResult:
        require_qualification_flags_off()
        now = self._clock.now().astimezone(TAIPEI)
        session_date = now.date()
        scheduled_open = datetime.combine(session_date, time(9, 0), tzinfo=TAIPEI)
        scheduled_close = datetime.combine(session_date, time(13, 30), tzinfo=TAIPEI)
        recorder = JsonlMarketEventRecorder(
            root=self._config.records_root,
            session_id=self._config.session_id,
            session_date=session_date,
            started_at=now,
            producer_identity="qualification-capture-harness-v1",
            source_mode="TICK_BIDASK",
        )
        worker: Thread | None = None
        try:
            evidence = self._stream.qualification_bootstrap_evidence(
                self._config.symbol,
                session_date,
                self._prior_session_date,
            )
            reference_path, reference_artifact = self._write_reference(
                recorder.session_dir,
                evidence,
                session_date,
            )
            self._stream.start(self._on_market, self._on_lifecycle)
            self._stream.request_subscribe(self._config.symbol)
            if not self._subscription_ack.wait(
                self._config.subscribe_ack_timeout_seconds
            ):
                raise RuntimeError("PAIRED_SUBSCRIPTION_ACK_TIMEOUT")
            ack = self._paired_ack()
            initialized_at = self._wait_for_open(scheduled_open, scheduled_close)
            references = InstrumentReferenceStore(session_date)
            references.put(evidence.reference)
            bars = IntradayBarStore(
                session_date,
                retention=timedelta(seconds=self._config.retention_seconds),
            )
            books = OrderBookStore(
                session_date,
                retention=timedelta(seconds=self._config.retention_seconds),
            )
            health = DataHealth(session_date, started_at=initialized_at)
            queue = BoundedIngressQueue(
                capacity=self._config.queue_capacity,
                control_reserve=self._config.control_reserve,
                health=health,
            )
            pipeline = CanonicalMarketDataPipeline(
                queue=queue,
                recorder=recorder,
                ingestor=MarketDataIngestor(
                    session_id=self._config.session_id,
                    session_date=session_date,
                    references=references,
                    bars=bars,
                    books=books,
                    health=health,
                ),
                health=health,
            )
            bootstrap_path, bootstrap_artifact = self._write_bootstrap(
                recorder.session_dir,
                evidence,
                ack,
                session_date,
                initialized_at,
                scheduled_open,
                scheduled_close,
            )
            ready_at = self._clock.now().astimezone(TAIPEI)
            health.mark_ready(
                occurred_at=ready_at,
                evidence=f"bootstrap:{bootstrap_artifact['content_sha256']}",
            )
            with self._lock:
                self._pipeline = pipeline
                self._queue = queue
            if self._process_observer is not None:
                self._process_observer.bind_market_pipeline(pipeline)
            worker = Thread(
                target=self._consume,
                name=f"qualification-{self._config.session_id}",
                daemon=True,
            )
            worker.start()
            self._capture_gate.set()
            Event().wait(self._config.duration_seconds)
            self._capture_gate.clear()
            queue.close_market_admission()
            self._stream.close()
            self._stop_worker.set()
            worker.join(timeout=10)
            if self._admission_failures:
                raise RuntimeError(
                    "INGRESS_ADMISSION_FAILED:" + "|".join(self._admission_failures)
                )
            if worker.is_alive() or len(queue):
                raise RuntimeError("QUEUE_DRAIN_TIMEOUT")
            callback_errors = tuple(getattr(self._stream, "callback_errors", ()))
            if callback_errors:
                raise RuntimeError("CALLBACK_ERRORS:" + "|".join(callback_errors))
            bar_digest = bars.finalize_session()
            book_digest = books.finalize_session()
            finalized_at = self._clock.now().astimezone(TAIPEI)
            recorder.finalize(
                MarketEventJournalSummary(
                    finalized_at=finalized_at,
                    queue_drained=True,
                    projection_digest={
                        "bar": bar_digest,
                        "book": book_digest,
                        "health": health.snapshot().digest,
                    },
                )
            )
            journal = verify_market_event_journal(recorder.session_dir)
            if not journal.valid or journal.manifest is None:
                raise RuntimeError("FINALIZED_JOURNAL_VERIFICATION_FAILED")
            live_digests = build_live_projection_digest_set(
                session_id=self._config.session_id,
                session_date=session_date,
                records=journal.records,
                health=health,
                bar_digest=bar_digest,
                book_digest=book_digest,
                initial_state=DataHealthState.HEALTHY,
            )
            projection_path = self._write_projection_state(
                recorder.session_dir,
                session_date=session_date,
                initialized_at=initialized_at,
                ready_at=ready_at,
                ready_evidence=f"bootstrap:{bootstrap_artifact['content_sha256']}",
                journal_sha256=str(journal.manifest["sha256"]),
                reference_sha256=str(reference_artifact["content_sha256"]),
                bootstrap_sha256=str(bootstrap_artifact["content_sha256"]),
                reference_digest=references.digest,
                empty_bar_digest=IntradayBarStore(
                    session_date,
                    retention=timedelta(seconds=self._config.retention_seconds),
                ).digest,
                empty_book_digest=OrderBookStore(
                    session_date,
                    retention=timedelta(seconds=self._config.retention_seconds),
                ).digest,
                digest_set=live_digests.to_contract_dict(),
            )
            replay = verify_exact_projection_replay(
                session_dir=recorder.session_dir,
                bootstrap_path=bootstrap_path,
                instrument_reference_path=reference_path,
            )
            reasons, classification = self._qualification_reasons(
                journal.manifest,
                health,
                replay.valid,
            )
            qualified = not reasons and (
                classification == f"CASE_{self._config.qualification_case}"
            )
            report_path = self._write_report(
                recorder.session_dir,
                classification=classification,
                qualified=qualified,
                reasons=reasons,
                replay=replay,
                projection_path=projection_path,
            )
            return QualificationCaptureResult(
                session_dir=recorder.session_dir,
                qualified=qualified,
                classification=classification,
                reasons=tuple(reasons),
                report_path=report_path,
                exact_replay_passed=replay.valid,
            )
        except Exception as error:
            self._capture_gate.clear()
            self._stop_worker.set()
            try:
                self._stream.close()
            except Exception:
                pass
            if worker is not None and worker.is_alive():
                worker.join(timeout=10)
            try:
                recorder.mark_incomplete(
                    reason=f"{type(error).__name__}:{error}",
                    occurred_at=self._clock.now().astimezone(TAIPEI),
                )
            except ValueError:
                pass
            return QualificationCaptureResult(
                session_dir=recorder.session_dir,
                qualified=False,
                classification="INCOMPLETE",
                reasons=(f"{type(error).__name__}:{error}",),
                report_path=None,
                exact_replay_passed=False,
            )

    def _on_market(self, envelope: EventEnvelope) -> None:
        if not self._capture_gate.is_set():
            with self._lock:
                self._preboundary_event_count += 1
            return
        with self._lock:
            pipeline = self._pipeline
        if pipeline is None:
            return
        admission = pipeline.submit_market(
            lambda sequence: _resequence(envelope, sequence)
        )
        with self._lock:
            if admission.accepted:
                self._stream_counts[envelope.stream_kind] += 1
            else:
                self._admission_failures.append(admission.status.value)

    def _on_lifecycle(self, event: StreamLifecycleEvent) -> None:
        with self._lock:
            self._lifecycle_events.append(event)
        if event.event_type is StreamLifecycleEventType.SUBSCRIBE_ACKED:
            self._subscription_ack.set()
            return
        if not self._capture_gate.is_set():
            return
        with self._lock:
            pipeline = self._pipeline
        if pipeline is None:
            return
        incident_type = _incident_type(event.event_type)
        admission = pipeline.submit_lifecycle(
            lambda sequence: LifecycleIngressMessage(
                event_id=_incident_id(self._config.session_id, sequence, event),
                session_id=self._config.session_id,
                event_type=incident_type,
                occurred_at=event.occurred_at,
                ingress_sequence=sequence,
                source_identity="shioaji:quote-lifecycle",
                reason=event.reason,
                symbol=event.symbol,
                raw_event_code=event.raw_event_code,
                raw_info=event.raw_info,
            )
        )
        if admission.status is not AdmissionStatus.ACCEPTED:
            with self._lock:
                self._admission_failures.append(admission.status.value)

    def _consume(self) -> None:
        while True:
            with self._lock:
                pipeline = self._pipeline
                queue = self._queue
            if pipeline is None or queue is None:
                return
            results = pipeline.process_pending(occurred_at=self._clock.now())
            if self._process_observer is not None:
                try:
                    for result in results:
                        self._process_observer.observe_canonical_result(result)
                except Exception as error:
                    queue.close_all_admission()
                    with self._lock:
                        self._admission_failures.append(
                            "PROCESS_OBSERVER_FAILED:"
                            f"{type(error).__name__}:{error}"
                        )
                    return
            if any(
                item.status is PipelineProcessStatus.RECORDER_FAILED
                for item in results
            ):
                with self._lock:
                    self._admission_failures.append("RECORDER_FAILED")
                return
            if self._stop_worker.is_set() and not len(queue):
                return
            if not results:
                Event().wait(0.002)

    def _paired_ack(self) -> StreamLifecycleEvent:
        with self._lock:
            matches = [
                item
                for item in self._lifecycle_events
                if item.event_type is StreamLifecycleEventType.SUBSCRIBE_ACKED
                and item.symbol == self._config.symbol
            ]
        if len(matches) != 1:
            raise RuntimeError("PAIRED_SUBSCRIPTION_ACK_AMBIGUOUS")
        return matches[0]

    def _wait_for_open(
        self,
        scheduled_open: datetime,
        scheduled_close: datetime,
    ) -> datetime:
        now = self._clock.now().astimezone(TAIPEI)
        if now < scheduled_open:
            seconds = (scheduled_open - now).total_seconds()
            if seconds > self._config.preopen_wait_timeout_seconds:
                raise RuntimeError("SESSION_OPEN_TOO_FAR_AHEAD")
            while now < scheduled_open:
                Event().wait((scheduled_open - now).total_seconds())
                now = self._clock.now().astimezone(TAIPEI)
        if now < scheduled_open or now > scheduled_close:
            raise RuntimeError("OUTSIDE_REGULAR_SESSION")
        return now

    def _qualification_reasons(
        self,
        manifest: Mapping[str, object],
        health: DataHealth,
        replay_passed: bool,
    ) -> tuple[list[str], str]:
        statistics = dict(manifest["statistics"])
        has_incident = int(statistics["incidents"]) > 0
        has_rejection = int(statistics["rejected"]) > 0
        degraded = health.state is not DataHealthState.HEALTHY
        classification = (
            "CASE_B" if has_incident or has_rejection or degraded else "CASE_A"
        )
        reasons: list[str] = []
        for kind in MarketStreamKind:
            if self._stream_counts[kind] <= 0:
                reasons.append(f"MISSING_{kind.value}_EVIDENCE")
        if not replay_passed:
            reasons.append("EXACT_REPLAY_FAILED")
        if classification != f"CASE_{self._config.qualification_case}":
            reasons.append(
                f"CAPTURE_CLASSIFIED_{classification}_NOT_CASE_{self._config.qualification_case}"
            )
        return reasons, classification

    def _write_reference(
        self,
        session_dir: Path,
        evidence: QualificationBootstrapEvidence,
        session_date: date,
    ) -> tuple[Path, dict[str, object]]:
        reference = evidence.reference
        exchange = reference.exchange.strip().upper()
        instrument_id = f"{exchange}:{reference.symbol}"
        raw: dict[str, object] = {
            "schema": INSTRUMENT_REFERENCE_SCHEMA,
            "artifact_id": _artifact_id("reference"),
            "session_id": self._config.session_id,
            "session_date": session_date.isoformat(),
            "timezone": "Asia/Taipei",
            "status": "FINALIZED",
            "source": {
                "provider": "SHIOAJI",
                "source_mode": "CONTRACT_LOOKUP",
                "source_identity": evidence.instrument_source_identity,
                "captured_at": evidence.captured_at.isoformat(),
            },
            "reference_count": 1,
            "content_sha256": "",
            "references": [{
                "instrument_id": instrument_id,
                "symbol": reference.symbol,
                "exchange": exchange,
                "security_type": evidence.security_type,
                "name": evidence.instrument_name,
                "valid_from": session_date.isoformat(),
                "valid_to": session_date.isoformat(),
                "reference_price": str(reference.reference_price),
                "limit_up_price": _decimal_or_none(reference.limit_up_price),
                "limit_down_price": _decimal_or_none(reference.limit_down_price),
                "price_limit_applies": reference.price_limit_applies,
                "trading_unit_shares": reference.trading_unit_shares,
                "source_updated_at": (
                    reference.source_updated_at or session_date
                ).isoformat(),
                "source_identity": evidence.instrument_source_identity,
            }],
        }
        raw["content_sha256"] = _content_digest(
            raw,
            {"status", "reference_count", "content_sha256"},
        )
        path = session_dir / "instrument_reference.json"
        _write_exclusive(path, raw)
        return path, raw

    def _write_bootstrap(
        self,
        session_dir: Path,
        evidence: QualificationBootstrapEvidence,
        ack: StreamLifecycleEvent,
        session_date: date,
        initialized_at: datetime,
        scheduled_open: datetime,
        scheduled_close: datetime,
    ) -> tuple[Path, dict[str, object]]:
        reference = evidence.reference
        instrument_id = f"{reference.exchange.strip().upper()}:{reference.symbol}"
        subscriptions = [
            {
                "instrument_id": instrument_id,
                "stream_kind": kind.value,
                "state": "ACKED",
                "effective_at": ack.occurred_at.isoformat(),
                "evidence_identity": (
                    f"shioaji-paired-ack:{ack.raw_event_code}:"
                    f"{ack.occurred_at.isoformat()}"
                ),
            }
            for kind in sorted(MarketStreamKind, key=lambda item: item.value)
        ]
        raw: dict[str, object] = {
            "schema": BOOTSTRAP_SNAPSHOT_SCHEMA,
            "artifact_id": _artifact_id("bootstrap"),
            "session_id": self._config.session_id,
            "session_date": session_date.isoformat(),
            "timezone": "Asia/Taipei",
            "status": "FINALIZED",
            "source": {
                "provider": "SHIOAJI",
                "source_mode": "SNAPSHOT_BOOTSTRAP",
                "source_identity": evidence.snapshot_source_identity,
            },
            "captured_at": evidence.captured_at.isoformat(),
            "received_at": evidence.received_at.isoformat(),
            "journal_boundary": {
                "first_record_index": 1,
                "first_ingress_sequence": 1,
                "projection_started_at": initialized_at.isoformat(),
            },
            "calendar": {
                "calendar_id": "TAIWAN_EXCHANGE_SESSION",
                "calendar_version": self._calendar_version,
                "session_phase": "REGULAR",
                "scheduled_open": scheduled_open.isoformat(),
                "scheduled_close": scheduled_close.isoformat(),
            },
            "coverage": {
                "required_instrument_ids": [instrument_id],
                "captured_instrument_ids": [instrument_id],
                "missing_instrument_ids": [],
            },
            "subscriptions": subscriptions,
            "symbols": [{
                "instrument_id": instrument_id,
                "symbol": reference.symbol,
                "prior_session_date": evidence.prior_session_date.isoformat(),
                "previous_close": str(evidence.previous_close),
                "previous_session_volume_lots": evidence.previous_session_volume_lots,
                "source_identity": evidence.snapshot_source_identity,
            }],
            "projection_seed_mode": "EMPTY_SESSION",
            "content_sha256": "",
        }
        raw["content_sha256"] = _content_digest(
            raw,
            {"status", "content_sha256"},
        )
        path = session_dir / "bootstrap_snapshot.json"
        _write_exclusive(path, raw)
        return path, raw

    def _write_projection_state(
        self,
        session_dir: Path,
        *,
        session_date: date,
        initialized_at: datetime,
        ready_at: datetime,
        ready_evidence: str,
        journal_sha256: str,
        reference_sha256: str,
        bootstrap_sha256: str,
        reference_digest: str,
        empty_bar_digest: str,
        empty_book_digest: str,
        digest_set: Mapping[str, object],
    ) -> Path:
        raw: dict[str, object] = {
            "schema": PROJECTION_STATE_SCHEMA,
            "artifact_id": _artifact_id("projection"),
            "session_id": self._config.session_id,
            "session_date": session_date.isoformat(),
            "timezone": "Asia/Taipei",
            "status": "FINALIZED",
            "input_digests": {
                "journal_sha256": journal_sha256,
                "instrument_reference_sha256": reference_sha256,
                "bootstrap_sha256": bootstrap_sha256,
            },
            "versions": {
                "ingestor": "market-data-ingestor-v1",
                "bar_projection": "bar-projection-digest-v1",
                "book_projection": "book-projection-digest-v1",
                "health_projection": "data-health-replay-v1",
                "replay_engine": EXACT_REPLAY_ENGINE_VERSION,
            },
            "initialization": {
                "mode": "EMPTY_SESSION",
                "initialized_at": initialized_at.isoformat(),
                "retention_seconds": self._config.retention_seconds,
                "reference_store": {"expected_initial_digest": reference_digest},
                "bar": {
                    "mode": "EMPTY",
                    "finalized": False,
                    "expected_initial_digest": empty_bar_digest,
                },
                "book": {
                    "mode": "EMPTY",
                    "finalized": False,
                    "expected_initial_digest": empty_book_digest,
                },
                "health": {
                    "state": "STARTING",
                    "reasons": [],
                    "streams": [],
                    "queue_depth": 0,
                    "queue_high_watermark": 0,
                    "queue_overflow_count": 0,
                    "session_mismatch_count": 0,
                    "invalid_count": 0,
                    "gap_count": 0,
                    "source_clock_skew_count": 0,
                    "reconnect_epoch": 0,
                    "resync_verified_at": None,
                    "as_of": initialized_at.isoformat(),
                },
                "ready_transition": {
                    "occurred_at": ready_at.isoformat(),
                    "evidence": ready_evidence,
                },
            },
            "expected_final": {
                "repeat_count": 10,
                "digest_set": dict(digest_set),
            },
            "content_sha256": "",
        }
        raw["content_sha256"] = _content_digest(
            raw,
            {"status", "content_sha256"},
        )
        path = session_dir / "projection_state.json"
        _write_exclusive(path, raw)
        return path

    def _write_report(
        self,
        session_dir: Path,
        *,
        classification: str,
        qualified: bool,
        reasons: list[str],
        replay,
        projection_path: Path,
    ) -> Path:
        raw = {
            "schema": QUALIFICATION_REPORT_SCHEMA,
            "session_id": self._config.session_id,
            "requested_case": self._config.qualification_case,
            "classification": classification,
            "status": "PASS" if qualified else "FAIL",
            "reasons": reasons,
            "safety": {
                "foundation_flags_off": True,
                "subscribe_trade": False,
                "order_path": "NOT_WIRED",
                "consumer_authority": "UNCHANGED",
                "source_environment": getattr(
                    self._stream,
                    "environment_identity",
                    "qualification-stream:unspecified",
                ),
            },
            "capture": {
                "symbol": self._config.symbol,
                "duration_seconds": self._config.duration_seconds,
                "preboundary_event_count": self._preboundary_event_count,
                "stream_counts": {
                    key.value: value for key, value in self._stream_counts.items()
                },
                "natural_lifecycle_events": [
                    item.event_type.value for item in self._lifecycle_events
                ],
            },
            "artifacts": {
                "journal": "records.jsonl",
                "manifest": "manifest.json",
                "bootstrap": "bootstrap_snapshot.json",
                "instrument_reference": "instrument_reference.json",
                "projection_state": projection_path.name,
            },
            "exact_replay": {
                "passed": replay.valid,
                "repeat_count": replay.repeat_count,
                "errors": list(replay.errors),
                "comparisons": [
                    {
                        "name": item.name,
                        "expected": item.expected,
                        "actual": item.actual,
                        "match": item.match,
                        "first_divergence": item.first_divergence,
                    }
                    for item in replay.comparisons
                ],
            },
            "gate_effect": "NONE_P1_2_REMAINS_BLOCKED",
        }
        path = session_dir / "qualification_report.json"
        _write_exclusive(path, raw)
        return path


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


def _artifact_id(kind: str) -> str:
    return f"{kind}-{uuid4().hex}"


def _decimal_or_none(value) -> str | None:
    return None if value is None else str(value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _content_digest(value: Mapping[str, object], excluded: set[str]) -> str:
    payload = {key: item for key, item in value.items() if key not in excluded}
    return hashlib.sha256(_canonical_bytes(payload).rstrip(b"\n")).hexdigest()


def _write_exclusive(path: Path, value: Mapping[str, object]) -> None:
    encoded = _canonical_bytes(value)
    with path.open("xb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    directory_fd = os.open(path.parent, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try:
        os.fsync(directory_fd)
    finally:
        os.close(directory_fd)
