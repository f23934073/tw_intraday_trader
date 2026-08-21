import hashlib
import json
import subprocess
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from market_data.events import (
    AggressorSide,
    EventEnvelope,
    InstrumentReference,
    MARKET_EVENT_SCHEMA_VERSION,
    MarketEventSource,
    MarketStreamKind,
    TickEvent,
)
from market_data.exact_replay import (
    ExactProjectionReplayRuntime,
    load_exact_replay_inputs,
    verify_exact_projection_replay,
)
from market_data.health import DataHealth
from market_data.ingestion import MarketDataIngestor
from market_data.ingress import BoundedIngressQueue
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.journal import (
    JsonlMarketEventRecorder,
    MarketEventJournalSummary,
)
from market_data.order_book_store import OrderBookStore
from market_data.pipeline import CanonicalMarketDataPipeline
from market_data.replay_cli import main as replay_cli_main


SESSION_DATE = date(2026, 8, 20)
SESSION_ID = "exact-replay-test"
TAIPEI = ZoneInfo("Asia/Taipei")


def timestamp(second: int) -> datetime:
    return datetime(2026, 8, 20, 9, 0, second, tzinfo=TAIPEI)


def tick_envelope(sequence: int) -> EventEnvelope:
    event_at = timestamp(sequence)
    payload = TickEvent(
        event_id=f"tick-{sequence}",
        source=MarketEventSource.TICK,
        symbol="2330",
        session_date=SESSION_DATE,
        event_time=event_at,
        received_at=event_at,
        ingress_sequence=sequence,
        price=Decimal("1180"),
        tick_volume_lots=2,
        total_volume_lots=100 + sequence,
        average_price=Decimal("1179.5"),
        intraday_high=Decimal("1181"),
        intraday_low=Decimal("1178"),
        raw_tick_type=1,
        aggressor_side=AggressorSide.BUY,
        buy_aggressor_total_lots=60,
        sell_aggressor_total_lots=40,
        suspended=False,
        simulated_trade=False,
        intraday_odd=False,
    )
    return EventEnvelope(
        event_id=payload.event_id,
        schema_version=MARKET_EVENT_SCHEMA_VERSION,
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        source=MarketEventSource.TICK,
        source_mode="QUOTE_BINDING",
        stream_kind=MarketStreamKind.TICK,
        symbol="2330",
        event_at=event_at,
        received_at=event_at,
        ingress_sequence=sequence,
        source_identity=f"shioaji:tick:{sequence}",
        payload=payload,
    )


def canonical_bytes(value: object) -> bytes:
    return (
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
        + b"\n"
    )


def content_digest(value: dict[str, object], excluded: set[str]) -> str:
    payload = {key: item for key, item in value.items() if key not in excluded}
    return hashlib.sha256(canonical_bytes(payload).rstrip(b"\n")).hexdigest()


def write_artifact(path: Path, value: dict[str, object]) -> None:
    path.write_bytes(canonical_bytes(value))


def reference_artifact(path: Path) -> dict[str, object]:
    raw: dict[str, object] = {
        "schema": "instrument-reference-v1",
        "artifact_id": "reference-test-artifact",
        "session_id": SESSION_ID,
        "session_date": SESSION_DATE.isoformat(),
        "timezone": "Asia/Taipei",
        "status": "FINALIZED",
        "source": {
            "provider": "SHIOAJI",
            "source_mode": "CONTRACT_LOOKUP",
            "source_identity": "pytest-contracts",
            "captured_at": timestamp(0).isoformat(),
        },
        "reference_count": 1,
        "content_sha256": "",
        "references": [
            {
                "instrument_id": "TWSE:2330",
                "symbol": "2330",
                "exchange": "TWSE",
                "security_type": "STOCK",
                "name": "台積電",
                "valid_from": SESSION_DATE.isoformat(),
                "valid_to": SESSION_DATE.isoformat(),
                "reference_price": "1180",
                "limit_up_price": "1295",
                "limit_down_price": "1065",
                "price_limit_applies": True,
                "trading_unit_shares": 1000,
                "source_updated_at": SESSION_DATE.isoformat(),
                "source_identity": "TSE:2330",
            }
        ],
    }
    raw["content_sha256"] = content_digest(
        raw,
        {"status", "reference_count", "content_sha256"},
    )
    write_artifact(path, raw)
    return raw


