from __future__ import annotations

import hashlib
import json
import multiprocessing
import os
from dataclasses import dataclass, replace
from datetime import date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backtest.domain import canonical_json
from backtest.historical_download import (
    ResumableHistoricalDownloader,
    assert_generic_history_resume_allowed,
)
from backtest.price_coverage_initialization import (
    ContractTarget,
    PREPARED_JOB_KIND,
    PREPARED_JOB_STATUS,
    PREPARED_PROGRESS_MESSAGE,
    PriceCoverageInitializationError,
    locked_artifact_store,
    normalize_contract_targets,
    persist_fresh_job_exactly_once,
    prepare_fresh_job,
    targets_from_contract_catalog,
)
from backtest.sqlite_repository import SQLiteBacktestRepository


TAIPEI = ZoneInfo("Asia/Taipei")


@dataclass
class _Contract:
    code: str
    name: str


class _PoisonProvider:
    def __init__(self) -> None:
        self._api = SimpleNamespace(
            Contracts=SimpleNamespace(
                Stocks=SimpleNamespace(
                    TSE=[_Contract("2330", "台積電")],
                    OTC=[_Contract("1240", "茂生農經")],
                )
            )
        )

    def get_market_stocks(self):  # type: ignore[no-untyped-def]
        raise AssertionError("Snapshot path must not be called")

    def get_kbars(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        raise AssertionError("Kbar path must not be called")

    def market_data_usage(self):  # type: ignore[no-untyped-def]
        raise AssertionError("Usage path must not be called")


def _try_lock_in_spawned_process(root: str, queue) -> None:  # type: ignore[no-untyped-def]
    try:
        with locked_artifact_store(Path(root)):
            queue.put("ACQUIRED")
    except PriceCoverageInitializationError:
        queue.put("BLOCKED")


def _prepared():  # type: ignore[no-untyped-def]
    return prepare_fresh_job(
        targets=(
            ContractTarget("1240", "茂生農經", "TPEX"),
            ContractTarget("2330", "台積電", "TWSE"),
        ),
        provider_environment_identity="shioaji:1.7.2:simulation=true",
        end_date=date(2026, 8, 18),
    )


def test_contract_catalog_path_never_calls_snapshot_usage_or_kbars() -> None:
    targets = targets_from_contract_catalog(_PoisonProvider())

    assert targets == (
        ContractTarget("1240", "茂生農經", "TPEX"),
        ContractTarget("2330", "台積電", "TWSE"),
    )


def test_contract_catalog_rejects_duplicate_empty_and_unknown_market() -> None:
    with pytest.raises(PriceCoverageInitializationError, match="Duplicate"):
        normalize_contract_targets(
            (
                ("TWSE", [_Contract("2330", "台積電")]),
                ("TPEX", [_Contract("2330", "duplicate")]),
            )
        )
    with pytest.raises(PriceCoverageInitializationError, match="incomplete"):
        normalize_contract_targets((("TWSE", [_Contract("", "missing")]),))
    with pytest.raises(PriceCoverageInitializationError, match="Unsupported"):
        normalize_contract_targets((("UNKNOWN", [_Contract("2330", "台積電")]),))


def test_prepared_job_is_deterministic_and_pins_new_universe_semantics() -> None:
    first = _prepared()
    second = _prepared()

    assert first == second
    assert first.job_id.startswith("dataset-download-r3-")
    assert first.request["start_date"] == "2023-08-19"
    assert first.request["end_date"] == "2026-08-18"
    assert first.request["universe_selection"] == "ALL_CURRENT_CONTRACT_CATALOG_V1"
    assert first.request["coverage_scan_mode"] is True
    assert first.request["lineage_mode"] == "FRESH_R3_NO_CHECKPOINT_REUSE"


def test_job_creation_is_idempotent_exact_and_leaves_zero_partitions() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        repository = SQLiteBacktestRepository(Path(directory) / "backtest.sqlite3")
        prepared = _prepared()
        created_at = datetime(2026, 8, 26, 9, 0, tzinfo=TAIPEI)
        try:
            first, created = persist_fresh_job_exactly_once(
                repository=repository,
                prepared=prepared,
                created_at=created_at,
            )
            replay, created_again = persist_fresh_job_exactly_once(
                repository=repository,
                prepared=prepared,
                created_at=created_at,
            )

            assert created is True
            assert created_again is False
            assert first == replay
            assert first["kind"] == PREPARED_JOB_KIND
            assert first["status"] == PREPARED_JOB_STATUS
            assert first["progress_message"] == PREPARED_PROGRESS_MESSAGE
            assert first["error_message"] is None
            assert repository.list_history_partitions(prepared.job_id) == []

            changed = replace(
                prepared,
                request={**prepared.request, "end_date": "2026-08-17"},
            )
            with pytest.raises(PriceCoverageInitializationError, match="different request"):
                persist_fresh_job_exactly_once(
                    repository=repository,
                    prepared=changed,
                    created_at=created_at,
                )
        finally:
            repository.close()


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("job_id", "dataset-download-r3-wrong", "different fresh job identity"),
        ("kind", "DATASET_DOWNLOAD", "untouched PREPARED"),
        ("status", "QUEUED", "untouched PREPARED"),
        ("progress", 0.5, "untouched PREPARED"),
        ("resource_id", "dataset-unexpected", "untouched PREPARED"),
        ("error_message", "stale failure", "untouched PREPARED"),
        ("progress_message", "drifted", "untouched PREPARED"),
        ("created_at", "2026-08-26T09:00:00+00:00", "Asia/Taipei"),
    ],
)
def test_job_exact_readback_rejects_identity_and_state_drift(
    field: str,
    value: object,
    message: str,
) -> None:
    prepared = _prepared()
    created_at = datetime(2026, 8, 26, 9, 0, tzinfo=TAIPEI)
    stored = {
        "job_id": prepared.job_id,
        "kind": PREPARED_JOB_KIND,
        "status": PREPARED_JOB_STATUS,
        "request": prepared.request,
        "progress": 0.0,
        "progress_message": PREPARED_PROGRESS_MESSAGE,
        "created_at": created_at.isoformat(),
        "resource_id": None,
        "error_message": None,
    }
    stored[field] = value

    class _Repository:
        def create_job_once(self, _record):  # type: ignore[no-untyped-def]
            return stored, True

        def list_history_partitions(self, _job_id):  # type: ignore[no-untyped-def]
            return []

        def get_dataset(self, _dataset_id):  # type: ignore[no-untyped-def]
            raise KeyError

    with pytest.raises(PriceCoverageInitializationError, match=message):
        persist_fresh_job_exactly_once(
            repository=_Repository(),
            prepared=prepared,
            created_at=created_at,
        )


