"""Metadata-only initialization for a fresh price-coverage acquisition lineage."""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import stat
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Iterable, Iterator, Mapping, Sequence

from backtest.domain import canonical_json


FRESH_LINEAGE_MODE = "FRESH_R3_NO_CHECKPOINT_REUSE"
UNIVERSE_SELECTION = "ALL_CURRENT_CONTRACT_CATALOG_V1"
TARGET_SCHEMA_VERSION = "price_coverage_target_order_v1"
CONFIG_SCHEMA_VERSION = "price_coverage_scan_configuration_v2"
PREPARED_JOB_KIND = "PRICE_COVERAGE_PREPARED"
PREPARED_JOB_STATUS = "PREPARED"
PREPARED_PROGRESS_MESSAGE = (
    "Fresh r3 prepared; generic Kbar resume prohibited; dedicated activation required"
)
ACQUISITION_LOCK_NAME = ".price_coverage_acquisition.lock"
_MAX_ARTIFACT_BYTES = 64 * 1024 * 1024


class PriceCoverageInitializationError(RuntimeError):
    """Fresh coverage initialization failed closed."""


@dataclass(frozen=True)
class ContractTarget:
    symbol: str
    name: str
    market: str

    def instrument_dict(self) -> dict[str, str]:
        return {
            "symbol": self.symbol,
            "name": self.name,
            "market": self.market,
        }

    def order_dict(self, target_index: int) -> dict[str, Any]:
        return {
            "target_index": target_index,
            **self.instrument_dict(),
        }


@dataclass(frozen=True)
class PreparedFreshPriceCoverageJob:
    job_id: str
    target_dataset_id: str
    request: dict[str, Any]
    request_canonical_sha256: str
    target_order_canonical_sha256: str
    targets: tuple[ContractTarget, ...]


