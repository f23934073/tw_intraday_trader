"""Passive multi-symbol late-delivery evidence collection.

The collector intentionally reuses the canonical bounded ingress, durable
Journal, and exact replay contracts.  It never treats a Health state or an
out-of-order disposition as a capture failure: those are the evidence being
measured by D-HEALTH-LATE-001.
"""

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
from market_data.ingress import AdmissionStatus, BoundedIngressQueue, LifecycleIngressMessage
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.journal import JsonlMarketEventRecorder, MarketEventJournalSummary, verify_market_event_journal
from market_data.late_delivery_evidence import (
    LateDeliveryCohort,
    SessionPhase,
    analyze_late_delivery_session,
    write_late_delivery_session_report,
)
from market_data.momentum_stream import (
    QualificationBootstrapEvidence,
    StreamLifecycleEvent,
    StreamLifecycleEventType,
)
from market_data.order_book_store import OrderBookStore
from market_data.pipeline import CanonicalMarketDataPipeline, PipelineProcessStatus
from market_data.qualification_capture import require_qualification_flags_off
from runtime.clock import Clock, SystemClock


TAIPEI = ZoneInfo("Asia/Taipei")
PASSIVE_CAPTURE_REPORT_SCHEMA = "late-delivery-passive-capture-report-v1"

_PHASE_WINDOWS = {
    SessionPhase.OPEN: (time(9, 0), time(9, 30)),
    SessionPhase.MID: (time(10, 30), time(11, 0)),
    SessionPhase.CLOSE: (time(13, 0), time(13, 30)),
}


class PassiveCaptureStream(Protocol):
    @property
    def callback_errors(self) -> tuple[str, ...]: ...

    def start(self, event_handler, lifecycle_handler) -> None: ...

    def qualification_bootstrap_evidence(
        self,
        symbol: str,
        session_date: date,
        prior_session_date: date,
    ) -> QualificationBootstrapEvidence: ...

    def request_subscribe(self, symbol: str) -> None: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class PassiveLateDeliveryCaptureConfig:
    cohort: LateDeliveryCohort
    phase: SessionPhase
    session_id: str
    records_root: Path
    duration_seconds: int = 1800
    subscribe_ack_timeout_seconds: int = 30
    prephase_wait_timeout_seconds: int = 600
    queue_capacity: int = 4096
    control_reserve: int = 64
    retention_seconds: int = 1200

    def __post_init__(self) -> None:
        if not self.session_id.strip():
            raise ValueError("passive collection session_id must not be empty")
        if not 1 <= self.duration_seconds <= 1800:
            raise ValueError("duration_seconds must be between 1 and 1800")
        if self.subscribe_ack_timeout_seconds <= 0:
            raise ValueError("subscribe ACK timeout must be positive")
        if self.prephase_wait_timeout_seconds < 0:
            raise ValueError("pre-phase wait timeout cannot be negative")
        if self.control_reserve <= 0 or self.control_reserve >= self.queue_capacity:
            raise ValueError("queue control reserve must fit within capacity")
        if self.retention_seconds < 1200:
            raise ValueError("retention_seconds must be at least 1200")


@dataclass(frozen=True)
class PassiveLateDeliveryCaptureResult:
    session_dir: Path
    completed: bool
    exact_replay_passed: bool
    evidence_path: Path | None
    report_path: Path | None
    reasons: tuple[str, ...]