@pytest.mark.parametrize("failure", ["retry", "partition", "dataset"])
def test_job_exact_readback_rejects_inherited_or_materialized_state(
    failure: str,
) -> None:
    prepared = _prepared()
    if failure == "retry":
        prepared = replace(
            prepared,
            request={**prepared.request, "retry_symbol": "1259"},
        )
    created_at = datetime(2026, 8, 26, 9, 0, tzinfo=TAIPEI)
    stored = {
        "job_id": prepared.job_id,
        "kind": PREPARED_JOB_KIND,
        "status": PREPARED_JOB_STATUS,
        "request": dict(prepared.request),
        "progress": 0.0,
        "progress_message": PREPARED_PROGRESS_MESSAGE,
        "created_at": created_at.isoformat(),
        "resource_id": None,
        "error_message": None,
    }

    class _Repository:
        def create_job_once(self, _record):  # type: ignore[no-untyped-def]
            return stored, True

        def list_history_partitions(self, _job_id):  # type: ignore[no-untyped-def]
            return [{}] if failure == "partition" else []

        def get_dataset(self, _dataset_id):  # type: ignore[no-untyped-def]
            if failure == "dataset":
                return {"dataset_id": _dataset_id}
            raise KeyError

    expected = {
        "retry": "retry marker",
        "partition": "history partitions",
        "dataset": "target Dataset",
    }[failure]
    with pytest.raises(PriceCoverageInitializationError, match=expected):
        persist_fresh_job_exactly_once(
            repository=_Repository(),
            prepared=prepared,
            created_at=created_at,
        )


def test_canonical_artifact_publish_is_append_only_and_digest_verified() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        root = Path(directory)
        payload = {"schema_version": "fixture_v1", "value": 1}

        with locked_artifact_store(root) as store:
            digest = store.publish("artifact.json", payload)
            replay_digest = store.publish("artifact.json", payload)

            assert replay_digest == digest
            assert store.load("artifact.json") == payload
            assert (
                root / "artifact.canonical.sha256"
            ).read_text() == f"{digest}\n"
            with pytest.raises(PriceCoverageInitializationError, match="conflict"):
                store.publish("artifact.json", {**payload, "value": 2})


def test_artifact_store_rejects_symlinked_root_component() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        base = Path(directory)
        outside = base / "outside"
        (outside / "nested").mkdir(parents=True)
        link = base / "link"
        link.symlink_to(outside, target_is_directory=True)

        with pytest.raises(PriceCoverageInitializationError, match="symlinked"):
            with locked_artifact_store(link / "nested"):
                pass


@pytest.mark.parametrize("symlink_name", ["artifact.json", "artifact.canonical.sha256"])
def test_artifact_store_rejects_json_and_sidecar_symlinks(
    symlink_name: str,
) -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        root = Path(directory)
        victim = root / "victim"
        victim.write_text("do not touch", encoding="utf-8")
        (root / symlink_name).symlink_to(victim)

        with locked_artifact_store(root) as store:
            with pytest.raises(PriceCoverageInitializationError, match="unsafe"):
                store.publish("artifact.json", {"value": 1})
        assert victim.read_text(encoding="utf-8") == "do not touch"