def bootstrap_artifact(path: Path) -> dict[str, object]:
    raw: dict[str, object] = {
        "schema": "bootstrap-snapshot-v1",
        "artifact_id": "bootstrap-test-artifact",
        "session_id": SESSION_ID,
        "session_date": SESSION_DATE.isoformat(),
        "timezone": "Asia/Taipei",
        "status": "FINALIZED",
        "source": {
            "provider": "SHIOAJI",
            "source_mode": "SNAPSHOT_BOOTSTRAP",
            "source_identity": "pytest-snapshot",
        },
        "captured_at": timestamp(0).isoformat(),
        "received_at": timestamp(0).isoformat(),
        "journal_boundary": {
            "first_record_index": 1,
            "first_ingress_sequence": 1,
            "projection_started_at": timestamp(0).isoformat(),
        },
        "calendar": {
            "calendar_id": "TWSE",
            "calendar_version": "2026-v1",
            "session_phase": "OPEN",
            "scheduled_open": timestamp(0).isoformat(),
            "scheduled_close": datetime(
                2026,
                8,
                20,
                13,
                30,
                tzinfo=TAIPEI,
            ).isoformat(),
        },
        "coverage": {
            "required_instrument_ids": ["TWSE:2330"],
            "captured_instrument_ids": ["TWSE:2330"],
            "missing_instrument_ids": [],
        },
        "subscriptions": [
            {
                "instrument_id": "TWSE:2330",
                "stream_kind": "TICK",
                "state": "ACKED",
                "effective_at": timestamp(0).isoformat(),
                "evidence_identity": "pytest-subscription-ack",
            }
        ],
        "symbols": [
            {
                "instrument_id": "TWSE:2330",
                "symbol": "2330",
                "prior_session_date": "2026-08-19",
                "previous_close": "1175",
                "previous_session_volume_lots": 27543,
                "source_identity": "snapshot:TSE:2330",
            }
        ],
        "projection_seed_mode": "EMPTY_SESSION",
        "content_sha256": "",
    }
    raw["content_sha256"] = content_digest(
        raw,
        {"status", "content_sha256"},
    )
    write_artifact(path, raw)
    return raw


def runtime_reference_digest() -> str:
    store = InstrumentReferenceStore(SESSION_DATE)
    store.put(
        InstrumentReference(
            symbol="2330",
            exchange="TWSE",
            session_date=SESSION_DATE,
            reference_price=Decimal("1180"),
            limit_up_price=Decimal("1295"),
            limit_down_price=Decimal("1065"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=SESSION_DATE,
        )
    )
    return store.digest


def projection_state_artifact(
    path: Path,
    *,
    journal_sha256: str,
    reference_sha256: str,
    bootstrap_sha256: str,
    digest_set: dict[str, object],
) -> dict[str, object]:
    empty_bar = IntradayBarStore(SESSION_DATE, retention=timedelta(minutes=20))
    empty_book = OrderBookStore(SESSION_DATE, retention=timedelta(minutes=20))
    raw: dict[str, object] = {
        "schema": "projection-state-v1",
        "artifact_id": "projection-state-test-artifact",
        "session_id": SESSION_ID,
        "session_date": SESSION_DATE.isoformat(),
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
            "replay_engine": "exact-projection-replay-v1",
        },
        "initialization": {
            "mode": "EMPTY_SESSION",
            "initialized_at": timestamp(0).isoformat(),
            "retention_seconds": 1200,
            "reference_store": {
                "expected_initial_digest": runtime_reference_digest(),
            },
            "bar": {
                "mode": "EMPTY",
                "finalized": False,
                "expected_initial_digest": empty_bar.digest,
            },
            "book": {
                "mode": "EMPTY",
                "finalized": False,
                "expected_initial_digest": empty_book.digest,
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
                "as_of": timestamp(0).isoformat(),
            },
            "ready_transition": {
                "occurred_at": timestamp(0).isoformat(),
                "evidence": "pytest-artifacts-validated",
            },
        },
        "expected_final": {
            "repeat_count": 10,
            "digest_set": digest_set,
        },
        "content_sha256": "",
    }
    raw["content_sha256"] = content_digest(
        raw,
        {"status", "content_sha256"},
    )
    write_artifact(path, raw)
    return raw


