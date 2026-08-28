"""Digest-pinned planning and aggregation for historical institutional MVP batches."""

from __future__ import annotations

import fcntl
import json
import os
import stat
import uuid
from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text
from institutional_mvp.domain import (
    InstitutionalMvpDailyPolicy,
    verify_candidate_batch_payload,
)
from institutional_mvp.ports import ReviewedEquitySessionCalendar


PLAN_SCHEMA_VERSION = "institutional_mvp_candidate_series_plan_v1"
SERIES_SCHEMA_VERSION = "institutional_mvp_candidate_series_v1"
PLAN_STATUS = "FROZEN_INSTITUTIONAL_CANDIDATE_SERIES_ACQUISITION_PLAN"
SERIES_STATUS = "MVP_INSTITUTIONAL_CANDIDATE_SERIES_OBSERVATION_ONLY"
CHANGE_POLICY = "IMMUTABLE_APPEND_ONLY_REVISIONS"
MINIMUM_OVERLAPPING_TARGET_SESSIONS = 60

_PLAN_PERMISSIONS = {
    "candidate_batch_publication_allowed": True,
    "candidate_series_publication_allowed": True,
    "institutional_provider_read_allowed": True,
    "evaluation_universe_freeze_allowed": False,
    "outcome_generation_allowed": False,
    "holdout_execution_allowed": False,
    "runtime_strategy_binding_allowed": False,
    "order_submission_allowed": False,
}
_SERIES_PERMISSIONS = {
    "institutional_candidate_series_observation_allowed": True,
    "evaluation_universe_freeze_allowed": False,
    "outcome_generation_allowed": False,
    "holdout_execution_allowed": False,
    "runtime_strategy_binding_allowed": False,
    "order_submission_allowed": False,
}
_LIMITATIONS = (
    "CURRENT_MARKET_MAPPING_CAN_HAVE_SURVIVORSHIP_AND_TRANSFER_BIAS",
    "DATASET_PRICE_BARS_WERE_NOT_READ_BY_THIS_ACQUISITION",
    "NO_EVALUATION_UNIVERSE_FREEZE_AUTHORITY",
    "NO_OUTCOME_OR_HOLDOUT_AUTHORITY",
    "NO_ORDER_OR_PRODUCTION_STRATEGY_AUTHORITY",
    "TWSE_CALENDAR_IS_OPERATIONAL_PROXY_FOR_CURRENT_TWSE_TPEX_MVP",
)

_ARTIFACT_PREFIX_BY_SCHEMA = {
    PLAN_SCHEMA_VERSION: "finmind-institutional-mvp-series-plan-v1",
    SERIES_SCHEMA_VERSION: "finmind-institutional-mvp-candidate-series-v1",
    "finmind_mvp_price_coverage_audit_v1": "finmind-mvp-price-coverage-audit-v1",
    "mvp_evaluation_universe_v1": "finmind-mvp-evaluation-universe-v1",
    "institutional_mvp_offline_ab_plan_v1": "institutional-mvp-offline-ab-plan-v1",
    "institutional_mvp_offline_ab_result_v1": "institutional-mvp-offline-ab-result-v1",
}
_SCHEMA_BY_CATEGORY = {
    "plans": PLAN_SCHEMA_VERSION,
    "series": SERIES_SCHEMA_VERSION,
    "coverage_audits": "finmind_mvp_price_coverage_audit_v1",
    "evaluation_universes": "mvp_evaluation_universe_v1",
    "diagnostic_plans": "institutional_mvp_offline_ab_plan_v1",
    "diagnostic_results": "institutional_mvp_offline_ab_result_v1",
}


class InstitutionalMvpSeriesError(RuntimeError):
    """A candidate-series plan or manifest failed closed."""


