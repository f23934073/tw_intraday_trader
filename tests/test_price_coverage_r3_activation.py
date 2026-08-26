from __future__ import annotations

import hashlib
import sys
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from zoneinfo import ZoneInfo

import pytest

from backtest.domain import canonical_json
from backtest.historical_download import (
    HistoricalDownloadPaused,
    ResumableHistoricalDownloader,
)
from backtest.price_coverage_activation import (
    ACTIVATION_STATUS,
    PriceCoverageActivationError,
    VerifiedPriceCoverageActivation,
    build_price_coverage_activation,
    verify_price_coverage_activation,
)
from backtest.price_coverage_initialization import (
    ContractTarget,
    persist_fresh_job_exactly_once,
    prepare_fresh_job,
)
from backtest.repository import BacktestIdempotencyConflict
from backtest.sqlite_repository import SQLiteBacktestRepository
from market_data.provider import MarketDataLimitReached
from scripts import run_price_coverage_r3_scan


ROOT = Path(__file__).resolve().parents[1]
ACQUISITION = ROOT / "research/institutional_evaluation/acquisition"
TAIPEI = ZoneInfo("Asia/Taipei")
ACTIVATION_DIGEST = "a" * 64


def _prepared():  # type: ignore[no-untyped-def]
    target_path = ACQUISITION / "price_coverage_target_order_v1_2026-08-26-r3.json"
    target = __import__("json").loads(target_path.read_text(encoding="utf-8"))
    return prepare_fresh_job(
        targets=tuple(
            ContractTarget(row["symbol"], row["name"], row["market"])
            for row in target["targets"]
        ),
        provider_environment_identity="shioaji:1.7.2:simulation=true",
        end_date=date(2026, 8, 18),
    )


def _stored_prepared_job() -> dict[str, object]:
    prepared = _prepared()
    return {
        "job_id": prepared.job_id,
        "kind": "PRICE_COVERAGE_PREPARED",
        "status": "PREPARED",
        "request": prepared.request,
        "resource_id": None,
        "progress": 0.0,
        "progress_message": (
            "Fresh r3 prepared; generic Kbar resume prohibited; "
            "dedicated activation required"
        ),
        "created_at": "2026-08-26T09:14:41.094249+08:00",
        "updated_at": "2026-08-26 01:30:53.833323+00",
        "error_message": None,
    }


def _canonical_digest(payload: object) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def test_repository_activation_is_exact_idempotent_compare_and_set() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        repository = SQLiteBacktestRepository(Path(directory) / "backtest.sqlite3")
        prepared = _prepared()
        try:
            persist_fresh_job_exactly_once(
                repository=repository,
                prepared=prepared,
                created_at=datetime(2026, 8, 26, 9, 14, tzinfo=TAIPEI),
            )
            activated, replayed = repository.activate_price_coverage_scan_job(
                prepared.job_id,
                expected_request_digest=prepared.request_canonical_sha256,
                activation_digest=ACTIVATION_DIGEST,
            )
            replay, replayed_again = repository.activate_price_coverage_scan_job(
                prepared.job_id,
                expected_request_digest=prepared.request_canonical_sha256,
                activation_digest=ACTIVATION_DIGEST,
            )

            assert replayed is False
            assert replayed_again is True
            assert activated == replay
            assert activated["kind"] == "PRICE_COVERAGE_SCAN"
            assert activated["status"] == "QUEUED"
            assert activated["progress_message"].startswith(
                f"[PRICE_COVERAGE_ACTIVATION={ACTIVATION_DIGEST}]"
            )
            with pytest.raises(BacktestIdempotencyConflict, match="different activation"):
                repository.activate_price_coverage_scan_job(
                    prepared.job_id,
                    expected_request_digest=prepared.request_canonical_sha256,
                    activation_digest="b" * 64,
                )
        finally:
            repository.close()