def finalized_journal(tmp_path: Path) -> tuple[Path, dict[str, object]]:
    references = InstrumentReferenceStore(SESSION_DATE)
    references.put(
        InstrumentReference(
            symbol="2330",
            exchange="TWSE",
            session_date=SESSION_DATE,
            reference_price=Decimal("1180"),
            limit_up_price=Decimal("1295"),
            limit_down_price=Decimal("1065"),
            price_limit_applies=True,
            trading_unit_shares=1000,
            source_updated_at=SESSION_DATE,
        )
    )
    bars = IntradayBarStore(SESSION_DATE, retention=timedelta(minutes=20))
    books = OrderBookStore(SESSION_DATE, retention=timedelta(minutes=20))
    health = DataHealth(SESSION_DATE, started_at=timestamp(0))
    health.mark_ready(
        occurred_at=timestamp(0),
        evidence="pytest-artifacts-validated",
    )
    recorder = JsonlMarketEventRecorder(
        root=tmp_path / "records" / "market_events",
        session_id=SESSION_ID,
        session_date=SESSION_DATE,
        started_at=timestamp(0),
        producer_identity="pytest",
        source_mode="TEST",
    )
    pipeline = CanonicalMarketDataPipeline(
        queue=BoundedIngressQueue(capacity=8, control_reserve=1, health=health),
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
    assert pipeline.submit_market(tick_envelope).accepted
    processed = pipeline.process_pending(occurred_at=timestamp(2))
    assert len(processed) == 1
    manifest_path = recorder.finalize(
        MarketEventJournalSummary(
            finalized_at=timestamp(3),
            queue_drained=True,
            projection_digest={
                "bar": bars.digest,
                "book": books.digest,
                "health": health.snapshot().digest,
            },
        )
    )
    return recorder.session_dir, json.loads(manifest_path.read_text())


def exact_artifacts(tmp_path: Path):
    session_dir, manifest = finalized_journal(tmp_path)
    reference_path = session_dir / "instrument_reference.json"
    bootstrap_path = session_dir / "bootstrap_snapshot.json"
    projection_path = session_dir / "projection_state.json"
    reference = reference_artifact(reference_path)
    bootstrap = bootstrap_artifact(bootstrap_path)
    empty_digest_set = {
        "digest_set_schema": "projection-digest-set-v1",
        "disposition_v1": {
            "contract": "ingest-disposition-digest-v1",
            "owner": "MarketDataIngestor",
            "sha256": "0" * 64,
        },
        "bar_v1": {
            "contract": "bar-projection-digest-v1",
            "owner": "IntradayBarStore",
            "sha256": manifest["projection_digest"]["bar"],
        },
        "book_v1": {
            "contract": "book-projection-digest-v1",
            "owner": "OrderBookStore",
            "sha256": manifest["projection_digest"]["book"],
        },
        "health_v1": {
            "contract": "data-health-replay-v1",
            "owner": "ReplaySemanticHealthProjection",
            "sha256": "0" * 64,
        },
    }
    projection_state_artifact(
        projection_path,
        journal_sha256=str(manifest["sha256"]),
        reference_sha256=str(reference["content_sha256"]),
        bootstrap_sha256=str(bootstrap["content_sha256"]),
        digest_set=empty_digest_set,
    )
    inputs = load_exact_replay_inputs(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )
    actual = ExactProjectionReplayRuntime().reconstruct(inputs)
    projection_state_artifact(
        projection_path,
        journal_sha256=str(manifest["sha256"]),
        reference_sha256=str(reference["content_sha256"]),
        bootstrap_sha256=str(bootstrap["content_sha256"]),
        digest_set=actual.to_contract_dict(),
    )
    return session_dir, bootstrap_path, reference_path


def test_exact_projection_replay_matches_all_versioned_digests(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)

    result = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )

    assert result.valid is True
    assert result.errors == ()
    assert result.repeat_count == 10
    assert all(item.match for item in result.comparisons)
    assert {item.name for item in result.comparisons} == {
        "disposition_v1",
        "bar_v1",
        "book_v1",
        "health_v1",
    }