def dataset_reference(
    manifest: Mapping[str, Any], *, selection_audit_digest: str
) -> dict[str, Any]:
    """Project the approved immutable price Dataset without reading price bars."""
    reference = {
        "bar_count": _nonnegative_integer(manifest.get("bar_count"), "bar_count"),
        "bars_sha256": _digest(manifest.get("bars_sha256"), "bars_sha256"),
        "dataset_id": _text(manifest.get("dataset_id"), "dataset_id"),
        "end_date": _date_text(manifest.get("end_date"), "end_date"),
        "issues": list(_text_sequence(manifest.get("issues"), "issues")),
        "manifest_digest": _digest(
            manifest.get("manifest_digest"), "manifest_digest"
        ),
        "observed_symbol_count": len(
            _text_sequence(manifest.get("observed_symbols"), "observed_symbols")
        ),
        "payload_order": _text(manifest.get("payload_order"), "payload_order"),
        "plan_identity_digest": _digest(
            manifest.get("plan_identity_digest"), "plan_identity_digest"
        ),
        "profile": _text(manifest.get("profile"), "profile"),
        "research_eligible": manifest.get("research_eligible"),
        "selection_audit_digest": _digest(
            selection_audit_digest, "selection_audit_digest"
        ),
        "source": _text(manifest.get("source"), "source"),
        "source_snapshot_digest": _digest(
            manifest.get("source_snapshot_digest"), "source_snapshot_digest"
        ),
        "start_date": _date_text(manifest.get("start_date"), "start_date"),
        "storage_format": _text(manifest.get("storage_format"), "storage_format"),
        "universe_scope": _text(
            manifest.get("universe_scope"), "universe_scope"
        ),
        "universe_selection": _text(
            manifest.get("universe_selection"), "universe_selection"
        ),
    }
    if reference["research_eligible"] is not False:
        raise ValueError("approved MVP Dataset must remain research_eligible=false")
    if date.fromisoformat(reference["end_date"]) < date.fromisoformat(
        reference["start_date"]
    ):
        raise ValueError("Dataset date coverage is invalid")
    return reference


def build_candidate_series_plan(
    *,
    calendar: ReviewedEquitySessionCalendar,
    policy: InstitutionalMvpDailyPolicy,
    price_dataset_reference: Mapping[str, Any],
    target_end: date,
    session_count: int = MINIMUM_OVERLAPPING_TARGET_SESSIONS,
) -> dict[str, Any]:
    """Freeze the latest explicit T -> T+1 pairs before any provider call."""
    if isinstance(session_count, bool) or session_count < MINIMUM_OVERLAPPING_TARGET_SESSIONS:
        raise ValueError("candidate series requires at least 60 target sessions")
    dataset_start = date.fromisoformat(
        _date_text(price_dataset_reference.get("start_date"), "Dataset start_date")
    )
    dataset_end = date.fromisoformat(
        _date_text(price_dataset_reference.get("end_date"), "Dataset end_date")
    )
    if not dataset_start <= target_end <= dataset_end:
        raise ValueError("target_end must fall inside the approved Dataset")

    reviewed_sessions: list[date] = []
    cursor = max(calendar.coverage_start, dataset_start)
    while cursor <= min(calendar.coverage_end, target_end):
        if calendar.is_trading_day(cursor):
            reviewed_sessions.append(cursor)
        cursor += timedelta(days=1)
    pairs = [
        {"source_session": source.isoformat(), "target_session": target.isoformat()}
        for source, target in zip(reviewed_sessions, reviewed_sessions[1:])
        if calendar.next_trading_day(source) == target
    ]
    if len(pairs) < session_count:
        raise ValueError("reviewed calendar has insufficient overlapping session pairs")
    pairs = pairs[-session_count:]
    source_sessions = [item["source_session"] for item in pairs]
    target_sessions = [item["target_session"] for item in pairs]
    calendar_reference = {
        "coverage_end": calendar.coverage_end.isoformat(),
        "coverage_start": calendar.coverage_start.isoformat(),
        "schema_version": _text(calendar.schema_version, "calendar schema_version"),
        "scope": "TWSE_REVIEWED_PROXY_FOR_CURRENT_TWSE_TPEX_MVP",
        "source_digest": _digest(calendar.source_digest, "calendar source_digest"),
        "timezone": _text(calendar.timezone, "calendar timezone"),
    }
    body: dict[str, Any] = {
        "calendar_reference": calendar_reference,
        "candidate_policy_reference": {
            "artifact_id": policy.artifact_id,
            "base_policy_artifact_id": policy.base_policy_artifact_id,
            "base_policy_digest": policy.base_policy_digest,
            "canonical_sha256": policy.canonical_sha256,
        },
        "change_policy": CHANGE_POLICY,
        "execution_permissions": dict(_PLAN_PERMISSIONS),
        "limitations": list(_LIMITATIONS),
        "minimum_overlapping_target_sessions": MINIMUM_OVERLAPPING_TARGET_SESSIONS,
        "planned_session_count": len(pairs),
        "price_dataset_reference": dict(price_dataset_reference),
        "provider_contract": {
            "flow_dataset": "TaiwanStockInstitutionalInvestorsBuySellWide",
            "provider": "FINMIND",
            "source_version": "FINMIND_API_V4",
            "stock_info_dataset": "TaiwanStockInfo",
        },
        "schema_version": PLAN_SCHEMA_VERSION,
        "session_pairs": pairs,
        "source_sessions_digest": sha256_text(canonical_json(source_sessions)),
        "status": PLAN_STATUS,
        "target_end": target_end.isoformat(),
        "target_sessions_digest": sha256_text(canonical_json(target_sessions)),
    }
    return _with_identity(body, "finmind-institutional-mvp-series-plan-v1")