@dataclass(frozen=True)
class LockedArtifactStore:
    """A no-follow acquisition root held under the repository-wide lock."""

    root: Path
    _root_fd: int

    def publish(self, name: str, payload: Mapping[str, Any]) -> str:
        _require_artifact_name(name)
        digest = _sha256_canonical(payload)
        presentation = (
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        sidecar_name = _sidecar_name(name)
        sidecar = f"{digest}\n".encode("ascii")
        _cleanup_completed_stage(
            self._root_fd,
            stage_name=_stage_name(sidecar_name, sidecar),
            final_name=sidecar_name,
        )
        _cleanup_completed_stage(
            self._root_fd,
            stage_name=_stage_name(name, presentation),
            final_name=name,
        )
        existing_json = _read_optional_regular_at(
            self._root_fd,
            name,
            require_single_link=True,
        )
        existing_sidecar = _read_optional_regular_at(
            self._root_fd,
            sidecar_name,
            require_single_link=True,
        )
        if existing_json is not None and existing_json != presentation:
            raise PriceCoverageInitializationError(
                f"Immutable artifact conflict: {self.root / name}"
            )
        if existing_sidecar is not None and existing_sidecar != sidecar:
            raise PriceCoverageInitializationError(
                f"Immutable artifact conflict: {self.root / sidecar_name}"
            )
        staged: list[str] = []
        try:
            sidecar_stage = None
            json_stage = None
            if existing_sidecar is None:
                sidecar_stage = _stage_exact_bytes(
                    self._root_fd,
                    final_name=sidecar_name,
                    content=sidecar,
                )
                staged.append(sidecar_stage)
            if existing_json is None:
                json_stage = _stage_exact_bytes(
                    self._root_fd,
                    final_name=name,
                    content=presentation,
                )
                staged.append(json_stage)
            # The sidecar is durable first.  The JSON link is the pair's commit marker.
            if sidecar_stage is not None:
                _link_stage_to_final(
                    self._root_fd,
                    stage_name=sidecar_stage,
                    final_name=sidecar_name,
                    expected=sidecar,
                )
                os.fsync(self._root_fd)
            if json_stage is not None:
                _link_stage_to_final(
                    self._root_fd,
                    stage_name=json_stage,
                    final_name=name,
                    expected=presentation,
                )
                os.fsync(self._root_fd)
        finally:
            for stage_name in staged:
                try:
                    os.unlink(stage_name, dir_fd=self._root_fd)
                except FileNotFoundError:
                    pass
            if staged:
                os.fsync(self._root_fd)
        if _read_required_regular_at(
            self._root_fd,
            sidecar_name,
            require_single_link=True,
        ) != sidecar or _read_required_regular_at(
            self._root_fd,
            name,
            require_single_link=True,
        ) != presentation:
            raise PriceCoverageInitializationError(
                f"Artifact pair postflight failed: {self.root / name}"
            )
        return digest

    def load(self, name: str) -> dict[str, Any]:
        _require_artifact_name(name)
        raw = _read_required_regular_at(
            self._root_fd,
            name,
            require_single_link=True,
        )
        expected = _read_required_regular_at(
            self._root_fd,
            _sidecar_name(name),
            require_single_link=True,
        )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as error:
            raise PriceCoverageInitializationError(
                f"Artifact JSON is invalid: {self.root / name}"
            ) from error
        if not isinstance(payload, dict):
            raise PriceCoverageInitializationError(
                f"Artifact root must be an object: {self.root / name}"
            )
        digest = _sha256_canonical(payload)
        if expected != f"{digest}\n".encode("ascii"):
            raise PriceCoverageInitializationError(
                f"Artifact digest mismatch: {self.root / name}"
            )
        return payload


@contextmanager
def locked_artifact_store(root: Path) -> Iterator[LockedArtifactStore]:
    """Open the fixed acquisition root without symlinks and hold its process lock."""

    root_fd = _open_absolute_directory_no_follow(root)
    lock_fd = -1
    try:
        root_stat = os.fstat(root_fd)
        if root_stat.st_uid != os.getuid() or stat.S_IMODE(root_stat.st_mode) & 0o022:
            raise PriceCoverageInitializationError(
                "Acquisition root must be caller-owned and not group/world writable"
            )
        flags = os.O_RDWR | os.O_CREAT | _no_follow_flags()
        lock_fd = os.open(ACQUISITION_LOCK_NAME, flags, 0o600, dir_fd=root_fd)
        lock_stat = os.fstat(lock_fd)
        if (
            not stat.S_ISREG(lock_stat.st_mode)
            or lock_stat.st_uid != os.getuid()
            or lock_stat.st_nlink != 1
            or stat.S_IMODE(lock_stat.st_mode) != 0o600
        ):
            raise PriceCoverageInitializationError(
                "Acquisition lock must be a caller-owned 0600 regular file"
            )
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise PriceCoverageInitializationError(
                "Another price acquisition process holds the repository lock"
            ) from error
        yield LockedArtifactStore(root=root, _root_fd=root_fd)
    finally:
        if lock_fd >= 0:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        os.close(root_fd)


def targets_from_contract_catalog(provider: object) -> tuple[ContractTarget, ...]:
    """Read only Shioaji contract metadata; never call Snapshot, usage, or Kbar APIs."""

    api = getattr(provider, "_api", None)
    try:
        stocks = api.Contracts.Stocks
        collections = (("TWSE", stocks.TSE), ("TPEX", stocks.OTC))
    except AttributeError as error:
        raise PriceCoverageInitializationError(
            "Shioaji contract catalog is unavailable"
        ) from error
    return normalize_contract_targets(collections)


def normalize_contract_targets(
    collections: Iterable[tuple[str, Iterable[object]]],
) -> tuple[ContractTarget, ...]:
    by_symbol: dict[str, ContractTarget] = {}
    for market, contracts in collections:
        if market not in {"TWSE", "TPEX"}:
            raise PriceCoverageInitializationError(
                f"Unsupported contract market: {market}"
            )
        for contract in contracts:
            if contract is None:
                continue
            symbol = str(getattr(contract, "code", "")).strip().upper()
            name = str(getattr(contract, "name", "")).strip()
            if not symbol or not name:
                raise PriceCoverageInitializationError(
                    f"Contract identity is incomplete in {market}"
                )
            target = ContractTarget(symbol=symbol, name=name, market=market)
            prior = by_symbol.get(symbol)
            if prior is not None:
                raise PriceCoverageInitializationError(
                    f"Duplicate contract symbol: {symbol} ({prior.market}/{market})"
                )
            by_symbol[symbol] = target
    if not by_symbol:
        raise PriceCoverageInitializationError("Contract catalog is empty")
    return tuple(by_symbol[symbol] for symbol in sorted(by_symbol))


def prepare_fresh_job(
    *,
    targets: Sequence[ContractTarget],
    provider_environment_identity: str,
    end_date: date,
) -> PreparedFreshPriceCoverageJob:
    ordered = tuple(targets)
    if ordered != tuple(sorted(ordered, key=lambda item: item.symbol)):
        raise PriceCoverageInitializationError("Targets must be sorted by symbol")
    if len({item.symbol for item in ordered}) != len(ordered) or not ordered:
        raise PriceCoverageInitializationError("Targets must be non-empty and unique")
    if not provider_environment_identity.strip():
        raise PriceCoverageInitializationError("Provider environment identity is required")

    order_rows = [
        target.order_dict(index)
        for index, target in enumerate(ordered)
    ]
    target_order_digest = _sha256_canonical(order_rows)
    start_date = end_date - timedelta(days=365 * 3)
    identity_payload = {
        "lineage_mode": FRESH_LINEAGE_MODE,
        "provider": "ShioajiProvider",
        "provider_environment_identity": provider_environment_identity,
        "requested_start_date": start_date.isoformat(),
        "requested_end_date": end_date.isoformat(),
        "target_order_canonical_sha256": target_order_digest,
        "universe_selection": UNIVERSE_SELECTION,
    }
    identity = _sha256_canonical(identity_payload)
    job_id = f"dataset-download-r3-{identity[:32]}"
    target_dataset_id = f"dataset-r3-{identity[:32]}"
    request = {
        "provider": "ShioajiProvider",
        "provider_environment_identity": provider_environment_identity,
        "years": 3,
        "start_date": start_date.isoformat(),
        "end_date": end_date.isoformat(),
        "universe_selection": UNIVERSE_SELECTION,
        "coverage_scan_mode": True,
        "lineage_mode": FRESH_LINEAGE_MODE,
        "target_order_canonical_sha256": target_order_digest,
        "instruments": [target.instrument_dict() for target in ordered],
        "target_dataset_id": target_dataset_id,
    }
    return PreparedFreshPriceCoverageJob(
        job_id=job_id,
        target_dataset_id=target_dataset_id,
        request=request,
        request_canonical_sha256=_sha256_canonical(request),
        target_order_canonical_sha256=target_order_digest,
        targets=ordered,
    )


def persist_fresh_job_exactly_once(
    *,
    repository: Any,
    prepared: PreparedFreshPriceCoverageJob,
    created_at: datetime,
) -> tuple[dict[str, Any], bool]:
    record = {
        "job_id": prepared.job_id,
        "kind": PREPARED_JOB_KIND,
        "status": PREPARED_JOB_STATUS,
        "request": prepared.request,
        "progress": 0.0,
        "progress_message": PREPARED_PROGRESS_MESSAGE,
        "created_at": created_at.isoformat(),
    }
    stored, created = repository.create_job_once(record)
    if stored.get("job_id") != prepared.job_id:
        raise PriceCoverageInitializationError(
            "Repository returned a different fresh job identity"
        )
    if canonical_json(stored["request"]) != canonical_json(prepared.request):
        raise PriceCoverageInitializationError(
            "Deterministic job id already exists with a different request"
        )
    if (
        stored["kind"] != PREPARED_JOB_KIND
        or stored["status"] != PREPARED_JOB_STATUS
        or float(stored["progress"]) != 0.0
        or stored.get("progress_message") != PREPARED_PROGRESS_MESSAGE
        or stored.get("resource_id") is not None
        or stored.get("error_message") is not None
    ):
        raise PriceCoverageInitializationError(
            "Fresh job is not an untouched PREPARED job"
        )
    try:
        stored_created_at = datetime.fromisoformat(str(stored["created_at"]))
    except (KeyError, TypeError, ValueError) as error:
        raise PriceCoverageInitializationError(
            "Fresh job has an invalid creation identity"
        ) from error
    if stored_created_at.utcoffset() != timedelta(hours=8):
        raise PriceCoverageInitializationError(
            "Fresh job creation identity must use Asia/Taipei offset"
        )
    if created and stored_created_at != created_at:
        raise PriceCoverageInitializationError(
            "Fresh job creation identity changed during persistence"
        )
    if "retry_symbol" in stored["request"]:
        raise PriceCoverageInitializationError(
            "Fresh job must not inherit a retry marker"
        )
    if repository.list_history_partitions(prepared.job_id):
        raise PriceCoverageInitializationError(
            "Fresh job unexpectedly contains history partitions"
        )
    try:
        repository.get_dataset(prepared.target_dataset_id)
    except KeyError:
        pass
    else:
        raise PriceCoverageInitializationError(
            "Fresh job target Dataset already exists"
        )
    return stored, created


def build_target_manifest(
    *,
    prepared: PreparedFreshPriceCoverageJob,
    captured_at: datetime,
    provider_environment_identity: str,
) -> dict[str, Any]:
    return {
        "artifact_id": "price-coverage-target-order-v1-2026-08-26-r3",
        "schema_version": TARGET_SCHEMA_VERSION,
        "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
        "captured_at": captured_at.isoformat(),
        "lineage": {
            "mode": FRESH_LINEAGE_MODE,
            "predecessor_checkpoint_inheritance_allowed": False,
            "summary_merge_with_r0_r1_r2_allowed": False,
        },
        "source": {
            "provider": "shioaji",
            "provider_environment_identity": provider_environment_identity,
            "catalog_access": "CONTRACT_METADATA_ONLY_NO_SNAPSHOT_NO_KBAR",
            "credential_values_stored": False,
        },
        "universe": {
            "selection": UNIVERSE_SELECTION,
            "market_scope": ["TWSE", "TPEX"],
            "sort_policy": "SYMBOL_ASC",
            "research_eligible": False,
        },
        "target_order": {
            "projection_fields": ["target_index", "symbol", "name", "market"],
            "target_count": len(prepared.targets),
            "canonical_sha256": prepared.target_order_canonical_sha256,
        },
        "targets": [
            target.order_dict(index)
            for index, target in enumerate(prepared.targets)
        ],
        "scope": {
            "price_values_read": False,
            "outcome_fields_read": False,
            "historical_kbar_requests_issued": False,
            "order_submission_allowed": False,
            "trade_subscription_allowed": False,
        },
    }


def build_r3_configuration(
    *,
    prepared: PreparedFreshPriceCoverageJob,
    stored_job: Mapping[str, Any],
    registered_at: datetime,
    target_manifest_digest: str,
    source_snapshot: Mapping[str, Any],
    provider_environment_identity: str,
) -> dict[str, Any]:
    return {
        "artifact_id": "price-coverage-scan-configuration-v2-2026-08-26-r3",
        "schema_version": CONFIG_SCHEMA_VERSION,
        "change_policy": "IMMUTABLE_NEW_ARTIFACT_REQUIRED",
        "status": "FROZEN_JOB_CREATED_SCAN_NOT_AUTHORIZED",
        "registered_at": registered_at.isoformat(),
        "lineage": {
            "mode": "FRESH_RESTART_NO_CHECKPOINT_INHERITANCE",
            "predecessor_configuration": {
                "artifact_id": "price-coverage-scan-configuration-v1-2026-08-21-r2",
                "canonical_sha256": (
                    "d60502f51897bdf4492717ec49f07b52"
                    "b09c5f7f60b8c5764d10b4295dc22797"
                ),
            },
            "predecessor_disposition": "ABANDONED_DURABLE_JOB_UNRECOVERABLE",
            "inherited_checkpoint_count": 0,
            "inherited_observation_count": 0,
            "summary_merge_with_old_lineage_allowed": False,
        },
        "job": {
            "job_id": prepared.job_id,
            "job_kind": stored_job["kind"],
            "state_at_registration": stored_job["status"],
            "start_target_index": 0,
            "checkpointed_partition_count": 0,
            "retry_symbol": None,
            "request_canonical_sha256": prepared.request_canonical_sha256,
            "requested_start_date": prepared.request["start_date"],
            "requested_end_date": prepared.request["end_date"],
            "target_count": len(prepared.targets),
            "universe_selection": UNIVERSE_SELECTION,
        },
        "target_order": {
            "manifest_artifact_id": "price-coverage-target-order-v1-2026-08-26-r3",
            "manifest_canonical_sha256": target_manifest_digest,
            "projection_fields": ["target_index", "symbol", "name", "market"],
            "target_order_canonical_sha256": (
                prepared.target_order_canonical_sha256
            ),
        },
        "source_snapshot": dict(source_snapshot),
        "provider_environment": {
            "provider": "shioaji",
            "adapter_class": "market_data.provider.ShioajiProvider",
            "sdk_package": "shioaji",
            "sdk_version": provider_environment_identity.split(":")[1],
            "simulation": provider_environment_identity.endswith("simulation=true"),
            "historical_query": "Shioaji.kbars",
            "subscribe_trade": False,
            "credential_values_stored": False,
        },
        "activation": {
            "activation_rule": "SEPARATE_EXPLICIT_SCAN_AUTHORIZATION_REQUIRED",
            "exact_config_digest_required_before_provider_build": True,
            "exact_target_order_required": True,
            "acquisition_lock_required": True,
            "historical_kbar_requests_allowed": False,
        },
        "execution_lock": {
            "dataset_materialization_allowed": False,
            "formal_coverage_audit_allowed": False,
            "population_freeze_allowed": False,
            "outcome_generation_allowed": False,
            "holdout_allowed": False,
            "order_submission_allowed": False,
            "trade_subscription_allowed": False,
        },
        "scope": {
            "purpose": "FRESH_PRICE_COVERAGE_JOB_INITIALIZATION_ONLY",
            "research_eligible": False,
            "price_values_read": False,
            "outcome_fields_read": False,
        },
    }


def git_source_snapshot(
    *,
    root: Path,
    source_paths: Sequence[str],
) -> dict[str, Any]:
    head = _git_text(root, "rev-parse", "HEAD")
    tree = _git_text(root, "rev-parse", "HEAD^{tree}")
    object_format = _git_text(root, "rev-parse", "--show-object-format")
    files: list[dict[str, Any]] = []
    for relative in source_paths:
        _require_git_clean(root, relative)
        working_bytes = (root / relative).read_bytes()
        committed_bytes = subprocess.run(
            ["git", "show", f"HEAD:{relative}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        if working_bytes != committed_bytes:
            raise PriceCoverageInitializationError(
                f"Pinned source is not reproducible from HEAD: {relative}"
            )
        files.append(
            {
                "path": relative,
                "git_blob_oid": _git_text(root, "rev-parse", f"HEAD:{relative}"),
                "content_sha256": hashlib.sha256(working_bytes).hexdigest(),
            }
        )
    return {
        "repository_commit": head,
        "repository_tree_oid": tree,
        "git_object_format": object_format,
        "pinned_source_paths_clean": True,
        "repository_worktree_clean": False,
        "files": files,
    }


def assert_no_secret_values(
    payloads: Iterable[Mapping[str, Any]],
    secret_values: Iterable[str],
) -> None:
    serialized = "\n".join(canonical_json(payload) for payload in payloads)
    for value in secret_values:
        secret = str(value or "")
        if len(secret) >= 8 and secret in serialized:
            raise PriceCoverageInitializationError(
                "Credential value would be persisted in research evidence"
            )


def _open_absolute_directory_no_follow(path: Path) -> int:
    if not path.is_absolute() or any(part in {".", "..", ""} for part in path.parts[1:]):
        raise PriceCoverageInitializationError(
            "Acquisition root must be an absolute normalized path"
        )
    flags = os.O_RDONLY | os.O_DIRECTORY | _no_follow_flags()
    descriptor = os.open("/", flags)
    try:
        for component in path.parts[1:]:
            try:
                child = os.open(component, flags, dir_fd=descriptor)
            except OSError as error:
                raise PriceCoverageInitializationError(
                    f"Acquisition root has an unavailable or symlinked component: {path}"
                ) from error
            if not stat.S_ISDIR(os.fstat(child).st_mode):
                os.close(child)
                raise PriceCoverageInitializationError(
                    f"Acquisition root component is not a directory: {path}"
                )
            os.close(descriptor)
            descriptor = child
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _no_follow_flags() -> int:
    flags = getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_CLOEXEC", 0)
    return flags


def _require_artifact_name(name: str) -> None:
    if (
        not name
        or Path(name).name != name
        or name in {".", ".."}
        or not name.endswith(".json")
    ):
        raise PriceCoverageInitializationError(
            "Artifact name must be one JSON basename inside the acquisition root"
        )


def _sidecar_name(name: str) -> str:
    return f"{name[:-5]}.canonical.sha256"


def _read_optional_regular_at(
    root_fd: int,
    name: str,
    *,
    require_single_link: bool = False,
) -> bytes | None:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | _no_follow_flags(),
            dir_fd=root_fd,
        )
    except FileNotFoundError:
        return None
    except OSError as error:
        raise PriceCoverageInitializationError(
            f"Artifact path is unsafe or unavailable: {name}"
        ) from error
    try:
        file_stat = os.fstat(descriptor)
        if not stat.S_ISREG(file_stat.st_mode):
            raise PriceCoverageInitializationError(
                f"Artifact must be a regular file: {name}"
            )
        if require_single_link and file_stat.st_nlink != 1:
            raise PriceCoverageInitializationError(
                f"Artifact must not have external hard links: {name}"
            )
        if file_stat.st_size > _MAX_ARTIFACT_BYTES:
            raise PriceCoverageInitializationError(
                f"Artifact exceeds the bounded read limit: {name}"
            )
        chunks: list[bytes] = []
        remaining = file_stat.st_size
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1024 * 1024))
            if not chunk:
                raise PriceCoverageInitializationError(
                    f"Artifact changed during bounded read: {name}"
                )
            chunks.append(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise PriceCoverageInitializationError(
                f"Artifact grew during bounded read: {name}"
            )
        return b"".join(chunks)
    finally:
        os.close(descriptor)


def _read_required_regular_at(
    root_fd: int,
    name: str,
    *,
    require_single_link: bool = False,
) -> bytes:
    content = _read_optional_regular_at(
        root_fd,
        name,
        require_single_link=require_single_link,
    )
    if content is None:
        raise PriceCoverageInitializationError(f"Artifact is unavailable: {name}")
    return content


def _stage_exact_bytes(root_fd: int, *, final_name: str, content: bytes) -> str:
    stage_name = _stage_name(final_name, content)
    existing = _read_optional_regular_at(root_fd, stage_name)
    if existing is not None:
        if existing != content:
            raise PriceCoverageInitializationError(
                f"Artifact staging conflict: {stage_name}"
            )
        return stage_name
    descriptor = os.open(
        stage_name,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | _no_follow_flags(),
        0o644,
        dir_fd=root_fd,
    )
    try:
        view = memoryview(content)
        written = 0
        while written < len(view):
            count = os.write(descriptor, view[written:])
            if count <= 0:
                raise PriceCoverageInitializationError(
                    f"Artifact staging write failed: {stage_name}"
                )
            written += count
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return stage_name


def _stage_name(final_name: str, content: bytes) -> str:
    stage_token = hashlib.sha256(
        final_name.encode("utf-8") + b"\0" + content
    ).hexdigest()
    return f".{stage_token}.price-coverage-stage"


def _cleanup_completed_stage(
    root_fd: int,
    *,
    stage_name: str,
    final_name: str,
) -> None:
    try:
        stage_stat = os.stat(stage_name, dir_fd=root_fd, follow_symlinks=False)
        final_stat = os.stat(final_name, dir_fd=root_fd, follow_symlinks=False)
    except FileNotFoundError:
        return
    if (
        not stat.S_ISREG(stage_stat.st_mode)
        or not stat.S_ISREG(final_stat.st_mode)
        or stage_stat.st_dev != final_stat.st_dev
        or stage_stat.st_ino != final_stat.st_ino
    ):
        return
    os.unlink(stage_name, dir_fd=root_fd)
    os.fsync(root_fd)


def _link_stage_to_final(
    root_fd: int,
    *,
    stage_name: str,
    final_name: str,
    expected: bytes,
) -> None:
    try:
        os.link(
            stage_name,
            final_name,
            src_dir_fd=root_fd,
            dst_dir_fd=root_fd,
            follow_symlinks=False,
        )
    except FileExistsError:
        existing = _read_required_regular_at(root_fd, final_name)
        if existing != expected:
            raise PriceCoverageInitializationError(
                f"Immutable artifact conflict: {final_name}"
            )


def _sha256_canonical(payload: Any) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def _git_text(root: Path, *arguments: str) -> str:
    return subprocess.run(
        ["git", *arguments],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _require_git_clean(root: Path, relative: str) -> None:
    for arguments in (("diff", "--quiet", "--", relative), ("diff", "--cached", "--quiet", "--", relative)):
        result = subprocess.run(["git", *arguments], cwd=root, check=False)
        if result.returncode != 0:
            raise PriceCoverageInitializationError(
                f"Pinned source has Git drift: {relative}"
            )