def test_exact_cli_reports_success(tmp_path: Path, capsys):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)

    exit_code = replay_cli_main(
        [
            "--session",
            str(session_dir),
            "--bootstrap",
            str(bootstrap_path),
            "--instrument-reference",
            str(reference_path),
            "--verify",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "projection_replay: PASS" in output
    assert "disposition_v1: MATCH" in output
    assert "bar_v1: MATCH" in output
    assert "book_v1: MATCH" in output
    assert "health_v1: MATCH" in output


def test_exact_cli_module_entrypoint_reports_success(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)

    completed = subprocess.run(
        [
            sys.executable,
            "-m",
            "market_data.replay_cli",
            "--session",
            str(session_dir),
            "--bootstrap",
            str(bootstrap_path),
            "--instrument-reference",
            str(reference_path),
            "--verify",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "projection_replay: PASS" in completed.stdout
    assert "health_v1: MATCH" in completed.stdout


def test_missing_bootstrap_never_falls_back(tmp_path: Path, capsys):
    session_dir, _, reference_path = exact_artifacts(tmp_path)
    missing = session_dir / "missing-bootstrap.json"

    exit_code = replay_cli_main(
        [
            "--session",
            str(session_dir),
            "--bootstrap",
            str(missing),
            "--instrument-reference",
            str(reference_path),
            "--verify",
        ]
    )
    output = capsys.readouterr().out

    assert exit_code != 0
    assert "projection_replay: FAILED" in output
    assert "MISSING_BOOTSTRAP_ARTIFACT" in output


def test_tampered_reference_fails_before_projection(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)
    raw = json.loads(reference_path.read_text())
    raw["references"][0]["name"] = "tampered"
    write_artifact(reference_path, raw)

    result = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )

    assert result.valid is False
    assert result.actual is None
    assert any("INPUT_DIGEST_MISMATCH" in error for error in result.errors)


def test_incomplete_or_tampered_journal_fails_before_projection(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)
    manifest_path = session_dir / "manifest.json"
    raw = json.loads(manifest_path.read_text())
    raw["status"] = "INCOMPLETE"
    raw["incomplete_reason"] = "TEST_INTERRUPTION"
    write_artifact(manifest_path, raw)

    result = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )

    assert result.valid is False
    assert result.actual is None
    assert any("INCOMPLETE_REPLAY_INPUT" in error for error in result.errors)


def test_final_digest_mismatch_is_honest_about_divergence(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)
    projection_path = session_dir / "projection_state.json"
    raw = json.loads(projection_path.read_text())
    raw["expected_final"]["digest_set"]["bar_v1"]["sha256"] = "f" * 64
    raw["content_sha256"] = content_digest(
        raw,
        {"status", "content_sha256"},
    )
    write_artifact(projection_path, raw)
    manifest_path = session_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["projection_digest"]["bar"] = "f" * 64
    write_artifact(manifest_path, manifest)

    result = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )

    comparison = next(item for item in result.comparisons if item.name == "bar_v1")
    assert result.valid is False
    assert comparison.match is False
    assert comparison.first_divergence == "UNKNOWN_NOT_RECORDED"


def test_records_sha_mismatch_fails_before_projection(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)
    records_path = session_dir / "records.jsonl"
    records_path.write_bytes(records_path.read_bytes() + b"\n")

    result = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )

    assert result.valid is False
    assert result.actual is None
    assert any("JOURNAL_INTEGRITY_FAILED" in error for error in result.errors)


def test_projection_version_mismatch_fails_before_projection(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)
    projection_path = session_dir / "projection_state.json"
    raw = json.loads(projection_path.read_text())
    raw["versions"]["bar_projection"] = "bar-projection-digest-v2"
    raw["content_sha256"] = content_digest(
        raw,
        {"status", "content_sha256"},
    )
    write_artifact(projection_path, raw)

    result = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )

    assert result.valid is False
    assert result.actual is None
    assert any("PROJECTION_VERSION_MISMATCH" in error for error in result.errors)


def test_initial_projection_digest_mismatch_fails_closed(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)
    projection_path = session_dir / "projection_state.json"
    raw = json.loads(projection_path.read_text())
    raw["initialization"]["bar"]["expected_initial_digest"] = "f" * 64
    raw["content_sha256"] = content_digest(
        raw,
        {"status", "content_sha256"},
    )
    write_artifact(projection_path, raw)

    result = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )

    assert result.valid is False
    assert result.actual is None
    assert any("INITIAL_STATE_DIGEST_MISMATCH" in error for error in result.errors)


def test_recorded_disposition_mismatch_reports_exact_records(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)
    records_path = session_dir / "records.jsonl"
    records = [json.loads(line) for line in records_path.read_text().splitlines()]
    records[1]["result"]["reason"] = "tampered-disposition"
    records_bytes = b"".join(canonical_bytes(record) for record in records)
    records_path.write_bytes(records_bytes)
    journal_sha256 = hashlib.sha256(records_bytes).hexdigest()

    manifest_path = session_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["sha256"] = journal_sha256
    write_artifact(manifest_path, manifest)

    projection_path = session_dir / "projection_state.json"
    projection = json.loads(projection_path.read_text())
    projection["input_digests"]["journal_sha256"] = journal_sha256
    projection["content_sha256"] = content_digest(
        projection,
        {"status", "content_sha256"},
    )
    write_artifact(projection_path, projection)

    result = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )

    assert result.valid is False
    assert result.actual is None
    assert result.errors == (
        "DISPOSITION_MISMATCH: record_index=2, ingress_record_index=1",
    )


def test_runtime_health_digest_is_not_replay_truth(tmp_path: Path):
    session_dir, bootstrap_path, reference_path = exact_artifacts(tmp_path)
    manifest_path = session_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["projection_digest"]["health"] = "f" * 64
    write_artifact(manifest_path, manifest)

    result = verify_exact_projection_replay(
        session_dir=session_dir,
        bootstrap_path=bootstrap_path,
        instrument_reference_path=reference_path,
    )

    assert result.valid is True
    health = next(item for item in result.comparisons if item.name == "health_v1")
    assert health.match is True