def verify_candidate_series_plan(
    payload: Mapping[str, Any],
    *,
    calendar: ReviewedEquitySessionCalendar,
    policy: InstitutionalMvpDailyPolicy,
    price_dataset_reference: Mapping[str, Any],
) -> tuple[tuple[date, date], ...]:
    """Reconstruct a frozen plan from its reviewed dependencies."""
    _verify_identity(payload, "finmind-institutional-mvp-series-plan-v1")
    if payload.get("schema_version") != PLAN_SCHEMA_VERSION:
        raise ValueError("candidate series plan schema drifted")
    if payload.get("status") != PLAN_STATUS or payload.get("change_policy") != CHANGE_POLICY:
        raise ValueError("candidate series plan authority drifted")
    count = _nonnegative_integer(payload.get("planned_session_count"), "planned_session_count")
    target_end = date.fromisoformat(_date_text(payload.get("target_end"), "target_end"))
    expected = build_candidate_series_plan(
        calendar=calendar,
        policy=policy,
        price_dataset_reference=price_dataset_reference,
        target_end=target_end,
        session_count=count,
    )
    if dict(payload) != expected:
        raise ValueError("candidate series plan differs from reviewed reconstruction")
    return tuple(
        (
            date.fromisoformat(item["source_session"]),
            date.fromisoformat(item["target_session"]),
        )
        for item in expected["session_pairs"]
    )