def test_artifact_store_replays_an_exact_orphan_sidecar() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        root = Path(directory)
        payload = {"schema_version": "fixture_v1", "value": 1}
        digest = hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()
        (root / "artifact.canonical.sha256").write_text(
            f"{digest}\n",
            encoding="ascii",
        )

        with locked_artifact_store(root) as store:
            assert store.publish("artifact.json", payload) == digest
            assert store.load("artifact.json") == payload


def test_artifact_store_replays_an_exact_orphan_json() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        root = Path(directory)
        payload = {"schema_version": "fixture_v1", "value": 1}
        presentation = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        )
        (root / "artifact.json").write_text(presentation, encoding="utf-8")

        with locked_artifact_store(root) as store:
            store.publish("artifact.json", payload)
            assert store.load("artifact.json") == payload


@pytest.mark.parametrize("orphan", ["json", "sidecar"])
def test_artifact_store_rejects_conflicting_one_sided_artifacts(orphan: str) -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        root = Path(directory)
        if orphan == "json":
            (root / "artifact.json").write_text("{}\n", encoding="utf-8")
        else:
            (root / "artifact.canonical.sha256").write_text(
                f"{'0' * 64}\n",
                encoding="ascii",
            )

        with locked_artifact_store(root) as store:
            with pytest.raises(PriceCoverageInitializationError, match="conflict"):
                store.publish("artifact.json", {"value": 1})


def test_artifact_store_lock_contention_fails_closed() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        root = Path(directory)

        with locked_artifact_store(root):
            with pytest.raises(PriceCoverageInitializationError, match="holds"):
                with locked_artifact_store(root):
                    pass


def test_artifact_store_lock_contention_fails_closed_across_processes() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        context = multiprocessing.get_context("spawn")
        queue = context.Queue()
        process = context.Process(
            target=_try_lock_in_spawned_process,
            args=(directory, queue),
        )
        with locked_artifact_store(Path(directory)):
            process.start()
            process.join(timeout=10)
        assert process.exitcode == 0
        assert queue.get(timeout=1) == "BLOCKED"


def test_artifact_store_rejects_external_hard_links() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        root = Path(directory)
        payload = {"schema_version": "fixture_v1", "value": 1}
        with locked_artifact_store(root) as store:
            store.publish("artifact.json", payload)
        outside_link = root / "outside-link"
        os.link(root / "artifact.json", outside_link)

        with locked_artifact_store(root) as store:
            with pytest.raises(PriceCoverageInitializationError, match="hard links"):
                store.load("artifact.json")


def test_acquisition_lock_rejects_external_hard_links() -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        root = Path(directory)
        with locked_artifact_store(root):
            pass
        os.link(
            root / ".price_coverage_acquisition.lock",
            root / "lock-hard-link",
        )

        with pytest.raises(PriceCoverageInitializationError, match="0600 regular"):
            with locked_artifact_store(root):
                pass


@pytest.mark.parametrize("name", ["artifact.json", "artifact.canonical.sha256"])
def test_artifact_store_rejects_load_time_symlinks(name: str) -> None:
    with TemporaryDirectory(dir="/private/tmp") as directory:
        root = Path(directory)
        with locked_artifact_store(root) as store:
            store.publish("artifact.json", {"value": 1})
        victim = root / "victim"
        victim.write_text("{}\n", encoding="utf-8")
        (root / name).unlink()
        (root / name).symlink_to(victim)

        with locked_artifact_store(root) as store:
            with pytest.raises(PriceCoverageInitializationError, match="unsafe"):
                store.load("artifact.json")


def test_generic_history_resume_rejects_fresh_r3_lineage() -> None:
    with pytest.raises(ValueError, match="鎖定"):
        assert_generic_history_resume_allowed(
            {
                "job_id": "dataset-download-r3-fixture",
                "kind": "DATASET_DOWNLOAD",
                "request": {"lineage_mode": "FRESH_R3_NO_CHECKPOINT_REUSE"},
            }
        )


def test_downloader_run_rejects_fresh_r3_before_provider_or_catalog_use() -> None:
    class _Repository:
        def get_job(self, job_id: str) -> dict[str, object]:
            return {
                "job_id": job_id,
                "kind": "DATASET_DOWNLOAD",
                "request": {"lineage_mode": "FRESH_R3_NO_CHECKPOINT_REUSE"},
            }

    class _Poison:
        def __getattribute__(self, name: str):  # type: ignore[no-untyped-def]
            raise AssertionError(f"unexpected provider/catalog access: {name}")

    downloader = ResumableHistoricalDownloader(
        provider=_Poison(),  # type: ignore[arg-type]
        repository=_Repository(),  # type: ignore[arg-type]
        catalog=_Poison(),  # type: ignore[arg-type]
    )

    with pytest.raises(ValueError, match="鎖定"):
        downloader.run("dataset-download-r3-fixture")
    with pytest.raises(ValueError, match="不是可續傳"):
        assert_generic_history_resume_allowed(
            {
                "job_id": "dataset-download-r3-fixture",
                "kind": PREPARED_JOB_KIND,
                "request": {},
            }
        )