class PassiveLateDeliveryCapture:
    """Own one evidence-only capture for every frozen cohort symbol."""

    def __init__(
        self,
        stream: PassiveCaptureStream,
        config: PassiveLateDeliveryCaptureConfig,
        *,
        prior_session_date: date,
        calendar_version: str,
        clock: Clock | None = None,
    ) -> None:
        self._stream = stream
        self.config = config
        self._prior_session_date = prior_session_date
        self._calendar_version = calendar_version
        self._clock = clock or SystemClock()
        self._subscription_acks: dict[str, StreamLifecycleEvent] = {}
        self._capture_gate = Event()
        self._stop_worker = Event()
        self._lock = Lock()
        self._pipeline: CanonicalMarketDataPipeline | None = None
        self._queue: BoundedIngressQueue | None = None
        self._lifecycle_events: list[StreamLifecycleEvent] = []
        self._preboundary_event_count = 0
        self._admission_failures: list[str] = []
        self._stream_counts = {
            symbol: {kind: 0 for kind in MarketStreamKind}
            for symbol in config.cohort.symbols
        }

    def run(self) -> PassiveLateDeliveryCaptureResult:
        require_qualification_flags_off()
        now = self._clock.now().astimezone(TAIPEI)
        session_date = now.date()
        phase_start, phase_end = self._phase_bounds(session_date)
        recorder = JsonlMarketEventRecorder(
            root=self.config.records_root,
            session_id=self.config.session_id,
            session_date=session_date,
            started_at=now,
            producer_identity="late-delivery-passive-capture-v1",
            source_mode="TICK_BIDASK",
        )
        worker: Thread | None = None
        report_path: Path | None = None
        evidence_path: Path | None = None
        try:
            evidence = self._load_bootstrap_evidence(session_date)
            reference_path, reference_artifact = self._write_references(
                recorder.session_dir, evidence, session_date
            )
            self._stream.start(self._on_market, self._on_lifecycle)
            for symbol in self.config.cohort.symbols:
                self._stream.request_subscribe(symbol)
            self._wait_for_paired_acks()
            initialized_at = self._wait_for_phase(phase_start, phase_end)

            references = InstrumentReferenceStore(session_date)
            for item in evidence:
                references.put(item.reference)
            bars = IntradayBarStore(
                session_date, retention=timedelta(seconds=self.config.retention_seconds)
            )
            books = OrderBookStore(
                session_date, retention=timedelta(seconds=self.config.retention_seconds)
            )
            health = DataHealth(session_date, started_at=initialized_at)
            queue = BoundedIngressQueue(
                capacity=self.config.queue_capacity,
                control_reserve=self.config.control_reserve,
                health=health,
            )
            pipeline = CanonicalMarketDataPipeline(
                queue=queue,
                recorder=recorder,
                ingestor=MarketDataIngestor(
                    session_id=self.config.session_id,
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
                evidence=evidence,
                session_date=session_date,
                initialized_at=initialized_at,
                phase_start=phase_start,
                phase_end=phase_end,
            )
            ready_at = self._clock.now().astimezone(TAIPEI)
            health.mark_ready(
                occurred_at=ready_at,
                evidence=f"bootstrap:{bootstrap_artifact['content_sha256']}",
            )
            with self._lock:
                self._pipeline = pipeline
                self._queue = queue
            worker = Thread(
                target=self._consume,
                name=f"late-delivery-{self.config.session_id}",
                daemon=True,
            )
            worker.start()
            self._capture_gate.set()
            self._wait_for_capture_duration()
            self._capture_gate.clear()
            queue.close_market_admission()
            self._stream.close()
            self._stop_worker.set()
            worker.join(timeout=10)
            if worker.is_alive() or len(queue):
                raise RuntimeError("QUEUE_DRAIN_TIMEOUT")
            callback_errors = tuple(getattr(self._stream, "callback_errors", ()))
            if callback_errors:
                raise RuntimeError("CALLBACK_ERRORS:" + "|".join(callback_errors))
            if self._admission_failures:
                raise RuntimeError(
                    "INGRESS_ADMISSION_FAILED:" + "|".join(self._admission_failures)
                )

            bar_digest = bars.finalize_session()
            book_digest = books.finalize_session()
            recorder.finalize(
                MarketEventJournalSummary(
                    finalized_at=self._clock.now().astimezone(TAIPEI),
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
                session_id=self.config.session_id,
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
                    session_date, retention=timedelta(seconds=self.config.retention_seconds)
                ).digest,
                empty_book_digest=OrderBookStore(
                    session_date, retention=timedelta(seconds=self.config.retention_seconds)
                ).digest,
                digest_set=live_digests.to_contract_dict(),
            )
            replay = verify_exact_projection_replay(
                session_dir=recorder.session_dir,
                bootstrap_path=bootstrap_path,
                instrument_reference_path=reference_path,
            )
            evidence_path = write_late_delivery_session_report(
                recorder.session_dir,
                analyze_late_delivery_session(recorder.session_dir),
            )
            reasons = () if replay.valid else tuple(replay.errors)
            report_path = self._write_report(
                recorder.session_dir,
                status="COMPLETE" if replay.valid else "REPLAY_FAILED",
                reasons=reasons,
                replay=replay,
                evidence_path=evidence_path,
                projection_path=projection_path,
            )
            return PassiveLateDeliveryCaptureResult(
                session_dir=recorder.session_dir,
                completed=replay.valid,
                exact_replay_passed=replay.valid,
                evidence_path=evidence_path,
                report_path=report_path,
                reasons=reasons,
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
            reason = f"{type(error).__name__}:{error}"
            try:
                report_path = self._write_report(
                    recorder.session_dir,
                    status="INCOMPLETE",
                    reasons=(reason,),
                    replay=None,
                    evidence_path=None,
                    projection_path=None,
                )
            except (OSError, ValueError):
                report_path = None
            return PassiveLateDeliveryCaptureResult(
                session_dir=recorder.session_dir,
                completed=False,
                exact_replay_passed=False,
                evidence_path=None,
                report_path=report_path,
                reasons=(reason,),
            )

    def _load_bootstrap_evidence(
        self, session_date: date
    ) -> tuple[QualificationBootstrapEvidence, ...]:
        evidence = tuple(
            self._stream.qualification_bootstrap_evidence(
                symbol, session_date, self._prior_session_date
            )
            for symbol in self.config.cohort.symbols
        )
        if tuple(item.reference.symbol for item in evidence) != self.config.cohort.symbols:
            raise RuntimeError("COHORT_BOOTSTRAP_IDENTITY_MISMATCH")
        return evidence

    def _on_market(self, envelope: EventEnvelope) -> None:
        if not self._capture_gate.is_set():
            with self._lock:
                self._preboundary_event_count += 1
            return
        if envelope.symbol not in self._stream_counts:
            return
        with self._lock:
            pipeline = self._pipeline
        if pipeline is None:
            return
        admission = pipeline.submit_market(lambda sequence: _resequence(envelope, sequence))
        with self._lock:
            if admission.accepted:
                self._stream_counts[envelope.symbol][envelope.stream_kind] += 1
            else:
                self._admission_failures.append(admission.status.value)

    def _on_lifecycle(self, event: StreamLifecycleEvent) -> None:
        with self._lock:
            self._lifecycle_events.append(event)
            if event.event_type is StreamLifecycleEventType.SUBSCRIBE_ACKED:
                if event.symbol in self._stream_counts:
                    self._subscription_acks[event.symbol] = event
                return
        if not self._capture_gate.is_set():
            return
        with self._lock:
            pipeline = self._pipeline
        if pipeline is None:
            return
        admission = pipeline.submit_lifecycle(
            lambda sequence: LifecycleIngressMessage(
                event_id=_incident_id(self.config.session_id, sequence, event),
                session_id=self.config.session_id,
                event_type=_incident_type(event.event_type),
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
                pipeline, queue = self._pipeline, self._queue
            if pipeline is None or queue is None:
                return
            results = pipeline.process_pending(occurred_at=self._clock.now())
            if any(item.status is PipelineProcessStatus.RECORDER_FAILED for item in results):
                with self._lock:
                    self._admission_failures.append("RECORDER_FAILED")
                return
            if self._stop_worker.is_set() and not len(queue):
                return
            if not results:
                Event().wait(0.002)

    def _wait_for_paired_acks(self) -> None:
        deadline = self._clock.now().astimezone(TAIPEI) + timedelta(
            seconds=self.config.subscribe_ack_timeout_seconds
        )
        while True:
            with self._lock:
                missing = set(self.config.cohort.symbols) - set(self._subscription_acks)
            if not missing:
                return
            remaining = (deadline - self._clock.now().astimezone(TAIPEI)).total_seconds()
            if remaining <= 0:
                raise RuntimeError("PAIRED_SUBSCRIPTION_ACK_TIMEOUT:" + ",".join(sorted(missing)))
            Event().wait(min(remaining, 0.05))

    def _wait_for_phase(self, starts_at: datetime, ends_at: datetime) -> datetime:
        now = self._clock.now().astimezone(TAIPEI)
        while now < starts_at:
            wait_seconds = (starts_at - now).total_seconds()
            if wait_seconds > self.config.prephase_wait_timeout_seconds:
                raise RuntimeError("PHASE_START_TOO_FAR_AHEAD")
            Event().wait(wait_seconds)
            now = self._clock.now().astimezone(TAIPEI)
        if not starts_at <= now < ends_at:
            raise RuntimeError("OUTSIDE_COLLECTION_PHASE")
        return now

    def _wait_for_capture_duration(self) -> None:
        _, phase_end = self._phase_bounds(self._clock.now().astimezone(TAIPEI).date())
        remaining = (phase_end - self._clock.now().astimezone(TAIPEI)).total_seconds()
        if remaining <= 0:
            raise RuntimeError("OUTSIDE_COLLECTION_PHASE")
        Event().wait(min(self.config.duration_seconds, remaining))

    def _phase_bounds(self, session_date: date) -> tuple[datetime, datetime]:
        start, end = _PHASE_WINDOWS[self.config.phase]
        return (
            datetime.combine(session_date, start, tzinfo=TAIPEI),
            datetime.combine(session_date, end, tzinfo=TAIPEI),
        )

    def _write_references(
        self,
        session_dir: Path,
        evidence: tuple[QualificationBootstrapEvidence, ...],
        session_date: date,
    ) -> tuple[Path, dict[str, object]]:
        entries = []
        for item in evidence:
            reference = item.reference
            exchange = reference.exchange.strip().upper()
            entries.append(
                {
                    "instrument_id": f"{exchange}:{reference.symbol}",
                    "symbol": reference.symbol,
                    "exchange": exchange,
                    "security_type": item.security_type,
                    "name": item.instrument_name,
                    "valid_from": session_date.isoformat(),
                    "valid_to": session_date.isoformat(),
                    "reference_price": str(reference.reference_price),
                    "limit_up_price": _decimal_or_none(reference.limit_up_price),
                    "limit_down_price": _decimal_or_none(reference.limit_down_price),
                    "price_limit_applies": reference.price_limit_applies,
                    "trading_unit_shares": reference.trading_unit_shares,
                    "source_updated_at": (reference.source_updated_at or session_date).isoformat(),
                    "source_identity": item.instrument_source_identity,
                }
            )
        entries.sort(key=lambda item: (str(item["exchange"]), str(item["symbol"])))
        latest_capture = max(item.captured_at for item in evidence)
        raw: dict[str, object] = {
            "schema": INSTRUMENT_REFERENCE_SCHEMA,
            "artifact_id": _artifact_id("reference"),
            "session_id": self.config.session_id,
            "session_date": session_date.isoformat(),
            "timezone": "Asia/Taipei",
            "status": "FINALIZED",
            "source": {
                "provider": "SHIOAJI",
                "source_mode": "CONTRACT_LOOKUP",
                "source_identity": "late-delivery-cohort:" + self.config.cohort.manifest_digest,
                "captured_at": latest_capture.isoformat(),
            },
            "reference_count": len(entries),
            "content_sha256": "",
            "references": entries,
        }
        raw["content_sha256"] = _content_digest(raw, {"status", "reference_count", "content_sha256"})
        path = session_dir / "instrument_reference.json"
        _write_exclusive(path, raw)
        return path, raw

    def _write_bootstrap(
        self,
        session_dir: Path,
        *,
        evidence: tuple[QualificationBootstrapEvidence, ...],
        session_date: date,
        initialized_at: datetime,
        phase_start: datetime,
        phase_end: datetime,
    ) -> tuple[Path, dict[str, object]]:
        by_symbol = {item.reference.symbol: item for item in evidence}
        instrument_ids = sorted(
            f"{item.reference.exchange.strip().upper()}:{item.reference.symbol}"
            for item in evidence
        )
        subscriptions = []
        for instrument_id in instrument_ids:
            symbol = instrument_id.split(":", maxsplit=1)[1]
            ack = self._subscription_acks[symbol]
            for stream in sorted(MarketStreamKind, key=lambda item: item.value):
                subscriptions.append(
                    {
                        "instrument_id": instrument_id,
                        "stream_kind": stream.value,
                        "state": "ACKED",
                        "effective_at": ack.occurred_at.isoformat(),
                        "evidence_identity": (
                            f"shioaji-paired-ack:{ack.raw_event_code}:{ack.occurred_at.isoformat()}"
                        ),
                    }
                )
        symbols = []
        for instrument_id in instrument_ids:
            symbol = instrument_id.split(":", maxsplit=1)[1]
            item = by_symbol[symbol]
            symbols.append(
                {
                    "instrument_id": instrument_id,
                    "symbol": symbol,
                    "prior_session_date": item.prior_session_date.isoformat(),
                    "previous_close": str(item.previous_close),
                    "previous_session_volume_lots": item.previous_session_volume_lots,
                    "source_identity": item.snapshot_source_identity,
                }
            )
        captured_at = max(item.captured_at for item in evidence)
        received_at = max(item.received_at for item in evidence)
        raw: dict[str, object] = {
            "schema": BOOTSTRAP_SNAPSHOT_SCHEMA,
            "artifact_id": _artifact_id("bootstrap"),
            "session_id": self.config.session_id,
            "session_date": session_date.isoformat(),
            "timezone": "Asia/Taipei",
            "status": "FINALIZED",
            "source": {
                "provider": "SHIOAJI",
                "source_mode": "SNAPSHOT_BOOTSTRAP",
                "source_identity": "late-delivery-cohort:" + self.config.cohort.manifest_digest,
            },
            "captured_at": captured_at.isoformat(),
            "received_at": received_at.isoformat(),
            "journal_boundary": {
                "first_record_index": 1,
                "first_ingress_sequence": 1,
                "projection_started_at": initialized_at.isoformat(),
            },
            "calendar": {
                "calendar_id": "TAIWAN_EXCHANGE_SESSION",
                "calendar_version": self._calendar_version,
                "session_phase": self.config.phase.value,
                "scheduled_open": phase_start.isoformat(),
                "scheduled_close": phase_end.isoformat(),
            },
            "coverage": {
                "required_instrument_ids": instrument_ids,
                "captured_instrument_ids": instrument_ids,
                "missing_instrument_ids": [],
            },
            "subscriptions": subscriptions,
            "symbols": symbols,
            "projection_seed_mode": "EMPTY_SESSION",
            "content_sha256": "",
        }
        raw["content_sha256"] = _content_digest(raw, {"status", "content_sha256"})
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
            "session_id": self.config.session_id,
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
                "retention_seconds": self.config.retention_seconds,
                "reference_store": {"expected_initial_digest": reference_digest},
                "bar": {"mode": "EMPTY", "finalized": False, "expected_initial_digest": empty_bar_digest},
                "book": {"mode": "EMPTY", "finalized": False, "expected_initial_digest": empty_book_digest},
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
                "ready_transition": {"occurred_at": ready_at.isoformat(), "evidence": ready_evidence},
            },
            "expected_final": {"repeat_count": 10, "digest_set": dict(digest_set)},
            "content_sha256": "",
        }
        raw["content_sha256"] = _content_digest(raw, {"status", "content_sha256"})
        path = session_dir / "projection_state.json"
        _write_exclusive(path, raw)
        return path

    def _write_report(
        self,
        session_dir: Path,
        *,
        status: str,
        reasons: tuple[str, ...],
        replay,
        evidence_path: Path | None,
        projection_path: Path | None,
    ) -> Path:
        raw = {
            "schema": PASSIVE_CAPTURE_REPORT_SCHEMA,
            "session_id": self.config.session_id,
            "status": status,
            "reasons": list(reasons),
            "safety": {
                "foundation_flags_off": True,
                "subscribe_trade": False,
                "order_path": "NOT_WIRED",
                "consumer_authority": "UNCHANGED",
                "source_environment": getattr(self._stream, "environment_identity", "passive-stream:unspecified"),
            },
            "collection": {
                "mode": "PASSIVE_EVIDENCE_ONLY",
                "phase": self.config.phase.value,
                "cohort_manifest_sha256": self.config.cohort.manifest_digest,
                "symbols": list(self.config.cohort.symbols),
                "duration_seconds_requested": self.config.duration_seconds,
                "preboundary_event_count": self._preboundary_event_count,
                "stream_counts": {
                    symbol: {kind.value: count for kind, count in counts.items()}
                    for symbol, counts in sorted(self._stream_counts.items())
                },
                "natural_lifecycle_events": [item.event_type.value for item in self._lifecycle_events],
            },
            "artifacts": {
                "journal": "records.jsonl",
                "manifest": "manifest.json",
                "bootstrap": "bootstrap_snapshot.json" if projection_path else None,
                "instrument_reference": "instrument_reference.json" if projection_path else None,
                "projection_state": projection_path.name if projection_path else None,
                "late_delivery_evidence": evidence_path.name if evidence_path else None,
            },
            "exact_replay": None if replay is None else {
                "passed": replay.valid,
                "repeat_count": replay.repeat_count,
                "errors": list(replay.errors),
                "comparisons": [
                    {"name": item.name, "expected": item.expected, "actual": item.actual, "match": item.match, "first_divergence": item.first_divergence}
                    for item in replay.comparisons
                ],
            },
            "policy_interpretation": "PROHIBITED_EVIDENCE_ONLY",
            "gate_effect": "NONE_HEALTH_POLICY_AND_P1_2_UNCHANGED",
        }
        path = session_dir / "passive_capture_report.json"
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