def build_candidate_series_manifest(
    *,
    plan: Mapping[str, Any],
    batches: Sequence[Mapping[str, Any]],
    calendar: ReviewedEquitySessionCalendar,
    policy: InstitutionalMvpDailyPolicy,
) -> dict[str, Any]:
    """Aggregate exactly pinned, independently verified daily candidate batches."""
    _verify_identity(plan, "finmind-institutional-mvp-series-plan-v1")
    if plan.get("schema_version") != PLAN_SCHEMA_VERSION or plan.get("status") != PLAN_STATUS:
        raise ValueError("candidate series plan contract drifted")
    pairs = plan.get("session_pairs")
    if not isinstance(pairs, list) or len(batches) != len(pairs):
        raise ValueError("candidate series requires one batch for every planned session")
    if len(pairs) < MINIMUM_OVERLAPPING_TARGET_SESSIONS:
        raise ValueError("candidate series requires at least 60 planned sessions")
    planned_targets = [item.get("target_session") for item in pairs if isinstance(item, Mapping)]
    if len(planned_targets) != len(pairs) or len(set(planned_targets)) != len(pairs):
        raise ValueError("candidate series plan target sessions must be unique")
    batch_references: list[dict[str, Any]] = []
    expected_calendar_evidence = {
        "coverage_end": calendar.coverage_end.isoformat(),
        "coverage_start": calendar.coverage_start.isoformat(),
        "schema_version": calendar.schema_version,
        "scope": "TWSE_REVIEWED_PROXY_FOR_CURRENT_TWSE_TPEX_MVP",
        "source_digest": calendar.source_digest,
        "timezone": calendar.timezone,
    }
    for planned, batch in zip(pairs, batches):
        if not isinstance(planned, Mapping) or not isinstance(batch, Mapping):
            raise ValueError("candidate series pairs and batches must be objects")
        verify_candidate_batch_payload(
            batch,
            next_session_resolver=calendar.next_trading_day,
            expected_policy_digest=policy.canonical_sha256,
            expected_base_policy_digest=policy.base_policy_digest,
            expected_calendar_digest=calendar.source_digest,
        )
        if batch.get("calendar_evidence") != expected_calendar_evidence:
            raise ValueError("candidate batch calendar evidence differs from reviewed calendar")
        source_session = _date_text(batch.get("source_session"), "batch source_session")
        target_session = _date_text(batch.get("target_session"), "batch target_session")
        if source_session != planned.get("source_session") or target_session != planned.get(
            "target_session"
        ):
            raise ValueError("candidate batch differs from frozen session plan")
        observation = _mapping(batch.get("candidate_observation"), "candidate_observation")
        source = _mapping(batch.get("source_evidence"), "source_evidence")
        batch_policy = _mapping(batch.get("candidate_policy"), "candidate_policy")
        batch_calendar = _mapping(batch.get("calendar_evidence"), "calendar_evidence")
        candidates = observation.get("candidates")
        if not isinstance(candidates, list):
            raise ValueError("candidate list is invalid")
        batch_references.append(
            {
                "artifact_digest": _digest(batch.get("artifact_digest"), "batch digest"),
                "artifact_id": _text(batch.get("artifact_id"), "batch artifact_id"),
                "candidate_count": _nonnegative_integer(
                    observation.get("count"), "candidate_count"
                ),
                "candidate_count_before_limit": _nonnegative_integer(
                    source.get("candidate_count_before_limit"),
                    "candidate_count_before_limit",
                ),
                "candidate_policy_digest": _digest(
                    batch_policy.get("canonical_sha256"), "candidate_policy_digest"
                ),
                "candidates": [
                    {
                        "entry_digest": _digest(item.get("entry_digest"), "entry_digest"),
                        "market": _text(item.get("market"), "candidate market"),
                        "rank": _positive_integer(item.get("rank"), "candidate rank"),
                        "symbol": _text(item.get("symbol"), "candidate symbol"),
                    }
                    for item in candidates
                    if isinstance(item, Mapping)
                ],
                "expires_at": _text(batch.get("expires_at"), "batch expires_at"),
                "calendar_digest": _digest(
                    batch_calendar.get("source_digest"), "calendar_digest"
                ),
                "flow_raw_sha256": _digest(
                    source.get("flow_raw_sha256"), "flow_raw_sha256"
                ),
                "flow_source_rows": _nonnegative_integer(
                    source.get("flow_source_rows"), "flow_source_rows"
                ),
                "mapped_flow_rows": _nonnegative_integer(
                    source.get("mapped_flow_rows"), "mapped_flow_rows"
                ),
                "provider": _text(source.get("provider"), "provider"),
                "source_fingerprint": _digest(
                    batch.get("source_fingerprint"), "source_fingerprint"
                ),
                "source_session": source_session,
                "source_version": _text(source.get("source_version"), "source_version"),
                "stock_info_raw_sha256": _digest(
                    source.get("stock_info_raw_sha256"), "stock_info_raw_sha256"
                ),
                "stock_info_source_rows": _positive_integer(
                    source.get("stock_info_source_rows"), "stock_info_source_rows"
                ),
                "target_session": target_session,
                "unmapped_flow_rows": _nonnegative_integer(
                    source.get("unmapped_flow_rows"), "unmapped_flow_rows"
                ),
            }
        )
    if any(len(item["candidates"]) != item["candidate_count"] for item in batch_references):
        raise ValueError("candidate series projection dropped a candidate entry")
    body: dict[str, Any] = {
        "batch_count": len(batch_references),
        "batch_references": batch_references,
        "candidate_policy_reference": dict(plan["candidate_policy_reference"]),
        "change_policy": CHANGE_POLICY,
        "evidence_scope": {
            "backtest_or_holdout_read": False,
            "institutional_flow_fields_read": True,
            "price_or_kbar_read": False,
            "return_or_pnl_read": False,
        },
        "execution_permissions": dict(_SERIES_PERMISSIONS),
        "limitations": list(_LIMITATIONS),
        "overlapping_target_session_count": len(batch_references),
        "price_dataset_reference": dict(plan["price_dataset_reference"]),
        "research_eligibility": {
            "formal_pit_eligible": False,
            "research_eligible": False,
        },
        "schema_version": SERIES_SCHEMA_VERSION,
        "series_plan_reference": {
            "artifact_digest": plan["artifact_digest"],
            "artifact_id": plan["artifact_id"],
            "source_sessions_digest": plan["source_sessions_digest"],
            "target_sessions_digest": plan["target_sessions_digest"],
        },
        "status": SERIES_STATUS,
    }
    return _with_identity(body, "finmind-institutional-mvp-candidate-series-v1")