def test_prepared_job_rejects_partition_before_activation() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        repository = SQLiteBacktestRepository(Path(directory) / "backtest.sqlite3")
        prepared = _prepared()
        try:
            persist_fresh_job_exactly_once(
                repository=repository,
                prepared=prepared,
                created_at=datetime(2026, 8, 26, 9, 14, tzinfo=TAIPEI),
            )
            with pytest.raises(ValueError, match="PREPARED"):
                repository.upsert_history_partition(
                    {
                        "job_id": prepared.job_id,
                        "symbol": "1101",
                        "name": "台泥",
                        "market": "TWSE",
                        "bar_count": 0,
                        "bars_sha256": hashlib.sha256(b"").hexdigest(),
                        "bars_payload": b"",
                        "error_message": "[PRICE_DATA_UNAVAILABLE] PROVIDER_EMPTY_KBAR",
                    }
                )
        finally:
            repository.close()


class ShioajiProvider:
    pass


class _ScanRepository:
    def __init__(self) -> None:
        self.job = {
            "job_id": "job-r3",
            "kind": "PRICE_COVERAGE_SCAN",
            "status": "QUEUED",
            "request": {
                "provider": "ShioajiProvider",
                "lineage_mode": "FRESH_R3_NO_CHECKPOINT_REUSE",
                "coverage_scan_mode": True,
                "target_dataset_id": "dataset-r3",
                "start_date": "2026-08-17",
                "end_date": "2026-08-18",
                "instruments": [
                    {"symbol": "1240", "name": "A", "market": "TPEX"},
                    {"symbol": "2330", "name": "B", "market": "TWSE"},
                ],
            },
            "resource_id": None,
            "progress": 0.0,
            "progress_message": (
                f"[PRICE_COVERAGE_ACTIVATION={ACTIVATION_DIGEST}] queued"
            ),
            "error_message": None,
        }
        self.partitions: list[dict[str, object]] = []
        self.dataset_calls = 0
        self.payload_reads = 0

    def get_job(self, _job_id: str) -> dict[str, object]:
        return dict(self.job)

    def update_job(self, _job_id: str, **changes: object) -> dict[str, object]:
        self.job.update(changes)
        return dict(self.job)

    def list_history_partitions(self, _job_id: str) -> list[dict[str, object]]:
        return [dict(row) for row in self.partitions]

    def upsert_history_partition(self, partition: dict[str, object]) -> None:
        self.partitions.append(dict(partition))

    def iter_history_partition_payloads(self, _job_id: str):  # type: ignore[no-untyped-def]
        self.payload_reads += 1
        raise AssertionError("raw coverage completion must not decode payloads")

    def upsert_dataset(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        self.dataset_calls += 1
        raise AssertionError("raw coverage completion must not create a Dataset")


class _ScanCatalog:
    def fetch_provider_bars(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        return ()

    def create_provider_dataset_from_partitions(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("raw coverage completion must not materialize a Dataset")


def test_dedicated_scan_stops_at_raw_inventory_without_dataset_or_payload_read() -> None:
    repository = _ScanRepository()
    downloader = ResumableHistoricalDownloader(
        provider=ShioajiProvider(),
        repository=repository,  # type: ignore[arg-type]
        catalog=_ScanCatalog(),  # type: ignore[arg-type]
        coverage_scan_mode=True,
    )

    summary = downloader.run_price_coverage_scan(
        "job-r3",
        activation_digest=ACTIVATION_DIGEST,
    )

    assert summary["status"] == "SCAN_COMPLETE"
    assert summary["dataset_materialized"] is False
    assert summary["observation_counts"] == {
        "NON_EMPTY_SUCCESS": 0,
        "PRICE_DATA_UNAVAILABLE": 2,
        "TEMPORARY_FETCH_FAILURE": 0,
        "SYMBOL_MAPPING_ERROR": 0,
        "UNKNOWN": 0,
    }
    assert repository.job["status"] == "SCAN_COMPLETE"
    assert repository.job["resource_id"] is None
    assert repository.payload_reads == 0
    assert repository.dataset_calls == 0


def test_rate_limit_pause_preserves_exact_activation_binding() -> None:
    repository = _ScanRepository()

    class _RateLimitedCatalog(_ScanCatalog):
        def fetch_provider_bars(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            raise MarketDataLimitReached("fixture quota")

    downloader = ResumableHistoricalDownloader(
        provider=ShioajiProvider(),
        repository=repository,  # type: ignore[arg-type]
        catalog=_RateLimitedCatalog(),  # type: ignore[arg-type]
        coverage_scan_mode=True,
    )

    with pytest.raises(HistoricalDownloadPaused, match="RATE_LIMITED"):
        downloader.run_price_coverage_scan(
            "job-r3",
            activation_digest=ACTIVATION_DIGEST,
        )

    assert repository.job["status"] == "PAUSED"
    assert repository.job["progress_message"].startswith(
        f"[PRICE_COVERAGE_ACTIVATION={ACTIVATION_DIGEST}]"
    )
    assert repository.partitions == []


def test_activation_verifier_rejects_rehashed_downstream_unlock(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = __import__("json").loads(
        (ACQUISITION / "price_coverage_target_order_v1_2026-08-26-r3.json").read_text(
            encoding="utf-8"
        )
    )
    quarantine = __import__("json").loads(
        (
            ACQUISITION
            / "price_coverage_scan_configuration_v2_2026-08-26-r3-rev2.json"
        ).read_text(encoding="utf-8")
    )
    job = _stored_prepared_job()
    activation = build_price_coverage_activation(
        job=job,
        source_snapshot={},
        authorized_at=datetime(2026, 8, 26, 12, 0, tzinfo=TAIPEI),
        authorized_by="research-owner",
    )
    activation["execution_lock"]["outcome_generation_allowed"] = True
    monkeypatch.setattr(
        "backtest.price_coverage_activation._verify_git_source_snapshot",
        lambda **_kwargs: None,
    )

    class _Repository:
        def get_job(self, _job_id: str) -> dict[str, object]:
            return job

        def list_history_partitions(self, _job_id: str) -> list[object]:
            return []

        def get_dataset(self, _dataset_id: str) -> None:
            raise KeyError

    with pytest.raises(PriceCoverageActivationError, match="downstream"):
        verify_price_coverage_activation(
            activation=activation,
            activation_digest=_canonical_digest(activation),
            target_manifest=target,
            quarantine_revision=quarantine,
            repository=_Repository(),
            source_root=ROOT,
        )


def test_activation_verifier_accepts_exact_artifact_and_prepared_job(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    target = __import__("json").loads(
        (ACQUISITION / "price_coverage_target_order_v1_2026-08-26-r3.json").read_text(
            encoding="utf-8"
        )
    )
    quarantine = __import__("json").loads(
        (
            ACQUISITION
            / "price_coverage_scan_configuration_v2_2026-08-26-r3-rev2.json"
        ).read_text(encoding="utf-8")
    )
    job = _stored_prepared_job()
    activation = build_price_coverage_activation(
        job=job,
        source_snapshot={},
        authorized_at=datetime(2026, 8, 26, 12, 0, tzinfo=TAIPEI),
        authorized_by="research-owner",
    )
    monkeypatch.setattr(
        "backtest.price_coverage_activation._verify_git_source_snapshot",
        lambda **_kwargs: None,
    )

    class _Repository:
        def get_job(self, _job_id: str) -> dict[str, object]:
            return job

        def list_history_partitions(self, _job_id: str) -> list[object]:
            return []

        def get_dataset(self, _dataset_id: str) -> None:
            raise KeyError

    digest = _canonical_digest(activation)
    verified = verify_price_coverage_activation(
        activation=activation,
        activation_digest=digest,
        target_manifest=target,
        quarantine_revision=quarantine,
        repository=_Repository(),
        source_root=ROOT,
    )

    assert verified.activation_digest == digest
    assert verified.job_id == job["job_id"]


def test_runner_missing_activation_fails_before_repository_and_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider_builds = 0
    repository_builds = 0

    class _Store:
        def load(self, name: str) -> dict[str, object]:
            if "activation_v1" in name:
                raise PriceCoverageActivationError("activation authority missing")
            return {}

    @contextmanager
    def _store(_root: Path):  # type: ignore[no-untyped-def]
        yield _Store()

    def _provider():  # type: ignore[no-untyped-def]
        nonlocal provider_builds
        provider_builds += 1
        raise AssertionError("provider must not be built")

    def _repository():  # type: ignore[no-untyped-def]
        nonlocal repository_builds
        repository_builds += 1
        raise AssertionError("repository must not be built before artifact load")

    monkeypatch.setattr(run_price_coverage_r3_scan, "locked_artifact_store", _store)
    monkeypatch.setattr(run_price_coverage_r3_scan, "ShioajiProvider", _provider)
    monkeypatch.setattr(
        run_price_coverage_r3_scan,
        "build_price_coverage_repository",
        _repository,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_price_coverage_r3_scan.py", "--activation-digest", ACTIVATION_DIGEST],
    )

    with pytest.raises(PriceCoverageActivationError, match="missing"):
        run_price_coverage_r3_scan.main()
    assert repository_builds == 0
    assert provider_builds == 0


def test_runner_holds_acquisition_lock_through_provider_and_repository_close(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state = {"locked": False, "provider_closed": False, "repository_closed": False}

    class _Store:
        def load(self, _name: str) -> dict[str, object]:
            return {}

    @contextmanager
    def _store(_root: Path):  # type: ignore[no-untyped-def]
        state["locked"] = True
        try:
            yield _Store()
        finally:
            state["locked"] = False

    class _Repository:
        def activate_price_coverage_scan_job(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return {"status": "QUEUED"}, False

        def close(self) -> None:
            assert state["locked"] is True
            state["repository_closed"] = True

    class _Provider:
        environment_identity = "shioaji:1.7.2:simulation=true"

        def close(self) -> None:
            assert state["locked"] is True
            state["provider_closed"] = True

    class _Downloader:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def run_price_coverage_scan(self, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            return {"status": "SCAN_COMPLETE"}

    repository = _Repository()
    monkeypatch.setattr(run_price_coverage_r3_scan, "locked_artifact_store", _store)
    monkeypatch.setattr(run_price_coverage_r3_scan, "ShioajiProvider", _Provider)
    monkeypatch.setattr(
        run_price_coverage_r3_scan,
        "ResumableHistoricalDownloader",
        _Downloader,
    )
    monkeypatch.setattr(
        run_price_coverage_r3_scan,
        "HistoricalDatasetCatalog",
        lambda _root: object(),
    )
    monkeypatch.setattr(
        run_price_coverage_r3_scan,
        "verify_price_coverage_activation",
        lambda **_kwargs: VerifiedPriceCoverageActivation(
            activation_digest=ACTIVATION_DIGEST,
            job_id="job-r3",
            request_digest="b" * 64,
            provider_environment_identity="shioaji:1.7.2:simulation=true",
        ),
    )
    monkeypatch.setattr(
        run_price_coverage_r3_scan,
        "build_price_coverage_repository",
        lambda: repository,
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["run_price_coverage_r3_scan.py", "--activation-digest", ACTIVATION_DIGEST],
    )

    run_price_coverage_r3_scan.main()

    assert state == {
        "locked": False,
        "provider_closed": True,
        "repository_closed": True,
    }


def test_activation_status_is_explicit_not_formal_research_authority() -> None:
    activation = build_price_coverage_activation(
        job=_stored_prepared_job(),
        source_snapshot={},
        authorized_at=datetime(2026, 8, 26, 12, 0, tzinfo=TAIPEI),
        authorized_by="research-owner",
    )

    assert activation["status"] == ACTIVATION_STATUS
    assert activation["activation"]["historical_kbar_requests_allowed"] is True
    assert activation["scope"]["research_eligible"] is False
    assert all(value is False for value in activation["execution_lock"].values())
