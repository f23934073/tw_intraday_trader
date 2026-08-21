import hashlib
import json
import os
import subprocess
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from market_data.events import (
    AggressorSide,
    EventEnvelope,
    InstrumentReference,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)
from market_data.health import DataHealth, DataHealthReason, DataHealthState
from market_data.ingestion import MarketDataIngestor
from market_data.ingress import BoundedIngressQueue, LifecycleIngressMessage
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.journal import (
    JOURNAL_SCHEMA_VERSION,
    JournalStatus,
    JsonlMarketEventRecorder,
    MarketEventJournalSummary,
    verify_market_event_journal,
)
from market_data.order_book_store import OrderBookStore
from market_data.pipeline import CanonicalMarketDataPipeline, PipelineProcessStatus
from market_data.replay_cli import main as replay_cli_main
from market_data.recording import MarketEventRecorder


TAIPEI = ZoneInfo("Asia/Taipei")
SESSION_DATE = date(2026, 8, 20)
SESSION_ID = "20260820-journal-test"


def timestamp(second: int) -> datetime:
    return datetime(2026, 8, 20, 9, 0, tzinfo=TAIPEI) + timedelta(
        seconds=second
    )


def tick_envelope(sequence: int) -> EventEnvelope:
    event_at = timestamp(sequence)
    event_id = f"tick-{sequence}"
    payload = TickEvent(
        event_id=event_id,
        source=MarketEventSource.TICK,
        symbol="2330",
        session_date=SESSION_DATE,
        event_time=event_at,
        received_at=event_at,
        ingress_sequence=sequence,
        price=Decimal("600"),
        tick_volume_lots=1,
        total_volume_lots=sequence,
        average_price=Decimal("599.5"),
        intraday_high=Decimal("601"),
        intraday_low=Decimal("598"),
        raw_tick_type=1,
        aggressor_side=AggressorSide.BUY,
        buy_aggressor_total_lots=None,
        sell_aggressor_total_lots=None,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=event_id,
        schema_version=MARKET_EVENT_SCHEMA_VERSION,
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        source=MarketEventSource.TICK,
        source_mode="TEST",
        stream_kind=MarketStreamKind.TICK,
        symbol="2330",
        event_at=event_at,
        received_at=event_at,
        ingress_sequence=sequence,
        source_identity=f"pytest:tick:{sequence}",
        payload=payload,
    )


def lifecycle_message(sequence: int) -> LifecycleIngressMessage:
    return LifecycleIngressMessage(
        event_id=f"lifecycle-{sequence}",
        session_id=SESSION_ID,
        event_type="RECONNECT",
        occurred_at=timestamp(sequence),
        ingress_sequence=sequence,
        source_identity=f"pytest:lifecycle:{sequence}",
        reason="test reconnect evidence",
    )


def components(tmp_path: Path):
    references = InstrumentReferenceStore(SESSION_DATE)
    references.put(
        InstrumentReference(
            symbol="2330",
            exchange="TSE",
            session_date=SESSION_DATE,
            reference_price=Decimal("590"),
            limit_up_price=Decimal("649"),
            limit_down_price=Decimal("531"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=SESSION_DATE,
        )
    )
    bars = IntradayBarStore(SESSION_DATE, retention=timedelta(minutes=20))
    books = OrderBookStore(SESSION_DATE, retention=timedelta(minutes=20))
    health = DataHealth(SESSION_DATE, started_at=timestamp(0))
    health.mark_ready(occurred_at=timestamp(0), evidence="fixture")
    recorder = JsonlMarketEventRecorder(
        root=tmp_path / "records" / "market_events",
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        started_at=timestamp(0),
        producer_identity="pytest",
        source_mode="TEST",
    )
    queue = BoundedIngressQueue(capacity=8, control_reserve=1, health=health)
    pipeline = CanonicalMarketDataPipeline(
        queue=queue,
        recorder=recorder,
        ingestor=MarketDataIngestor(
            session_id=SESSION_ID,
            session_date=SESSION_DATE,
            references=references,
            bars=bars,
            books=books,
            health=health,
        ),
        health=health,
    )
    return pipeline, recorder, bars, books, health


def finalized_session(tmp_path: Path):
    pipeline, recorder, bars, books, health = components(tmp_path)
    assert pipeline.submit_market(tick_envelope).accepted
    assert pipeline.submit_lifecycle(lifecycle_message).accepted
    processed = pipeline.process_pending(occurred_at=timestamp(3))
    assert [item.status for item in processed] == [
        PipelineProcessStatus.MARKET_INGESTED,
        PipelineProcessStatus.LIFECYCLE_RECORDED,
    ]
    manifest_path = recorder.finalize(
        MarketEventJournalSummary(
            finalized_at=timestamp(4),
            queue_drained=True,
            projection_digest={
                "bar": bars.digest,
                "book": books.digest,
                "health": health.snapshot().digest,
            },
        )
    )
    return recorder.session_dir, manifest_path


def test_finalized_journal_is_one_durable_timeline(tmp_path: Path):
    session_dir, manifest_path = finalized_session(tmp_path)

    records = [
        json.loads(line)
        for line in (session_dir / "records.jsonl").read_text().splitlines()
    ]
    manifest = json.loads(manifest_path.read_text())
    verification = verify_market_event_journal(session_dir)

    assert [record["record_type"] for record in records] == [
        "INGRESS",
        "DISPOSITION",
        "SYSTEM_INCIDENT",
    ]
    assert [record["record_index"] for record in records] == [1, 2, 3]
    assert records[1]["ingress_record_index"] == 1
    assert records[1]["event_id"] == "tick-1"
    assert manifest["schema"] == JOURNAL_SCHEMA_VERSION
    assert manifest["status"] == JournalStatus.FINALIZED
    assert manifest["record_count"] == 3
    assert manifest["first_record_index"] == 1
    assert manifest["last_record_index"] == 3
    assert manifest["statistics"] == {
        "accepted": 1,
        "rejected": 0,
        "incidents": 1,
    }
    assert manifest["shutdown"]["queue_drained"] is True
    assert verification.valid is True
    assert verification.errors == ()
    assert verification.record_count == 3


def test_session_directory_is_exclusive_create(tmp_path: Path):
    _, recorder, _, _, _ = components(tmp_path)

    assert isinstance(recorder, MarketEventRecorder)

    with pytest.raises(FileExistsError):
        JsonlMarketEventRecorder(
            root=tmp_path / "records" / "market_events",
            session_id=SESSION_ID,
            session_date=SESSION_DATE,
            started_at=timestamp(0),
            producer_identity="pytest",
            source_mode="TEST",
        )

    recorder.close()


def test_fsync_failure_blocks_before_projection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    pipeline, recorder, bars, _, health = components(tmp_path)
    assert pipeline.submit_market(tick_envelope).accepted

    def fail_fsync(_: int) -> None:
        raise OSError("disk sync failed")

    monkeypatch.setattr("market_data.journal.os.fsync", fail_fsync)
    processed = pipeline.process_pending(occurred_at=timestamp(2))

    assert processed[0].status is PipelineProcessStatus.RECORDER_FAILED
    assert processed[0].ingest_result is None
    assert bars.bars("2330") == ()
    assert health.state is DataHealthState.BLOCKED
    assert DataHealthReason.RECORDER_FAILURE in health.snapshot().reasons
    recorder.close()


def test_disposition_fsync_failure_leaves_projection_but_blocks_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    pipeline, recorder, bars, _, health = components(tmp_path)
    assert pipeline.submit_market(tick_envelope).accepted
    real_fsync = os.fsync
    call_count = 0

    def fail_second_fsync(file_descriptor: int) -> None:
        nonlocal call_count
        call_count += 1
        if call_count == 2:
            raise OSError("disposition sync failed")
        real_fsync(file_descriptor)

    monkeypatch.setattr("market_data.journal.os.fsync", fail_second_fsync)
    processed = pipeline.process_pending(occurred_at=timestamp(2))

    assert processed[0].status is PipelineProcessStatus.RECORDER_FAILED
    assert processed[0].ingest_result is not None
    assert len(bars.bars("2330")) == 1
    assert health.state is DataHealthState.BLOCKED
    assert json.loads(recorder.manifest_path.read_text())["status"] == "INCOMPLETE"
    recorder.close()


class FailingFile:
    def __init__(self, wrapped, *, operation: str) -> None:
        self._wrapped = wrapped
        self._operation = operation

    def write(self, value: bytes):
        if self._operation == "write":
            raise OSError("disk full")
        return self._wrapped.write(value)

    def flush(self) -> None:
        if self._operation == "flush":
            raise OSError("flush failed")
        self._wrapped.flush()

    def fileno(self) -> int:
        return self._wrapped.fileno()

    def close(self) -> None:
        self._wrapped.close()


@pytest.mark.parametrize("operation", ("write", "flush"))
def test_write_or_flush_failure_blocks_before_projection(
    tmp_path: Path,
    operation: str,
):
    pipeline, recorder, bars, _, health = components(tmp_path)
    recorder._file = FailingFile(  # type: ignore[assignment]
        recorder._file,  # type: ignore[attr-defined]
        operation=operation,
    )
    assert pipeline.submit_market(tick_envelope).accepted

    processed = pipeline.process_pending(occurred_at=timestamp(2))

    assert processed[0].status is PipelineProcessStatus.RECORDER_FAILED
    assert processed[0].ingest_result is None
    assert bars.bars("2330") == ()
    assert health.state is DataHealthState.BLOCKED
    recorder.close()


def test_tampered_finalized_journal_fails_integrity_verification(tmp_path: Path):
    session_dir, _ = finalized_session(tmp_path)
    records_path = session_dir / "records.jsonl"
    records_path.write_bytes(records_path.read_bytes().replace(b"tick-1", b"tick-X"))

    verification = verify_market_event_journal(session_dir)

    assert verification.valid is False
    assert any("sha256" in error for error in verification.errors)


def test_record_index_violation_fails_even_with_updated_digest(tmp_path: Path):
    session_dir, manifest_path = finalized_session(tmp_path)
    records_path = session_dir / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines()]
    records[1]["record_index"] = 7
    encoded = b"".join(
        (
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        for record in records
    )
    records_path.write_bytes(encoded)
    manifest = json.loads(manifest_path.read_text())
    manifest["sha256"] = hashlib.sha256(encoded).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    )

    verification = verify_market_event_journal(session_dir)

    assert verification.valid is False
    assert any("record_index" in error for error in verification.errors)