def verify_candidate_series_manifest(
    payload: Mapping[str, Any],
    *,
    plan: Mapping[str, Any],
    batches: Sequence[Mapping[str, Any]],
    calendar: ReviewedEquitySessionCalendar,
    policy: InstitutionalMvpDailyPolicy,
) -> None:
    _verify_identity(payload, "finmind-institutional-mvp-candidate-series-v1")
    expected = build_candidate_series_manifest(
        plan=plan,
        batches=batches,
        calendar=calendar,
        policy=policy,
    )
    if dict(payload) != expected:
        raise ValueError("candidate series manifest differs from exact batch reconstruction")


def publish_content_addressed_json(
    root: Path, *, category: str, payload: Mapping[str, Any]
) -> tuple[Path, bool]:
    """Publish canonical bytes once; return ``(path, created)``."""
    expected_schema = _SCHEMA_BY_CATEGORY.get(category)
    if expected_schema is None:
        raise ValueError("unsupported institutional series artifact category")
    if payload.get("schema_version") != expected_schema:
        raise InstitutionalMvpSeriesError(
            "artifact schema does not match publication category"
        )
    digest = _verify_content_addressed_identity(payload)
    encoded = (canonical_json(payload) + "\n").encode("utf-8")
    root_path = Path(root)
    destination = root_path / category / f"{digest}.json"
    root_descriptor: int | None = None
    directory_descriptor: int | None = None
    lock_descriptor: int | None = None
    try:
        try:
            _require_no_symlink_components(root_path, allow_missing=True)
            root_path.mkdir(parents=True, exist_ok=True)
            _require_no_symlink_components(root_path)
            root_descriptor = _open_directory_nofollow(root_path)
            try:
                os.mkdir(category, mode=0o750, dir_fd=root_descriptor)
                os.fsync(root_descriptor)
            except FileExistsError:
                pass
            directory_descriptor = _open_directory_at(root_descriptor, category)
            lock_descriptor = _open_publish_lock(directory_descriptor)
            fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
            _cleanup_stale_temporaries(directory_descriptor, digest)

            existing = _read_regular_at(
                directory_descriptor,
                f"{digest}.json",
                missing_ok=True,
            )
            if existing is not None:
                if existing != encoded:
                    raise InstitutionalMvpSeriesError(
                        "content-addressed artifact bytes conflict"
                    )
                return destination, False

            temporary_name = f".{digest}.{uuid.uuid4().hex}.tmp"
            temporary_descriptor = os.open(
                temporary_name,
                os.O_WRONLY
                | os.O_CREAT
                | os.O_EXCL
                | os.O_CLOEXEC
                | os.O_NOFOLLOW,
                0o440,
                dir_fd=directory_descriptor,
            )
            with os.fdopen(temporary_descriptor, "wb") as output:
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())

            created = False
            try:
                os.link(
                    temporary_name,
                    f"{digest}.json",
                    src_dir_fd=directory_descriptor,
                    dst_dir_fd=directory_descriptor,
                    follow_symlinks=False,
                )
                created = True
                os.fsync(directory_descriptor)
            except FileExistsError:
                existing = _read_regular_at(
                    directory_descriptor,
                    f"{digest}.json",
                    missing_ok=False,
                )
                if existing != encoded:
                    raise InstitutionalMvpSeriesError(
                        "content-addressed concurrent publication conflicted"
                    )
            finally:
                os.unlink(temporary_name, dir_fd=directory_descriptor)
                os.fsync(directory_descriptor)

            if _read_regular_at(
                directory_descriptor,
                f"{digest}.json",
                missing_ok=False,
            ) != encoded:
                raise InstitutionalMvpSeriesError(
                    "content-addressed publication verification failed"
                )
            return destination, created
        except InstitutionalMvpSeriesError:
            raise
        except OSError as error:
            raise InstitutionalMvpSeriesError(
                "content-addressed publication path is unsafe"
            ) from error
    finally:
        if lock_descriptor is not None:
            os.close(lock_descriptor)
        if directory_descriptor is not None:
            os.close(directory_descriptor)
        if root_descriptor is not None:
            os.close(root_descriptor)


