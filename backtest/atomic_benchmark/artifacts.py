"""Canonical immutable artifact primitives for the R6 benchmark.

This adapter only builds and verifies bytes.  It has no filesystem locator and
cannot bypass the later PostgreSQL quarantine or seven-of-seven release gate.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

from backtest.domain import digest

from .domain import (
    ALGORITHM_CONTRACT_DIGEST,
    COST_IDENTITY,
    COST_IDENTITY_DIGEST,
    EPISODE_ROW_SCHEMA,
    LEDGER_ROW_SCHEMA,
    MATCH_ROW_SCHEMA,
    AtomicBenchmarkIntegrityError,
    MatchPlanBuild,
    build_summary,
    canonical_object_bytes,
    canonical_rows,
    compare_layers,
    layer_multiplicity_digest,
    require_exact_fields,
    require_sha256,
    verify_episode_row,
    verify_ledger_row,
    verify_match_row,
    verify_summary,
)


LEDGER_MANIFEST_SCHEMA_V1 = "r6-ledger-manifest-v1"
MATCH_MANIFEST_SCHEMA_V1 = "r6-match-manifest-v1"
LEDGER_MANIFEST_SCHEMA = "r6-ledger-manifest-v2"
MATCH_MANIFEST_SCHEMA = "r6-match-manifest-v2"
RESULT_MANIFEST_SCHEMA = "r6-result-manifest-v1"
POSTFLIGHT_SCHEMA = "r6-postflight-v1"
FAMILY_RELEASE_SCHEMA = "r6-family-release-v1"
PUBLIC_BUNDLE_SCHEMA = "r6-public-family-bundle-v1"
PUBLIC_BUNDLE_PAYLOAD_CONTRACT = "r6-public-family-bundle-payload-v1"
EPISODE_CHUNK_ROW_LIMIT = 10000


def _self_digest(value: Mapping[str, Any], field: str) -> str:
    return digest({key: item for key, item in value.items() if key != field})


def _verify_self_digest(value: Mapping[str, Any], field: str, label: str) -> None:
    require_sha256(value[field], field)
    if value[field] != _self_digest(value, field):
        raise AtomicBenchmarkIntegrityError(f"{label} digest cannot rebuild")


def _nonempty_string(value: object, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise AtomicBenchmarkIntegrityError(f"{label} must be non-empty string")
    return value


def _integer(value: object, label: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise AtomicBenchmarkIntegrityError(f"{label} must be integer >= {minimum}")
    return value


def _boolean(value: object, label: str) -> bool:
    if type(value) is not bool:
        raise AtomicBenchmarkIntegrityError(f"{label} must be exact boolean")
    return value


def _parse_canonical_object_member(content: bytes, label: str) -> dict[str, Any]:
    try:
        decoded = content.decode("utf-8")
        value = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AtomicBenchmarkIntegrityError(f"{label} is not canonical JSON") from error
    if not isinstance(value, Mapping):
        raise AtomicBenchmarkIntegrityError(f"{label} must be JSON object")
    document = dict(value)
    if canonical_object_bytes(document) != content:
        raise AtomicBenchmarkIntegrityError(f"{label} bytes are not canonical")
    return document


def _parse_canonical_episode_chunks(
    chunks: Sequence[bytes],
) -> tuple[
    tuple[dict[str, Any], ...],
    bytes,
    tuple[tuple[dict[str, Any], ...], ...],
]:
    rows: list[dict[str, Any]] = []
    rows_by_chunk: list[tuple[dict[str, Any], ...]] = []
    payload = b"".join(chunks)
    for content in chunks:
        chunk_rows: list[dict[str, Any]] = []
        if content and not content.endswith(b"\n"):
            raise AtomicBenchmarkIntegrityError("episode chunk requires trailing LF")
        for line in content.splitlines(keepends=True):
            if line == b"\n":
                raise AtomicBenchmarkIntegrityError("episode chunk rejects blank row")
            row = verify_episode_row(
                _parse_canonical_object_member(line, "episode row")
            )
            if row["sequence"] != len(rows) + 1:
                raise AtomicBenchmarkIntegrityError("episode sequence drift")
            rows.append(row)
            chunk_rows.append(row)
        rows_by_chunk.append(tuple(chunk_rows))
    return tuple(rows), payload, tuple(rows_by_chunk)


_COMMON_MANIFEST_FIELDS = frozenset(
    {
        "matrix_id",
        "registration_digest",
        "family_id",
        "research_baseline_digest",
        "slot_sequence",
        "hypothesis_id",
        "strategy_id",
        "strategy_version_id",
        "strategy_configuration_digest",
        "strategy_implementation_digest",
        "lifecycle_sequence",
        "lifecycle_event_id",
        "lifecycle_projection_digest",
        "dataset_id",
        "dataset_digest",
        "dataset_bars_sha256",
        "dataset_binding_revision",
        "protocol_core_digest",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
    }
)

_LEDGER_MANIFEST_FIELDS = _COMMON_MANIFEST_FIELDS | frozenset(
    {
        "schema_version",
        "ledger_row_schema_version",
        "ledger_signal_count",
        "ledger_rows_sha256",
        "ledger_signal_multiplicity_digest",
        "ledger_manifest_digest",
        "eligibility_manifest_digest",
    }
)
_LEDGER_MANIFEST_FIELDS_V1 = _LEDGER_MANIFEST_FIELDS - frozenset(
    {"eligibility_manifest_digest"}
)


def _verify_common_identity(value: Mapping[str, Any]) -> None:
    for field in (
        "matrix_id",
        "family_id",
        "strategy_id",
        "strategy_version_id",
        "lifecycle_event_id",
        "dataset_id",
    ):
        _nonempty_string(value[field], field)
    for field in (
        "registration_digest",
        "research_baseline_digest",
        "hypothesis_id",
        "strategy_configuration_digest",
        "strategy_implementation_digest",
        "lifecycle_projection_digest",
        "dataset_digest",
        "dataset_bars_sha256",
        "protocol_core_digest",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
    ):
        require_sha256(value[field], field)
    for field in ("slot_sequence", "lifecycle_sequence", "dataset_binding_revision"):
        _integer(value[field], field, minimum=1)
    if value["algorithm_contract_digest"] != ALGORITHM_CONTRACT_DIGEST:
        raise AtomicBenchmarkIntegrityError("algorithm contract digest drift")


def _verify_row_lineage(row: Mapping[str, Any], identity: Mapping[str, Any]) -> None:
    pairs = {
        "matrix_id": "matrix_id",
        "registration_digest": "registration_digest",
        "slot_sequence": "slot_sequence",
        "hypothesis_id": "hypothesis_id",
        "strategy_id": "strategy_id",
        "strategy_version_id": "strategy_version_id",
        "strategy_configuration_digest": "strategy_configuration_digest",
        "strategy_implementation_digest": "strategy_implementation_digest",
    }
    for row_field, identity_field in pairs.items():
        if row_field in row and row[row_field] != identity[identity_field]:
            raise AtomicBenchmarkIntegrityError(f"row lineage mismatch: {row_field}")


def build_ledger_manifest(
    *,
    identity: Mapping[str, Any],
    ledger_rows: Iterable[Mapping[str, Any]],
    eligibility_manifest_digest: str | None = None,
) -> dict[str, Any]:
    common = dict(identity)
    require_exact_fields(common, _COMMON_MANIFEST_FIELDS, "ledger identity")
    _verify_common_identity(common)
    rows, payload = canonical_rows(ledger_rows, verify_ledger_row)
    for row in rows:
        _verify_row_lineage(row, common)
    body = {
        "schema_version": (
            LEDGER_MANIFEST_SCHEMA
            if eligibility_manifest_digest is not None
            else LEDGER_MANIFEST_SCHEMA_V1
        ),
        **common,
        "ledger_row_schema_version": LEDGER_ROW_SCHEMA,
        "ledger_signal_count": len(rows),
        "ledger_rows_sha256": hashlib.sha256(payload).hexdigest(),
        "ledger_signal_multiplicity_digest": layer_multiplicity_digest(rows),
    }
    if eligibility_manifest_digest is not None:
        body["eligibility_manifest_digest"] = require_sha256(
            eligibility_manifest_digest, "eligibility_manifest_digest"
        )
    return verify_ledger_manifest(
        {**body, "ledger_manifest_digest": digest(body)}
    )


def verify_ledger_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = dict(value)
    schema = manifest.get("schema_version")
    expected_fields = (
        _LEDGER_MANIFEST_FIELDS
        if schema == LEDGER_MANIFEST_SCHEMA
        else _LEDGER_MANIFEST_FIELDS_V1
    )
    require_exact_fields(manifest, expected_fields, "ledger manifest")
    if schema not in (LEDGER_MANIFEST_SCHEMA_V1, LEDGER_MANIFEST_SCHEMA) or manifest[
        "ledger_row_schema_version"
    ] != LEDGER_ROW_SCHEMA:
        raise AtomicBenchmarkIntegrityError("ledger manifest schema drift")
    _verify_common_identity(manifest)
    _integer(manifest["ledger_signal_count"], "ledger_signal_count")
    for field in (
        "ledger_rows_sha256",
        "ledger_signal_multiplicity_digest",
        "ledger_manifest_digest",
    ):
        require_sha256(manifest[field], field)
    if schema == LEDGER_MANIFEST_SCHEMA:
        require_sha256(
            manifest["eligibility_manifest_digest"],
            "eligibility_manifest_digest",
        )
    _verify_self_digest(manifest, "ledger_manifest_digest", "ledger manifest")
    canonical_object_bytes(manifest)
    return manifest


_MATCH_MANIFEST_FIELDS = _COMMON_MANIFEST_FIELDS | frozenset(
    {
        "schema_version",
        "ledger_manifest_digest",
        "ledger_rows_sha256",
        "match_row_schema_version",
        "signal_count",
        "matched_entry_count",
        "matched_exit_count",
        "missing_entry_count",
        "missing_exit_count",
        "duplicate_match_count",
        "match_rows_sha256",
        "match_signal_multiplicity_digest",
        "match_manifest_digest",
        "eligibility_manifest_digest",
    }
)
_MATCH_MANIFEST_FIELDS_V1 = _MATCH_MANIFEST_FIELDS - frozenset(
    {"eligibility_manifest_digest"}
)


def build_match_manifest(
    *, ledger_manifest: Mapping[str, Any], match_plan: MatchPlanBuild
) -> dict[str, Any]:
    ledger = verify_ledger_manifest(ledger_manifest)
    for row in match_plan.rows:
        _verify_row_lineage(row, ledger)
    body = {
        "schema_version": (
            MATCH_MANIFEST_SCHEMA
            if ledger["schema_version"] == LEDGER_MANIFEST_SCHEMA
            else MATCH_MANIFEST_SCHEMA_V1
        ),
        **{field: ledger[field] for field in _COMMON_MANIFEST_FIELDS},
        "ledger_manifest_digest": ledger["ledger_manifest_digest"],
        "ledger_rows_sha256": ledger["ledger_rows_sha256"],
        "match_row_schema_version": MATCH_ROW_SCHEMA,
        "signal_count": match_plan.signal_count,
        "matched_entry_count": len(match_plan.rows),
        "matched_exit_count": len(match_plan.rows),
        "missing_entry_count": match_plan.missing_entry_count,
        "missing_exit_count": match_plan.missing_exit_count,
        "duplicate_match_count": match_plan.duplicate_match_count,
        "match_rows_sha256": match_plan.rows_sha256,
        "match_signal_multiplicity_digest": match_plan.signal_multiplicity_digest,
    }
    if ledger["schema_version"] == LEDGER_MANIFEST_SCHEMA:
        body["eligibility_manifest_digest"] = ledger[
            "eligibility_manifest_digest"
        ]
    return verify_match_manifest({**body, "match_manifest_digest": digest(body)})


def verify_match_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = dict(value)
    schema = manifest.get("schema_version")
    expected_fields = (
        _MATCH_MANIFEST_FIELDS
        if schema == MATCH_MANIFEST_SCHEMA
        else _MATCH_MANIFEST_FIELDS_V1
    )
    require_exact_fields(manifest, expected_fields, "match manifest")
    if schema not in (MATCH_MANIFEST_SCHEMA_V1, MATCH_MANIFEST_SCHEMA) or manifest[
        "match_row_schema_version"
    ] != MATCH_ROW_SCHEMA:
        raise AtomicBenchmarkIntegrityError("match manifest schema drift")
    _verify_common_identity(manifest)
    for field in (
        "signal_count",
        "matched_entry_count",
        "matched_exit_count",
        "missing_entry_count",
        "missing_exit_count",
        "duplicate_match_count",
    ):
        _integer(manifest[field], field)
    for field in (
        "ledger_manifest_digest",
        "ledger_rows_sha256",
        "match_rows_sha256",
        "match_signal_multiplicity_digest",
        "match_manifest_digest",
    ):
        require_sha256(manifest[field], field)
    if schema == MATCH_MANIFEST_SCHEMA:
        require_sha256(
            manifest["eligibility_manifest_digest"],
            "eligibility_manifest_digest",
        )
    if manifest["matched_entry_count"] != manifest["matched_exit_count"]:
        raise AtomicBenchmarkIntegrityError("matched entry/exit counts differ")
    if manifest["signal_count"] != (
        manifest["matched_entry_count"]
        + manifest["missing_entry_count"]
        + manifest["missing_exit_count"]
    ):
        raise AtomicBenchmarkIntegrityError("match counts cannot reconcile")
    _verify_self_digest(manifest, "match_manifest_digest", "match manifest")
    canonical_object_bytes(manifest)
    return manifest


_RESULT_MANIFEST_FIELDS = _COMMON_MANIFEST_FIELDS | frozenset(
    {
        "schema_version",
        "replay_id",
        "cost_identity_digest",
        "ledger_manifest_digest",
        "match_manifest_digest",
        "episode_row_schema_version",
        "episode_count",
        "episode_rows_sha256",
        "episode_signal_multiplicity_digest",
        "summary",
        "summary_digest",
        "result_projection_digest",
        "result_manifest_digest",
    }
)


def build_result_manifest(
    *,
    replay_id: str,
    match_manifest: Mapping[str, Any],
    episode_rows: Iterable[Mapping[str, Any]],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    match = verify_match_manifest(match_manifest)
    episodes, payload = canonical_rows(episode_rows, verify_episode_row)
    for row in episodes:
        _verify_row_lineage(row, match)
    verified_summary = verify_summary(summary)
    if verified_summary["episode_count"] != len(episodes):
        raise AtomicBenchmarkIntegrityError("summary/episode count mismatch")
    rebuilt_summary = build_summary(
        episodes,
        family_id=match["family_id"],
        hypothesis_id=match["hypothesis_id"],
        dataset_limitations=tuple(verified_summary["limitations"][1:]),
    )
    if rebuilt_summary != verified_summary:
        raise AtomicBenchmarkIntegrityError("summary cannot rebuild from episodes")
    summary_digest = digest(verified_summary)
    episode_sha = hashlib.sha256(payload).hexdigest()
    episode_parity = layer_multiplicity_digest(episodes)
    result_projection = {
        "cost_identity_digest": COST_IDENTITY_DIGEST,
        "episode_rows_sha256": episode_sha,
        "episode_signal_multiplicity_digest": episode_parity,
        "summary_digest": summary_digest,
    }
    body = {
        "schema_version": RESULT_MANIFEST_SCHEMA,
        "replay_id": _nonempty_string(replay_id, "replay_id"),
        **{field: match[field] for field in _COMMON_MANIFEST_FIELDS},
        "cost_identity_digest": COST_IDENTITY_DIGEST,
        "ledger_manifest_digest": match["ledger_manifest_digest"],
        "match_manifest_digest": match["match_manifest_digest"],
        "episode_row_schema_version": EPISODE_ROW_SCHEMA,
        "episode_count": len(episodes),
        "episode_rows_sha256": episode_sha,
        "episode_signal_multiplicity_digest": episode_parity,
        "summary": verified_summary,
        "summary_digest": summary_digest,
        "result_projection_digest": digest(result_projection),
    }
    return verify_result_manifest({**body, "result_manifest_digest": digest(body)})


def verify_result_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = dict(value)
    require_exact_fields(manifest, _RESULT_MANIFEST_FIELDS, "result manifest")
    if (
        manifest["schema_version"] != RESULT_MANIFEST_SCHEMA
        or manifest["episode_row_schema_version"] != EPISODE_ROW_SCHEMA
    ):
        raise AtomicBenchmarkIntegrityError("result manifest schema drift")
    _verify_common_identity(manifest)
    _nonempty_string(manifest["replay_id"], "replay_id")
    _integer(manifest["episode_count"], "episode_count")
    for field in (
        "cost_identity_digest",
        "ledger_manifest_digest",
        "match_manifest_digest",
        "episode_rows_sha256",
        "episode_signal_multiplicity_digest",
        "summary_digest",
        "result_projection_digest",
        "result_manifest_digest",
    ):
        require_sha256(manifest[field], field)
    if manifest["cost_identity_digest"] != COST_IDENTITY_DIGEST:
        raise AtomicBenchmarkIntegrityError("result cost identity drift")
    summary = verify_summary(manifest["summary"])
    if summary["episode_count"] != manifest["episode_count"] or digest(summary) != manifest["summary_digest"]:
        raise AtomicBenchmarkIntegrityError("result summary cannot rebuild")
    projection = {
        "cost_identity_digest": manifest["cost_identity_digest"],
        "episode_rows_sha256": manifest["episode_rows_sha256"],
        "episode_signal_multiplicity_digest": manifest[
            "episode_signal_multiplicity_digest"
        ],
        "summary_digest": manifest["summary_digest"],
    }
    if digest(projection) != manifest["result_projection_digest"]:
        raise AtomicBenchmarkIntegrityError("result projection cannot rebuild")
    _verify_self_digest(manifest, "result_manifest_digest", "result manifest")
    canonical_object_bytes(manifest)
    return manifest


_DIAGNOSTIC_FIELDS = frozenset(
    {
        "source_bar_count",
        "source_bars_sha256",
        "source_eof_verified",
        "ledger_minus_match_count",
        "match_minus_ledger_count",
        "match_minus_episode_count",
        "episode_minus_match_count",
        "ledger_duplicate_count",
        "match_duplicate_count",
        "episode_duplicate_count",
        "missing_entry_count",
        "missing_exit_count",
    }
)
_CONDITION_FIELDS = frozenset(
    {
        "exact_identity",
        "dataset_verified",
        "version_lifecycle_verified",
        "row_schema_verified",
        "ledger_match_parity",
        "match_episode_parity",
        "cost_rebuilt",
        "summary_rebuilt",
        "no_incomplete_matches",
        "no_duplicates",
        "no_external_calls",
        "all_conditions_accepted",
    }
)
_POSTFLIGHT_FIELDS = frozenset(
    {
        "schema_version",
        "replay_id",
        "matrix_id",
        "registration_digest",
        "family_id",
        "research_baseline_digest",
        "slot_sequence",
        "hypothesis_id",
        "expected_ledger_manifest_digest",
        "actual_ledger_manifest_digest",
        "expected_match_manifest_digest",
        "actual_match_manifest_digest",
        "expected_result_manifest_digest",
        "actual_result_manifest_digest",
        "expected_result_projection_digest",
        "actual_result_projection_digest",
        "diagnostics",
        "recomputed_cost_identity",
        "recomputed_summary",
        "acceptance_conditions",
        "verdict",
        "postflight_digest",
    }
)


def build_postflight(
    *,
    ledger_manifest: Mapping[str, Any],
    ledger_rows: Sequence[Mapping[str, Any]],
    match_manifest: Mapping[str, Any],
    match_rows: Sequence[Mapping[str, Any]],
    result_manifest: Mapping[str, Any],
    episode_rows: Sequence[Mapping[str, Any]],
    source_bar_count: int,
    source_bars_sha256: str,
    source_eof_verified: bool,
    dataset_verified: bool,
    version_lifecycle_verified: bool,
    no_external_calls: bool,
) -> dict[str, Any]:
    source_eof = _boolean(source_eof_verified, "source_eof_verified")
    dataset_evidence = _boolean(dataset_verified, "dataset_verified")
    lifecycle_evidence = _boolean(
        version_lifecycle_verified, "version_lifecycle_verified"
    )
    external_call_evidence = _boolean(no_external_calls, "no_external_calls")
    ledger = verify_ledger_manifest(ledger_manifest)
    match = verify_match_manifest(match_manifest)
    result = verify_result_manifest(result_manifest)
    verified_ledger, ledger_payload = canonical_rows(ledger_rows, verify_ledger_row)
    verified_matches, match_payload = canonical_rows(match_rows, verify_match_row)
    verified_episodes, episode_payload = canonical_rows(episode_rows, verify_episode_row)
    ledger_match = compare_layers(verified_ledger, verified_matches)
    match_episode = compare_layers(verified_matches, verified_episodes)
    ledger_duplicates = sum(
        max(count - 1, 0)
        for count in Counter(row["signal_id"] for row in verified_ledger).values()
    )
    match_duplicates = sum(
        max(count - 1, 0)
        for count in Counter(row["match_id"] for row in verified_matches).values()
    )
    episode_duplicates = sum(
        max(count - 1, 0)
        for count in Counter(row["episode_id"] for row in verified_episodes).values()
    )
    exact_identity = (
        all(
            ledger[field] == match[field] == result[field]
            for field in _COMMON_MANIFEST_FIELDS
        )
        and match["ledger_manifest_digest"] == ledger["ledger_manifest_digest"]
        and result["ledger_manifest_digest"] == ledger["ledger_manifest_digest"]
        and result["match_manifest_digest"] == match["match_manifest_digest"]
    )
    row_schema_verified = (
        hashlib.sha256(ledger_payload).hexdigest() == ledger["ledger_rows_sha256"]
        and hashlib.sha256(match_payload).hexdigest() == match["match_rows_sha256"]
        and hashlib.sha256(episode_payload).hexdigest() == result["episode_rows_sha256"]
        and layer_multiplicity_digest(verified_ledger)
        == ledger["ledger_signal_multiplicity_digest"]
        and layer_multiplicity_digest(verified_matches)
        == match["match_signal_multiplicity_digest"]
        and layer_multiplicity_digest(verified_episodes)
        == result["episode_signal_multiplicity_digest"]
    )
    summary_rebuilt = (
        build_summary(
            verified_episodes,
            family_id=result["family_id"],
            hypothesis_id=result["hypothesis_id"],
            dataset_limitations=tuple(result["summary"]["limitations"][1:]),
        )
        == result["summary"]
    )
    diagnostics = {
        "source_bar_count": _integer(source_bar_count, "source_bar_count"),
        "source_bars_sha256": require_sha256(source_bars_sha256, "source_bars_sha256"),
        "source_eof_verified": source_eof,
        "ledger_minus_match_count": ledger_match.left_minus_right_count,
        "match_minus_ledger_count": ledger_match.right_minus_left_count,
        "match_minus_episode_count": match_episode.left_minus_right_count,
        "episode_minus_match_count": match_episode.right_minus_left_count,
        "ledger_duplicate_count": ledger_duplicates,
        "match_duplicate_count": match_duplicates,
        "episode_duplicate_count": episode_duplicates,
        "missing_entry_count": match["missing_entry_count"],
        "missing_exit_count": match["missing_exit_count"],
    }
    conditions = {
        "exact_identity": exact_identity,
        "dataset_verified": (
            dataset_evidence
            and source_eof
            and source_bars_sha256 == result["dataset_bars_sha256"]
        ),
        "version_lifecycle_verified": lifecycle_evidence,
        "row_schema_verified": row_schema_verified,
        "ledger_match_parity": ledger_match.equal,
        "match_episode_parity": match_episode.equal,
        "cost_rebuilt": all(
            row["cost_identity_digest"] == COST_IDENTITY_DIGEST
            for row in verified_episodes
        ),
        "summary_rebuilt": summary_rebuilt,
        "no_incomplete_matches": (
            match["missing_entry_count"] == match["missing_exit_count"] == 0
        ),
        "no_duplicates": ledger_duplicates == match_duplicates == episode_duplicates == 0,
        "no_external_calls": external_call_evidence,
    }
    conditions["all_conditions_accepted"] = all(conditions.values())
    body = {
        "schema_version": POSTFLIGHT_SCHEMA,
        "replay_id": result["replay_id"],
        "matrix_id": result["matrix_id"],
        "registration_digest": result["registration_digest"],
        "family_id": result["family_id"],
        "research_baseline_digest": result["research_baseline_digest"],
        "slot_sequence": result["slot_sequence"],
        "hypothesis_id": result["hypothesis_id"],
        "expected_ledger_manifest_digest": ledger["ledger_manifest_digest"],
        "actual_ledger_manifest_digest": ledger["ledger_manifest_digest"],
        "expected_match_manifest_digest": match["match_manifest_digest"],
        "actual_match_manifest_digest": match["match_manifest_digest"],
        "expected_result_manifest_digest": result["result_manifest_digest"],
        "actual_result_manifest_digest": result["result_manifest_digest"],
        "expected_result_projection_digest": result["result_projection_digest"],
        "actual_result_projection_digest": result["result_projection_digest"],
        "diagnostics": diagnostics,
        "recomputed_cost_identity": dict(COST_IDENTITY),
        "recomputed_summary": result["summary"],
        "acceptance_conditions": conditions,
        "verdict": "ACCEPTED" if conditions["all_conditions_accepted"] else "REJECTED",
    }
    return verify_postflight({**body, "postflight_digest": digest(body)})


def verify_postflight(value: Mapping[str, Any]) -> dict[str, Any]:
    postflight = dict(value)
    require_exact_fields(postflight, _POSTFLIGHT_FIELDS, "postflight")
    if postflight["schema_version"] != POSTFLIGHT_SCHEMA:
        raise AtomicBenchmarkIntegrityError("postflight schema drift")
    for field in ("replay_id", "matrix_id", "family_id"):
        _nonempty_string(postflight[field], field)
    _integer(postflight["slot_sequence"], "slot_sequence", minimum=1)
    for field in _POSTFLIGHT_FIELDS:
        if field.endswith("_digest"):
            require_sha256(postflight[field], field)
    diagnostics = dict(postflight["diagnostics"])
    require_exact_fields(diagnostics, _DIAGNOSTIC_FIELDS, "postflight diagnostics")
    for field in _DIAGNOSTIC_FIELDS - {"source_bars_sha256", "source_eof_verified"}:
        _integer(diagnostics[field], field)
    require_sha256(diagnostics["source_bars_sha256"], "source_bars_sha256")
    if not isinstance(diagnostics["source_eof_verified"], bool):
        raise AtomicBenchmarkIntegrityError("source_eof_verified must be boolean")
    conditions = dict(postflight["acceptance_conditions"])
    require_exact_fields(conditions, _CONDITION_FIELDS, "postflight conditions")
    if any(not isinstance(value, bool) for value in conditions.values()):
        raise AtomicBenchmarkIntegrityError("postflight conditions must be booleans")
    expected_all = all(
        value for key, value in conditions.items() if key != "all_conditions_accepted"
    )
    if conditions["all_conditions_accepted"] != expected_all:
        raise AtomicBenchmarkIntegrityError("postflight AND cannot rebuild")
    expected_verdict = "ACCEPTED" if expected_all else "REJECTED"
    if postflight["verdict"] != expected_verdict:
        raise AtomicBenchmarkIntegrityError("postflight verdict mismatch")
    if conditions["exact_identity"] and (
        postflight["expected_ledger_manifest_digest"]
        != postflight["actual_ledger_manifest_digest"]
        or postflight["expected_match_manifest_digest"]
        != postflight["actual_match_manifest_digest"]
        or postflight["expected_result_manifest_digest"]
        != postflight["actual_result_manifest_digest"]
        or postflight["expected_result_projection_digest"]
        != postflight["actual_result_projection_digest"]
    ):
        raise AtomicBenchmarkIntegrityError("postflight exact identity claims unequal roots")
    if postflight["recomputed_cost_identity"] != COST_IDENTITY:
        raise AtomicBenchmarkIntegrityError("postflight cost identity drift")
    verify_summary(postflight["recomputed_summary"])
    _verify_self_digest(postflight, "postflight_digest", "postflight")
    canonical_object_bytes(postflight)
    return postflight


_ACCEPTED_ATTEMPT_FIELDS = frozenset(
    {
        "slot_sequence",
        "attempt_id",
        "attempt_revision",
        "accepted_retry_generation",
        "hypothesis_id",
        "result_manifest_digest",
        "result_projection_digest",
        "postflight_digest",
    }
)
_FAMILY_RELEASE_FIELDS = frozenset(
    {
        "schema_version",
        "family_id",
        "matrix_id",
        "registration_digest",
        "research_baseline_digest",
        "protocol_core_digest",
        "family_head_sequence",
        "ordered_accepted_attempts",
    }
)


def build_family_release(
    *,
    family_id: str,
    matrix_id: str,
    registration_digest: str,
    research_baseline_digest: str,
    protocol_core_digest: str,
    accepted_attempts: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    body = {
        "schema_version": FAMILY_RELEASE_SCHEMA,
        "family_id": family_id,
        "matrix_id": matrix_id,
        "registration_digest": registration_digest,
        "research_baseline_digest": research_baseline_digest,
        "protocol_core_digest": protocol_core_digest,
        "family_head_sequence": 7,
        "ordered_accepted_attempts": [dict(item) for item in accepted_attempts],
    }
    verify_family_release(body)
    return {**body, "family_release_digest": digest(body)}


def verify_family_release(value: Mapping[str, Any]) -> dict[str, Any]:
    release = dict(value)
    has_digest = "family_release_digest" in release
    expected = _FAMILY_RELEASE_FIELDS | (
        frozenset({"family_release_digest"}) if has_digest else frozenset()
    )
    require_exact_fields(release, expected, "family release")
    if release["schema_version"] != FAMILY_RELEASE_SCHEMA or release["family_head_sequence"] != 7:
        raise AtomicBenchmarkIntegrityError("family release literal drift")
    for field in ("family_id", "matrix_id"):
        _nonempty_string(release[field], field)
    for field in (
        "registration_digest",
        "research_baseline_digest",
        "protocol_core_digest",
    ):
        require_sha256(release[field], field)
    attempts = release["ordered_accepted_attempts"]
    if not isinstance(attempts, list) or len(attempts) != 7:
        raise AtomicBenchmarkIntegrityError("family release requires seven attempts")
    for expected_slot, item in enumerate(attempts, start=1):
        require_exact_fields(dict(item), _ACCEPTED_ATTEMPT_FIELDS, "accepted attempt")
        if item["slot_sequence"] != expected_slot:
            raise AtomicBenchmarkIntegrityError("accepted attempt order drift")
        for field in ("attempt_revision", "accepted_retry_generation"):
            _integer(item[field], field, minimum=1)
        _nonempty_string(item["attempt_id"], "attempt_id")
        for field in (
            "hypothesis_id",
            "result_manifest_digest",
            "result_projection_digest",
            "postflight_digest",
        ):
            require_sha256(item[field], field)
    if has_digest:
        _verify_self_digest(release, "family_release_digest", "family release")
    canonical_object_bytes(release)
    return release


@dataclass(frozen=True)
class SlotBundleInput:
    result_manifest: Mapping[str, Any]
    postflight: Mapping[str, Any]
    episode_rows: Sequence[Mapping[str, Any]]


@dataclass(frozen=True)
class PublicBundle:
    manifest: dict[str, Any]
    members: tuple[tuple[str, bytes], ...]

    @property
    def manifest_bytes(self) -> bytes:
        return canonical_object_bytes(self.manifest)


def frame_member(path: str, content: bytes) -> bytes:
    path_bytes = path.encode("utf-8")
    if len(path_bytes) > (2**32 - 1) or len(content) > (2**64 - 1):
        raise AtomicBenchmarkIntegrityError("bundle member exceeds framing range")
    return len(path_bytes).to_bytes(4, "big") + path_bytes + len(content).to_bytes(8, "big") + content


def _chunk_episodes(
    *, slot: int, episode_rows: Sequence[Mapping[str, Any]]
) -> tuple[list[dict[str, Any]], list[tuple[str, bytes]], str]:
    episodes, payload = canonical_rows(episode_rows, verify_episode_row)
    descriptors: list[dict[str, Any]] = []
    members: list[tuple[str, bytes]] = []
    for index in range(0, len(episodes), EPISODE_CHUNK_ROW_LIMIT):
        chunk_sequence = (index // EPISODE_CHUNK_ROW_LIMIT) + 1
        selected = episodes[index : index + EPISODE_CHUNK_ROW_LIMIT]
        content = b"".join(canonical_object_bytes(row) for row in selected)
        path = f"slots/{slot:02d}/episodes/{chunk_sequence:08d}.jsonl"
        descriptors.append(
            {
                "chunk_sequence": chunk_sequence,
                "path": path,
                "row_start_sequence": index + 1,
                "row_end_sequence": index + len(selected),
                "row_count": len(selected),
                "byte_count": len(content),
                "sha256": hashlib.sha256(content).hexdigest(),
            }
        )
        members.append((path, content))
    return descriptors, members, hashlib.sha256(payload).hexdigest()


def build_public_bundle(
    *, family_release: Mapping[str, Any], slot_inputs: Sequence[SlotBundleInput]
) -> PublicBundle:
    release = verify_family_release(family_release)
    if "family_release_digest" not in release:
        raise AtomicBenchmarkIntegrityError("sealed family release digest required")
    if len(slot_inputs) != 7:
        raise AtomicBenchmarkIntegrityError("public bundle requires all seven slots")
    descriptors: list[dict[str, Any]] = []
    members: list[tuple[str, bytes]] = []
    for slot, (attempt, source) in enumerate(
        zip(release["ordered_accepted_attempts"], slot_inputs, strict=True), start=1
    ):
        result = verify_result_manifest(source.result_manifest)
        postflight = verify_postflight(source.postflight)
        if (
            result["slot_sequence"] != slot
            or postflight["slot_sequence"] != slot
            or result["family_id"] != release["family_id"]
            or postflight["family_id"] != release["family_id"]
            or result["matrix_id"] != release["matrix_id"]
            or postflight["matrix_id"] != release["matrix_id"]
            or result["registration_digest"] != release["registration_digest"]
            or postflight["registration_digest"] != release["registration_digest"]
            or result["hypothesis_id"] != attempt["hypothesis_id"]
            or postflight["hypothesis_id"] != attempt["hypothesis_id"]
            or result["result_manifest_digest"] != attempt["result_manifest_digest"]
            or result["result_projection_digest"] != attempt["result_projection_digest"]
            or postflight["postflight_digest"] != attempt["postflight_digest"]
            or postflight["expected_result_manifest_digest"]
            != result["result_manifest_digest"]
            or postflight["actual_result_manifest_digest"]
            != result["result_manifest_digest"]
            or postflight["expected_result_projection_digest"]
            != result["result_projection_digest"]
            or postflight["actual_result_projection_digest"]
            != result["result_projection_digest"]
            or postflight["recomputed_summary"] != result["summary"]
            or postflight["verdict"] != "ACCEPTED"
        ):
            raise AtomicBenchmarkIntegrityError("bundle slot/release identity mismatch")
        result_path = f"slots/{slot:02d}/result_manifest.json"
        postflight_path = f"slots/{slot:02d}/postflight.json"
        result_bytes = canonical_object_bytes(result)
        postflight_bytes = canonical_object_bytes(postflight)
        verified_episodes, _ = canonical_rows(source.episode_rows, verify_episode_row)
        for row in verified_episodes:
            _verify_row_lineage(row, result)
        chunks, episode_members, episode_sha = _chunk_episodes(
            slot=slot, episode_rows=verified_episodes
        )
        rebuilt_summary = build_summary(
            verified_episodes,
            family_id=result["family_id"],
            hypothesis_id=result["hypothesis_id"],
            dataset_limitations=tuple(result["summary"]["limitations"][1:]),
        )
        if (
            len(verified_episodes) != result["episode_count"]
            or episode_sha != result["episode_rows_sha256"]
            or rebuilt_summary != result["summary"]
        ):
            raise AtomicBenchmarkIntegrityError("bundle episode evidence mismatch")
        descriptors.append(
            {
                "slot_sequence": slot,
                "hypothesis_id": result["hypothesis_id"],
                "result_manifest_path": result_path,
                "result_manifest_digest": result["result_manifest_digest"],
                "result_manifest_byte_count": len(result_bytes),
                "result_manifest_file_sha256": hashlib.sha256(result_bytes).hexdigest(),
                "postflight_path": postflight_path,
                "postflight_digest": postflight["postflight_digest"],
                "postflight_byte_count": len(postflight_bytes),
                "postflight_file_sha256": hashlib.sha256(postflight_bytes).hexdigest(),
                "episode_count": result["episode_count"],
                "episode_rows_sha256": result["episode_rows_sha256"],
                "episode_chunks": chunks,
            }
        )
        members.extend(((result_path, result_bytes), (postflight_path, postflight_bytes)))
        members.extend(episode_members)
    payload = b"".join(frame_member(path, content) for path, content in members)
    body = {
        "schema_version": PUBLIC_BUNDLE_SCHEMA,
        "family_id": release["family_id"],
        "matrix_id": release["matrix_id"],
        "registration_digest": release["registration_digest"],
        "family_release_digest": release["family_release_digest"],
        "payload_contract_version": PUBLIC_BUNDLE_PAYLOAD_CONTRACT,
        "episode_chunk_row_limit": EPISODE_CHUNK_ROW_LIMIT,
        "ordered_slot_payloads": descriptors,
        "bundle_member_count": len(members),
        "bundle_content_byte_count": sum(len(content) for _, content in members),
        "bundle_payload_sha256": hashlib.sha256(payload).hexdigest(),
    }
    manifest = {**body, "bundle_manifest_digest": digest(body)}
    verify_public_bundle(manifest, members=members, family_release=release)
    return PublicBundle(manifest=manifest, members=tuple(members))


_BUNDLE_FIELDS = frozenset(
    {
        "schema_version",
        "family_id",
        "matrix_id",
        "registration_digest",
        "family_release_digest",
        "payload_contract_version",
        "episode_chunk_row_limit",
        "ordered_slot_payloads",
        "bundle_member_count",
        "bundle_content_byte_count",
        "bundle_payload_sha256",
        "bundle_manifest_digest",
    }
)
_SLOT_PAYLOAD_FIELDS = frozenset(
    {
        "slot_sequence",
        "hypothesis_id",
        "result_manifest_path",
        "result_manifest_digest",
        "result_manifest_byte_count",
        "result_manifest_file_sha256",
        "postflight_path",
        "postflight_digest",
        "postflight_byte_count",
        "postflight_file_sha256",
        "episode_count",
        "episode_rows_sha256",
        "episode_chunks",
    }
)
_CHUNK_FIELDS = frozenset(
    {
        "chunk_sequence",
        "path",
        "row_start_sequence",
        "row_end_sequence",
        "row_count",
        "byte_count",
        "sha256",
    }
)


def verify_public_bundle(
    value: Mapping[str, Any],
    *,
    members: Sequence[tuple[str, bytes]],
    family_release: Mapping[str, Any],
) -> dict[str, Any]:
    manifest = dict(value)
    release = verify_family_release(family_release)
    if "family_release_digest" not in release:
        raise AtomicBenchmarkIntegrityError("sealed family release digest required")
    require_exact_fields(manifest, _BUNDLE_FIELDS, "public bundle manifest")
    if (
        manifest["schema_version"] != PUBLIC_BUNDLE_SCHEMA
        or manifest["payload_contract_version"] != PUBLIC_BUNDLE_PAYLOAD_CONTRACT
        or manifest["episode_chunk_row_limit"] != EPISODE_CHUNK_ROW_LIMIT
    ):
        raise AtomicBenchmarkIntegrityError("public bundle contract drift")
    for field in ("family_id", "matrix_id"):
        _nonempty_string(manifest[field], field)
    for field in (
        "registration_digest",
        "family_release_digest",
        "bundle_payload_sha256",
        "bundle_manifest_digest",
    ):
        require_sha256(manifest[field], field)
    if (
        manifest["family_id"] != release["family_id"]
        or manifest["matrix_id"] != release["matrix_id"]
        or manifest["registration_digest"] != release["registration_digest"]
        or manifest["family_release_digest"] != release["family_release_digest"]
    ):
        raise AtomicBenchmarkIntegrityError("bundle family release identity mismatch")
    slots = manifest["ordered_slot_payloads"]
    if not isinstance(slots, list) or len(slots) != 7:
        raise AtomicBenchmarkIntegrityError("bundle requires seven slot descriptors")
    _integer(manifest["bundle_member_count"], "bundle_member_count")
    _integer(manifest["bundle_content_byte_count"], "bundle_content_byte_count")
    paths = [path for path, _ in members]
    if len(paths) != len(set(paths)):
        raise AtomicBenchmarkIntegrityError("bundle member paths must be unique")
    member_by_path = dict(members)
    expected_members: list[tuple[str, int, str]] = []
    for expected_slot, slot in enumerate(slots, start=1):
        require_exact_fields(dict(slot), _SLOT_PAYLOAD_FIELDS, "slot payload")
        if slot["slot_sequence"] != expected_slot:
            raise AtomicBenchmarkIntegrityError("slot payload order drift")
        _integer(slot["result_manifest_byte_count"], "result manifest byte count")
        _integer(slot["postflight_byte_count"], "postflight byte count")
        _integer(slot["episode_count"], "episode_count")
        for field in (
            "hypothesis_id",
            "result_manifest_digest",
            "result_manifest_file_sha256",
            "postflight_digest",
            "postflight_file_sha256",
            "episode_rows_sha256",
        ):
            require_sha256(slot[field], field)
        result_path = f"slots/{expected_slot:02d}/result_manifest.json"
        postflight_path = f"slots/{expected_slot:02d}/postflight.json"
        if slot["result_manifest_path"] != result_path or slot["postflight_path"] != postflight_path:
            raise AtomicBenchmarkIntegrityError("slot payload path drift")
        expected_members.extend(
            (
                (result_path, slot["result_manifest_byte_count"], slot["result_manifest_file_sha256"]),
                (postflight_path, slot["postflight_byte_count"], slot["postflight_file_sha256"]),
            )
        )
        chunks = slot["episode_chunks"]
        expected_chunk_count = (slot["episode_count"] + 9999) // 10000
        if not isinstance(chunks, list) or len(chunks) != expected_chunk_count:
            raise AtomicBenchmarkIntegrityError("episode chunk count drift")
        for expected_chunk, chunk in enumerate(chunks, start=1):
            require_exact_fields(dict(chunk), _CHUNK_FIELDS, "episode chunk")
            for field in (
                "chunk_sequence",
                "row_start_sequence",
                "row_end_sequence",
                "row_count",
                "byte_count",
            ):
                _integer(chunk[field], field, minimum=1)
            require_sha256(chunk["sha256"], "chunk sha256")
            start = (expected_chunk - 1) * 10000 + 1
            end = min(expected_chunk * 10000, slot["episode_count"])
            path = f"slots/{expected_slot:02d}/episodes/{expected_chunk:08d}.jsonl"
            if (
                chunk["chunk_sequence"] != expected_chunk
                or chunk["path"] != path
                or chunk["row_start_sequence"] != start
                or chunk["row_end_sequence"] != end
                or chunk["row_count"] != end - start + 1
            ):
                raise AtomicBenchmarkIntegrityError("episode chunk boundary drift")
            expected_members.append((path, chunk["byte_count"], chunk["sha256"]))
        concatenated = b"".join(
            member_by_path[chunk["path"]] for chunk in chunks if chunk["path"] in member_by_path
        )
        if len(concatenated) != sum(chunk["byte_count"] for chunk in chunks):
            raise AtomicBenchmarkIntegrityError("episode chunk member missing")
        if hashlib.sha256(concatenated).hexdigest() != slot["episode_rows_sha256"]:
            raise AtomicBenchmarkIntegrityError("episode concatenated SHA mismatch")
    if len(members) != len(expected_members):
        raise AtomicBenchmarkIntegrityError("bundle member count mismatch")
    for (path, content), (expected_path, byte_count, sha256) in zip(
        members, expected_members, strict=True
    ):
        if (
            path != expected_path
            or len(content) != byte_count
            or hashlib.sha256(content).hexdigest() != sha256
        ):
            raise AtomicBenchmarkIntegrityError("bundle member evidence mismatch")
    if manifest["bundle_member_count"] != len(members) or manifest[
        "bundle_content_byte_count"
    ] != sum(len(content) for _, content in members):
        raise AtomicBenchmarkIntegrityError("bundle aggregate counts mismatch")
    payload = b"".join(frame_member(path, content) for path, content in members)
    if hashlib.sha256(payload).hexdigest() != manifest["bundle_payload_sha256"]:
        raise AtomicBenchmarkIntegrityError("bundle payload SHA mismatch")
    for slot, (descriptor, attempt) in enumerate(
        zip(slots, release["ordered_accepted_attempts"], strict=True), start=1
    ):
        result = verify_result_manifest(
            _parse_canonical_object_member(
                member_by_path[descriptor["result_manifest_path"]],
                "result manifest member",
            )
        )
        postflight = verify_postflight(
            _parse_canonical_object_member(
                member_by_path[descriptor["postflight_path"]],
                "postflight member",
            )
        )
        (
            episode_rows,
            episode_payload,
            physical_chunks,
        ) = _parse_canonical_episode_chunks(
            tuple(
                member_by_path[chunk["path"]]
                for chunk in descriptor["episode_chunks"]
            )
        )
        for chunk_index, (chunk_descriptor, chunk_rows) in enumerate(
            zip(descriptor["episode_chunks"], physical_chunks, strict=True), start=1
        ):
            if (
                len(chunk_rows) != chunk_descriptor["row_count"]
                or not chunk_rows
                or chunk_rows[0]["sequence"]
                != chunk_descriptor["row_start_sequence"]
                or chunk_rows[-1]["sequence"]
                != chunk_descriptor["row_end_sequence"]
                or (
                    chunk_index < len(physical_chunks)
                    and len(chunk_rows) != EPISODE_CHUNK_ROW_LIMIT
                )
            ):
                raise AtomicBenchmarkIntegrityError(
                    "episode physical chunk boundary mismatch"
                )
        for row in episode_rows:
            _verify_row_lineage(row, result)
        rebuilt_summary = build_summary(
            episode_rows,
            family_id=result["family_id"],
            hypothesis_id=result["hypothesis_id"],
            dataset_limitations=tuple(result["summary"]["limitations"][1:]),
        )
        if (
            result["slot_sequence"] != slot
            or postflight["slot_sequence"] != slot
            or result["family_id"] != release["family_id"]
            or postflight["family_id"] != release["family_id"]
            or result["matrix_id"] != release["matrix_id"]
            or postflight["matrix_id"] != release["matrix_id"]
            or result["registration_digest"] != release["registration_digest"]
            or postflight["registration_digest"] != release["registration_digest"]
            or result["research_baseline_digest"]
            != release["research_baseline_digest"]
            or postflight["research_baseline_digest"]
            != release["research_baseline_digest"]
            or result["protocol_core_digest"] != release["protocol_core_digest"]
            or descriptor["hypothesis_id"] != attempt["hypothesis_id"]
            or result["hypothesis_id"] != attempt["hypothesis_id"]
            or postflight["hypothesis_id"] != attempt["hypothesis_id"]
            or descriptor["result_manifest_digest"]
            != result["result_manifest_digest"]
            or descriptor["postflight_digest"] != postflight["postflight_digest"]
            or descriptor["episode_count"] != result["episode_count"]
            or descriptor["episode_rows_sha256"] != result["episode_rows_sha256"]
            or result["result_manifest_digest"]
            != attempt["result_manifest_digest"]
            or postflight["postflight_digest"] != attempt["postflight_digest"]
            or result["result_projection_digest"]
            != attempt["result_projection_digest"]
            or postflight["expected_result_manifest_digest"]
            != result["result_manifest_digest"]
            or postflight["actual_result_manifest_digest"]
            != result["result_manifest_digest"]
            or postflight["expected_result_projection_digest"]
            != result["result_projection_digest"]
            or postflight["actual_result_projection_digest"]
            != result["result_projection_digest"]
            or postflight["recomputed_summary"] != result["summary"]
            or postflight["verdict"] != "ACCEPTED"
            or len(episode_rows) != result["episode_count"]
            or hashlib.sha256(episode_payload).hexdigest()
            != result["episode_rows_sha256"]
            or layer_multiplicity_digest(episode_rows)
            != result["episode_signal_multiplicity_digest"]
            or rebuilt_summary != result["summary"]
        ):
            raise AtomicBenchmarkIntegrityError("bundle semantic evidence mismatch")
    _verify_self_digest(manifest, "bundle_manifest_digest", "bundle manifest")
    canonical_object_bytes(manifest)
    return manifest
