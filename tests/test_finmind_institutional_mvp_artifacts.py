"""Immutability, replay, conflict, and tamper tests for daily MVP batches."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import threading
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest

from config import twse_calendar_2026
from config.institutional_mvp import (
    CALENDAR_SCOPE,
    EXPECTED_BASE_POLICY_DIGEST,
    EXPECTED_CALENDAR_SCHEMA_VERSION,
    EXPECTED_CALENDAR_SOURCE_DIGEST,
    EXPECTED_CALENDAR_TIMEZONE,
    load_daily_policy,
)
from institutional_data.serialization import canonical_json, sha256_text
from institutional_mvp.application import DailyInstitutionalMvpService
from institutional_mvp.artifacts import (
    DirectoryInstitutionalMvpCandidateBatchRepository,
    InstitutionalMvpArtifactConflict,
    InstitutionalMvpArtifactError,
)
from institutional_mvp.domain import (
    DailyRunStatus,
    InstitutionalMvpCandidateEntry,
    source_fingerprint,
    verify_candidate_batch_payload,
)
from institutional_mvp.ports import (
    InstitutionalFlowSnapshot,
    InstitutionalMvpArtifactPublication,
)
from market_data.equity_calendar import ReviewedEquityCalendar


TAIPEI = ZoneInfo("Asia/Taipei")
SOURCE_SESSION = date(2026, 8, 21)


def _payload(*, foreign_buy: int) -> bytes:
    return json.dumps(
        {
            "status": 200,
            "data": [
                {
                    "date": SOURCE_SESSION.isoformat(),
                    "stock_id": "1101",
                    "Foreign_Investor_buy": foreign_buy,
                    "Foreign_Investor_sell": 1,
                    "Investment_Trust_buy": 5,
                    "Investment_Trust_sell": 1,
                    "Dealer_buy": 0,
                    "Dealer_sell": 0,
                    "Dealer_self_buy": 2,
                    "Dealer_self_sell": 0,
                    "Dealer_Hedging_buy": 1,
                    "Dealer_Hedging_sell": 0,
                }
            ],
        },
        separators=(",", ":"),
    ).encode()


INFO = json.dumps(
    {
        "status": 200,
        "data": [
            {
                "date": "2026-01-01",
                "stock_id": "1101",
                "stock_name": "Company A",
                "type": "twse",
            }
        ],
    },
    separators=(",", ":"),
).encode()


class Provider:
    def __init__(self, foreign_buy: int) -> None:
        self.foreign_buy = foreign_buy

    def fetch_daily(self, source_session: date) -> InstitutionalFlowSnapshot:
        assert source_session == SOURCE_SESSION
        return InstitutionalFlowSnapshot(
            provider="FINMIND",
            source_version="FINMIND_API_V4",
            retrieved_at=datetime(2026, 8, 21, 18, self.foreign_buy, tzinfo=TAIPEI),
            wide_payload=_payload(foreign_buy=self.foreign_buy),
            stock_info_payload=INFO,
            wide_row_count=1,
            stock_info_row_count=1,
            usage_user_count_before=100,
            usage_request_limit=1000,
            usage_remaining_before=900,
        )


def _service(root: Path, provider: Provider, generated_minute: int) -> DailyInstitutionalMvpService:
    policy = load_daily_policy()
    return DailyInstitutionalMvpService(
        provider=provider,
        repository=_repository(root, policy.canonical_sha256),
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        policy=policy,
        expected_calendar_schema_version=EXPECTED_CALENDAR_SCHEMA_VERSION,
        expected_calendar_timezone=EXPECTED_CALENDAR_TIMEZONE,
        expected_calendar_source_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
        calendar_scope=CALENDAR_SCOPE,
        clock=lambda: datetime(2026, 8, 21, 19, generated_minute, tzinfo=TAIPEI),
    )


def _repository(
    root: Path, policy_digest: str | None = None
) -> DirectoryInstitutionalMvpCandidateBatchRepository:
    return DirectoryInstitutionalMvpCandidateBatchRepository(
        root,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        expected_policy_digest=policy_digest or load_daily_policy().canonical_sha256,
        expected_base_policy_digest=EXPECTED_BASE_POLICY_DIGEST,
        expected_calendar_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
    )


class CapturingRepository:
    def __init__(self) -> None:
        self.batch = None

    def put_immutable(self, batch):  # type: ignore[no-untyped-def]
        self.batch = batch
        return InstitutionalMvpArtifactPublication(
            status=DailyRunStatus.PUBLISHED,
            artifact_id=batch.artifact_id,
            artifact_digest=batch.artifact_digest,
            source_session=batch.source_session,
            target_session=batch.target_session,
            path=Path("unused"),
        )

    def get_by_target_session(self, target_session: date):  # type: ignore[no-untyped-def]
        raise NotImplementedError

    def get_by_digest(self, *, target_session: date, artifact_digest: str):  # type: ignore[no-untyped-def]
        raise NotImplementedError


def _capture_batch(provider: Provider, generated_minute: int):  # type: ignore[no-untyped-def]
    policy = load_daily_policy()
    repository = CapturingRepository()
    service = DailyInstitutionalMvpService(
        provider=provider,
        repository=repository,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        policy=policy,
        expected_calendar_schema_version=EXPECTED_CALENDAR_SCHEMA_VERSION,
        expected_calendar_timezone=EXPECTED_CALENDAR_TIMEZONE,
        expected_calendar_source_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
        calendar_scope=CALENDAR_SCOPE,
        clock=lambda: datetime(2026, 8, 21, 19, generated_minute, tzinfo=TAIPEI),
    )
    service.run(SOURCE_SESSION)
    assert repository.batch is not None
    return repository.batch


def test_same_source_bytes_replay_and_changed_bytes_append_conflict_revision(
    tmp_path: Path,
) -> None:
    first = _service(tmp_path, Provider(10), 0).run(SOURCE_SESSION)
    replay = _service(tmp_path, Provider(10), 1).run(SOURCE_SESSION)
    changed = _service(tmp_path, Provider(11), 2).run(SOURCE_SESSION)

    assert first.status is DailyRunStatus.PUBLISHED
    assert replay.status is DailyRunStatus.IDEMPOTENT_REPLAY
    assert replay.artifact_digest == first.artifact_digest
    assert replay.path == first.path
    assert changed.status is DailyRunStatus.CONFLICT_REVISION_CREATED
    assert changed.artifact_digest != first.artifact_digest
    assert len(list(tmp_path.rglob("*.json"))) == 2

    repository = _repository(tmp_path)
    with pytest.raises(InstitutionalMvpArtifactConflict):
        repository.get_by_target_session(date(2026, 8, 24))
    assert (
        repository.get_by_digest(
            target_session=date(2026, 8, 24),
            artifact_digest=first.artifact_digest,
        )["artifact_id"]
        == first.artifact_id
    )


def test_same_source_fingerprint_with_changed_derivation_is_not_silent_replay(
    tmp_path: Path,
) -> None:
    original = _capture_batch(Provider(10), 0)
    entry = original.candidates[0]
    changed_entry = InstitutionalMvpCandidateEntry.create(
        rank=entry.rank,
        symbol=entry.symbol,
        name="Changed derivation",
        market=entry.market,
        source_session=entry.source_session,
        target_session=entry.target_session,
        expires_at=entry.expires_at,
    )
    changed = replace(original, candidates=(changed_entry,))
    repository = _repository(tmp_path)

    first = repository.put_immutable(original)
    second = repository.put_immutable(changed)

    assert first.status is DailyRunStatus.PUBLISHED
    assert second.status is DailyRunStatus.CONFLICT_REVISION_CREATED
    assert second.artifact_digest != first.artifact_digest


def test_published_artifact_is_read_only_and_tampering_is_rejected(
    tmp_path: Path,
) -> None:
    publication = _service(tmp_path, Provider(10), 0).run(SOURCE_SESSION)
    mode = stat.S_IMODE(publication.path.stat().st_mode)
    assert mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH) == 0

    payload = json.loads(publication.path.read_text(encoding="utf-8"))
    payload["target_session"] = "2026-08-25"
    os.chmod(publication.path, 0o640)
    publication.path.write_text(canonical_json(payload) + "\n", encoding="utf-8")

    repository = _repository(tmp_path)
    with pytest.raises(InstitutionalMvpArtifactError):
        repository.get_by_digest(
            target_session=date(2026, 8, 24),
            artifact_digest=publication.artifact_digest,
        )


@pytest.mark.parametrize("digest", ["*", "A" * 64, "../" + "0" * 61, "0" * 63])
def test_exact_digest_lookup_rejects_non_lowercase_sha256(
    tmp_path: Path, digest: str
) -> None:
    _service(tmp_path, Provider(10), 0).run(SOURCE_SESSION)

    with pytest.raises(ValueError, match="64 lowercase"):
        _repository(tmp_path).get_by_digest(
            target_session=date(2026, 8, 24), artifact_digest=digest
        )


def test_rehashed_semantic_tampering_is_rejected(tmp_path: Path) -> None:
    publication = _service(tmp_path, Provider(10), 0).run(SOURCE_SESSION)
    payload = json.loads(publication.path.read_text(encoding="utf-8"))
    payload["candidate_observation"]["count"] = 999
    _rehash_artifact(payload)

    with pytest.raises(ValueError, match="count differs"):
        verify_candidate_batch_payload(
            payload,
            next_session_resolver=ReviewedEquityCalendar.from_path(
                twse_calendar_2026.PATH
            ).next_trading_day,
        )

    payload = json.loads(publication.path.read_text(encoding="utf-8"))
    payload["candidate_policy"]["execution_permissions"][
        "order_submission_allowed"
    ] = True
    payload["execution_permissions"]["order_submission_allowed"] = True
    _rehash_policy_and_artifact(payload)

    with pytest.raises(ValueError, match="non-observation authority"):
        verify_candidate_batch_payload(
            payload,
            next_session_resolver=ReviewedEquityCalendar.from_path(
                twse_calendar_2026.PATH
            ).next_trading_day,
        )

    payload = json.loads(publication.path.read_text(encoding="utf-8"))
    payload["source_evidence"]["candidate_count_before_limit"] = 999
    _rehash_artifact(payload)

    with pytest.raises(ValueError, match="candidate counts"):
        verify_candidate_batch_payload(
            payload,
            next_session_resolver=ReviewedEquityCalendar.from_path(
                twse_calendar_2026.PATH
            ).next_trading_day,
        )


def test_rehashed_truncated_candidate_projection_is_rejected(tmp_path: Path) -> None:
    publication = _service(tmp_path, Provider(10), 0).run(SOURCE_SESSION)
    payload = json.loads(publication.path.read_text(encoding="utf-8"))
    source = payload["source_evidence"]
    source["flow_source_rows"] = 2
    source["mapped_flow_rows"] = 2
    source["candidate_count_before_limit"] = 2
    _rehash_artifact(payload)

    with pytest.raises(ValueError, match="complete policy projection"):
        verify_candidate_batch_payload(
            payload,
            next_session_resolver=ReviewedEquityCalendar.from_path(
                twse_calendar_2026.PATH
            ).next_trading_day,
        )


def test_rehashed_non_next_target_session_is_rejected(tmp_path: Path) -> None:
    publication = _service(tmp_path, Provider(10), 0).run(SOURCE_SESSION)
    payload = json.loads(publication.path.read_text(encoding="utf-8"))
    payload["target_session"] = "2026-08-25"
    payload["expires_at"] = "2026-08-25T13:30:00+08:00"
    candidate = payload["candidate_observation"]["candidates"][0]
    candidate["target_session"] = payload["target_session"]
    candidate["expires_at"] = payload["expires_at"]
    candidate_body = dict(candidate)
    candidate_body.pop("entry_digest")
    candidate["entry_digest"] = sha256_text(canonical_json(candidate_body))
    _rehash_policy_and_artifact(payload)

    with pytest.raises(ValueError, match="reviewed next session"):
        verify_candidate_batch_payload(
            payload,
            next_session_resolver=ReviewedEquityCalendar.from_path(
                twse_calendar_2026.PATH
            ).next_trading_day,
        )

    tampered_directory = tmp_path / "2026-08-25" / SOURCE_SESSION.isoformat()
    tampered_directory.mkdir(parents=True)
    tampered_path = tampered_directory / f"{payload['artifact_digest']}.json"
    tampered_path.write_text(canonical_json(payload) + "\n", encoding="utf-8")
    with pytest.raises(InstitutionalMvpArtifactError, match="verification failed"):
        _repository(tmp_path).get_by_target_session(date(2026, 8, 25))


def test_rehashed_non_taipei_expiry_is_rejected(tmp_path: Path) -> None:
    publication = _service(tmp_path, Provider(10), 0).run(SOURCE_SESSION)
    payload = json.loads(publication.path.read_text(encoding="utf-8"))
    payload["expires_at"] = "2026-08-24T13:30:00+00:00"
    candidate = payload["candidate_observation"]["candidates"][0]
    candidate["expires_at"] = payload["expires_at"]
    candidate_body = dict(candidate)
    candidate_body.pop("entry_digest")
    candidate["entry_digest"] = sha256_text(canonical_json(candidate_body))
    _rehash_artifact(payload)

    with pytest.raises(ValueError, match="Asia/Taipei"):
        verify_candidate_batch_payload(
            payload,
            next_session_resolver=ReviewedEquityCalendar.from_path(
                twse_calendar_2026.PATH
            ).next_trading_day,
        )


def test_mismatched_expected_lineage_publishes_no_artifact(tmp_path: Path) -> None:
    batch = _capture_batch(Provider(10), 0)
    repository = DirectoryInstitutionalMvpCandidateBatchRepository(
        tmp_path,
        calendar=ReviewedEquityCalendar.from_path(twse_calendar_2026.PATH),
        expected_policy_digest="0" * 64,
        expected_base_policy_digest=EXPECTED_BASE_POLICY_DIGEST,
        expected_calendar_digest=EXPECTED_CALENDAR_SOURCE_DIGEST,
    )

    with pytest.raises(ValueError, match="reviewed daily policy"):
        repository.put_immutable(batch)

    assert list(tmp_path.rglob("*.json")) == []
    assert list(tmp_path.rglob("*.tmp")) == []


def test_publish_interruption_leaves_no_artifact_or_temporary_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_link = os.link

    def interrupt_link(source: Path, destination: Path) -> None:
        real_link(source, destination)
        raise KeyboardInterrupt

    monkeypatch.setattr("institutional_mvp.artifacts.os.link", interrupt_link)

    with pytest.raises(KeyboardInterrupt):
        _service(tmp_path, Provider(10), 0).run(SOURCE_SESSION)

    assert list(tmp_path.rglob("*.json")) == []
    assert list(tmp_path.rglob("*.tmp")) == []


def test_reader_cannot_observe_publication_that_is_rolled_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = _repository(tmp_path)
    batch = _capture_batch(Provider(10), 0)
    linked = threading.Event()
    release_writer = threading.Event()
    reader_started = threading.Event()
    reader_attempted_shared = threading.Event()
    reader_done = threading.Event()
    original_fsync = DirectoryInstitutionalMvpCandidateBatchRepository._fsync_directory
    original_flock = fcntl.flock
    fsync_calls = 0
    writer_error: list[BaseException] = []
    reader_result: list[object] = []

    def fail_first_directory_fsync(path: Path) -> None:
        nonlocal fsync_calls
        fsync_calls += 1
        if fsync_calls == 1:
            linked.set()
            if not release_writer.wait(timeout=2):
                raise AssertionError("test did not release writer")
            raise OSError("simulated directory fsync failure")
        original_fsync(path)

    monkeypatch.setattr(
        DirectoryInstitutionalMvpCandidateBatchRepository,
        "_fsync_directory",
        staticmethod(fail_first_directory_fsync),
    )

    def observed_flock(descriptor: int, operation: int) -> None:
        if operation & fcntl.LOCK_SH:
            reader_attempted_shared.set()
        original_flock(descriptor, operation)

    monkeypatch.setattr("institutional_mvp.artifacts.fcntl.flock", observed_flock)

    def publish() -> None:
        try:
            repository.put_immutable(batch)
        except BaseException as error:
            writer_error.append(error)

    def read() -> None:
        reader_started.set()
        reader_result.append(
            repository.get_by_digest(
                target_session=batch.target_session,
                artifact_digest=batch.artifact_digest,
            )
        )
        reader_done.set()

    writer = threading.Thread(target=publish, daemon=True)
    writer.start()
    assert linked.wait(timeout=2)
    reader = threading.Thread(target=read, daemon=True)
    reader.start()
    try:
        assert reader_started.wait(timeout=2)
        assert reader_attempted_shared.wait(timeout=2)
        assert reader_done.is_set() is False
    finally:
        release_writer.set()
    writer.join(timeout=2)
    reader.join(timeout=2)

    assert writer.is_alive() is False
    assert reader.is_alive() is False
    assert len(writer_error) == 1
    assert isinstance(writer_error[0], OSError)
    assert reader_result == [None]
    assert list(tmp_path.rglob("*.json")) == []


def _rehash_artifact(payload: dict[str, object]) -> None:
    identity = dict(payload)
    identity.pop("artifact_digest")
    identity.pop("artifact_id")
    digest = sha256_text(canonical_json(identity))
    payload["artifact_digest"] = digest
    payload["artifact_id"] = (
        "finmind-institutional-mvp-batch-v1-"
        f"{payload['target_session']}-{digest[:16]}"
    )


def _rehash_policy_and_artifact(payload: dict[str, object]) -> None:
    policy = payload["candidate_policy"]
    assert isinstance(policy, dict)
    policy_body = dict(policy)
    policy_body.pop("canonical_sha256")
    policy_digest = sha256_text(canonical_json(policy_body))
    policy["canonical_sha256"] = policy_digest
    calendar = payload["calendar_evidence"]
    source = payload["source_evidence"]
    assert isinstance(calendar, dict)
    assert isinstance(source, dict)
    payload["source_fingerprint"] = source_fingerprint(
        source_session=date.fromisoformat(str(payload["source_session"])),
        target_session=date.fromisoformat(str(payload["target_session"])),
        policy_digest=policy_digest,
        calendar_digest=str(calendar["source_digest"]),
        provider=str(source["provider"]),
        source_version=str(source["source_version"]),
        flow_raw_sha256=str(source["flow_raw_sha256"]),
        stock_info_raw_sha256=str(source["stock_info_raw_sha256"]),
    )
    _rehash_artifact(payload)