def load_canonical_artifact(path: Path) -> Mapping[str, Any]:
    try:
        _require_no_symlink_components(Path(path))
        encoded = _read_regular_path_nofollow(Path(path))
    except OSError as error:
        raise InstitutionalMvpSeriesError(
            "institutional series artifact path is unsafe"
        ) from error
    try:
        payload = json.loads(encoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise InstitutionalMvpSeriesError("institutional series artifact is invalid") from error
    if not isinstance(payload, Mapping):
        raise InstitutionalMvpSeriesError("institutional series artifact must be an object")
    if encoded != (canonical_json(payload) + "\n").encode("utf-8"):
        raise InstitutionalMvpSeriesError("institutional series artifact is not canonical")
    digest = _verify_content_addressed_identity(payload)
    if Path(path).name != f"{digest}.json":
        raise InstitutionalMvpSeriesError("institutional series artifact filename drifted")
    return payload


def _verify_content_addressed_identity(payload: Mapping[str, Any]) -> str:
    schema = payload.get("schema_version")
    prefix = _ARTIFACT_PREFIX_BY_SCHEMA.get(schema)
    if prefix is None:
        raise InstitutionalMvpSeriesError("unsupported content-addressed artifact schema")
    try:
        _verify_identity(payload, prefix)
        return _digest(payload.get("artifact_digest"), "artifact_digest")
    except ValueError as error:
        raise InstitutionalMvpSeriesError(
            "content-addressed artifact digest or identity is invalid"
        ) from error


def _open_directory_nofollow(path: Path) -> int:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    _require_owned_directory(descriptor)
    return descriptor


def _open_directory_at(parent_descriptor: int, name: str) -> int:
    descriptor = os.open(
        name,
        os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC | os.O_NOFOLLOW,
        dir_fd=parent_descriptor,
    )
    _require_owned_directory(descriptor)
    return descriptor


def _open_publish_lock(directory_descriptor: int) -> int:
    common_flags = os.O_RDWR | os.O_CLOEXEC | os.O_NOFOLLOW
    created = False
    try:
        descriptor = os.open(
            ".publish.lock",
            common_flags | os.O_CREAT | os.O_EXCL,
            0o600,
            dir_fd=directory_descriptor,
        )
        created = True
    except FileExistsError:
        descriptor = os.open(
            ".publish.lock",
            common_flags,
            dir_fd=directory_descriptor,
        )
    metadata = os.fstat(descriptor)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_uid != os.getuid()
        or metadata.st_nlink != 1
    ):
        os.close(descriptor)
        raise InstitutionalMvpSeriesError(
            "content-addressed publication lock is unsafe"
        )
    os.fchmod(descriptor, 0o600)
    os.fsync(descriptor)
    if created:
        os.fsync(directory_descriptor)
    return descriptor