def test_truncated_tail_fails_integrity_and_jsonl_boundary(tmp_path: Path):
    session_dir, _ = finalized_session(tmp_path)
    records_path = session_dir / "records.jsonl"
    records_path.write_bytes(records_path.read_bytes()[:-1])

    verification = verify_market_event_journal(session_dir)

    assert verification.valid is False
    assert any("sha256" in error for error in verification.errors)
    assert any("end with a newline" in error for error in verification.errors)


def test_event_schema_tamper_fails_after_manifest_digest_is_updated(tmp_path: Path):
    session_dir, manifest_path = finalized_session(tmp_path)
    records_path = session_dir / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines()]
    records[0]["event"]["event_type"] = "tick"
    encoded = b"".join(
        (
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
        ).encode()
        for record in records
    )
    records_path.write_bytes(encoded)
    manifest = json.loads(manifest_path.read_text())
    manifest["sha256"] = hashlib.sha256(encoded).hexdigest()
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    )

    verification = verify_market_event_journal(session_dir)

    assert verification.valid is False
    assert any("event contract violation" in error for error in verification.errors)


def test_finalized_manifest_cannot_claim_an_undrained_shutdown(tmp_path: Path):
    session_dir, manifest_path = finalized_session(tmp_path)
    manifest = json.loads(manifest_path.read_text())
    manifest["shutdown"]["queue_drained"] = False
    manifest_path.write_text(
        json.dumps(manifest, sort_keys=True, separators=(",", ":")) + "\n"
    )

    verification = verify_market_event_journal(session_dir)

    assert verification.valid is False
    assert any("drained shutdown" in error for error in verification.errors)


def test_explicit_incomplete_manifest_can_be_inspected_but_not_verified(
    tmp_path: Path,
):
    _, recorder, _, _, _ = components(tmp_path)
    recorder.record_lifecycle(record_index=0, message=lifecycle_message(1))
    recorder.mark_incomplete(reason="SIGTERM", occurred_at=timestamp(2))

    inspection = verify_market_event_journal(
        recorder.session_dir,
        require_finalized=False,
    )
    verification = verify_market_event_journal(recorder.session_dir)

    assert inspection.valid is True
    assert inspection.incident_count == 1
    assert verification.valid is False
    assert any("INCOMPLETE" in error for error in verification.errors)


def test_finalized_bytes_are_deterministic_across_runs(tmp_path: Path):
    first, first_manifest = finalized_session(tmp_path / "first")
    second, second_manifest = finalized_session(tmp_path / "second")

    assert (first / "records.jsonl").read_bytes() == (
        second / "records.jsonl"
    ).read_bytes()
    assert first_manifest.read_bytes() == second_manifest.read_bytes()


def test_incomplete_session_and_cli_return_nonzero(tmp_path: Path, capsys):
    _, recorder, _, _, _ = components(tmp_path)
    session_dir = recorder.session_dir
    recorder.close()

    verification = verify_market_event_journal(session_dir)
    exit_code = replay_cli_main(["--session", str(session_dir), "--verify"])
    output = capsys.readouterr()

    assert verification.valid is False
    assert any("INCOMPLETE" in error for error in verification.errors)
    assert exit_code != 0
    assert "match: false" in output.out


def test_replay_cli_integrity_verification_returns_zero(tmp_path: Path, capsys):
    session_dir, _ = finalized_session(tmp_path)

    exit_code = replay_cli_main(["--session", str(session_dir), "--verify"])
    output = capsys.readouterr()

    assert exit_code == 0
    assert "events: 1" in output.out
    assert "accepted: 1" in output.out
    assert "rejected: 0" in output.out
    assert "incidents: 1" in output.out
    assert "match: true" in output.out


def test_replay_cli_module_entrypoint_returns_zero(tmp_path: Path):
    session_dir, _ = finalized_session(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "market_data.replay_cli",
            "--session",
            str(session_dir),
            "--verify",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "verification: journal-integrity-v1" in completed.stdout
    assert "projection_replay: pending-complete-reference-contract" in (
        completed.stdout
    )