def _cleanup_stale_temporaries(directory_descriptor: int, digest: str) -> None:
    prefix = f".{digest}."
    removed = False
    for name in os.listdir(directory_descriptor):
        if not name.startswith(prefix) or not name.endswith(".tmp"):
            continue
        nonce = name[len(prefix) : -4]
        if len(nonce) != 32 or any(
            character not in "0123456789abcdef" for character in nonce
        ):
            continue
        metadata = os.stat(
            name,
            dir_fd=directory_descriptor,
            follow_symlinks=False,
        )
        if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
            raise InstitutionalMvpSeriesError(
                "content-addressed stale temporary is unsafe"
            )
        os.unlink(name, dir_fd=directory_descriptor)
        removed = True
    if removed:
        os.fsync(directory_descriptor)


def _require_no_symlink_components(
    path: Path, *, allow_missing: bool = False
) -> None:
    absolute = path.absolute()
    for component in (absolute, *absolute.parents):
        try:
            metadata = os.lstat(component)
        except FileNotFoundError:
            if allow_missing:
                continue
            raise
        if stat.S_ISLNK(metadata.st_mode):
            raise InstitutionalMvpSeriesError(
                "content-addressed artifact path contains a symlink"
            )


def _require_owned_directory(descriptor: int) -> None:
    metadata = os.fstat(descriptor)
    if not stat.S_ISDIR(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise InstitutionalMvpSeriesError(
            "content-addressed artifact directory is unsafe"
        )


def _read_regular_at(
    directory_descriptor: int,
    name: str,
    *,
    missing_ok: bool,
) -> bytes | None:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
            dir_fd=directory_descriptor,
        )
    except FileNotFoundError:
        if missing_ok:
            return None
        raise
    with os.fdopen(descriptor, "rb") as artifact:
        _require_owned_single_link_regular(artifact.fileno())
        return artifact.read()


def _read_regular_path_nofollow(path: Path) -> bytes:
    descriptor = os.open(
        path,
        os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW,
    )
    with os.fdopen(descriptor, "rb") as artifact:
        _require_owned_single_link_regular(artifact.fileno())
        return artifact.read()


def _require_owned_single_link_regular(descriptor: int) -> None:
    metadata = os.fstat(descriptor)
    if not stat.S_ISREG(metadata.st_mode) or metadata.st_uid != os.getuid():
        raise InstitutionalMvpSeriesError(
            "content-addressed artifact must be an owner-controlled regular file"
        )
    if metadata.st_nlink != 1:
        raise InstitutionalMvpSeriesError(
            "content-addressed artifact link count is unsafe"
        )


def _with_identity(body: Mapping[str, Any], prefix: str) -> dict[str, Any]:
    digest = sha256_text(canonical_json(body))
    return {
        "artifact_digest": digest,
        "artifact_id": f"{prefix}-{digest[:20]}",
        **body,
    }


def _verify_identity(payload: Mapping[str, Any], prefix: str) -> None:
    identity = dict(payload)
    digest = _digest(identity.pop("artifact_digest", None), "artifact_digest")
    artifact_id = _text(identity.pop("artifact_id", None), "artifact_id")
    if sha256_text(canonical_json(identity)) != digest:
        raise ValueError("institutional series artifact digest mismatch")
    if artifact_id != f"{prefix}-{digest[:20]}":
        raise ValueError("institutional series artifact id mismatch")


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise ValueError(f"{field_name} must be canonical non-empty text")
    return value


def _date_text(value: object, field_name: str) -> str:
    parsed = _text(value, field_name)
    if date.fromisoformat(parsed).isoformat() != parsed:
        raise ValueError(f"{field_name} must be a canonical ISO date")
    return parsed


def _digest(value: object, field_name: str) -> str:
    parsed = _text(value, field_name)
    if len(parsed) != 64 or any(character not in "0123456789abcdef" for character in parsed):
        raise ValueError(f"{field_name} must be lowercase SHA-256")
    return parsed


def _text_sequence(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError(f"{field_name} must be a list")
    result = tuple(_text(item, field_name) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field_name} must not contain duplicates")
    return result


def _nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    parsed = _nonnegative_integer(value, field_name)
    if parsed == 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed
