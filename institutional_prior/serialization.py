"""Canonical serialization for institutional Candidate Prior artifacts."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text
from institutional_research.domain import (
    ArtifactIdentity,
    DefinitionIdentity,
    ResearchLabel,
)
from watchlist.reference_data import EquityMarket

from .domain import (
    CandidatePriorArtifact,
    CandidatePriorArtifactManifestV0,
    CandidatePriorDefinition,
    CandidatePriorEntry,
    CandidatePriorEntryPayload,
    CandidatePriorHypothesis,
    CandidatePriorProjection,
    CandidatePriorRunManifestV0,
    EvaluationCohort,
    InstitutionalFactorPrior,
    InstitutionalFactorPriorArtifact,
    PriceMomentumPrior,
    PriceMomentumPriorArtifact,
)

CANDIDATE_PRIOR_DEFINITION_SCHEMA_VERSION = "candidate_prior_definition_v0"
CANDIDATE_PRIOR_RUN_SCHEMA_VERSION = "candidate_prior_run_manifest_v0"
CANDIDATE_PRIOR_RUN_IDENTITY_SCHEMA_VERSION = "candidate_prior_run_identity_v0"
PRICE_MOMENTUM_PRIOR_SCHEMA_VERSION = "price_momentum_prior_input_v0"
INSTITUTIONAL_FACTOR_PRIOR_SCHEMA_VERSION = "institutional_factor_prior_input_v0"
CANDIDATE_PRIOR_ENTRY_SCHEMA_VERSION = "institutional_candidate_prior_entry_v0"
CANDIDATE_PRIOR_ENTRIES_SCHEMA_VERSION = "institutional_candidate_prior_entries_v0"
CANDIDATE_PRIOR_ARTIFACT_SCHEMA_VERSION = "institutional_candidate_prior_v0"

FORBIDDEN_CANDIDATE_PRIOR_FIELDS = frozenset(
    {
        "forward_return",
        "ic",
        "icir",
        "decile_return",
        "win_rate",
        "expectancy",
    }
)


class CandidatePriorSerializationError(ValueError):
    """Candidate Prior bytes do not satisfy the frozen v0 contract."""


def _to_payload(value: object) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {
            field.name: _to_payload(getattr(value, field.name))
            for field in fields(value)
        }
    if isinstance(value, tuple):
        return [_to_payload(item) for item in value]
    if isinstance(value, list):
        return [_to_payload(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _to_payload(item) for key, item in value.items()}
    return value


def serialize_candidate_prior_definition(
    definition: CandidatePriorDefinition,
) -> str:
    return canonical_json(
        {
            "schema_version": CANDIDATE_PRIOR_DEFINITION_SCHEMA_VERSION,
            "definition": _to_payload(definition),
        }
    )


def candidate_prior_definition_sha256(
    definition: CandidatePriorDefinition,
) -> str:
    return sha256_text(serialize_candidate_prior_definition(definition))


def candidate_prior_definition_identity(
    definition: CandidatePriorDefinition,
) -> DefinitionIdentity:
    return DefinitionIdentity(
        definition_id=definition.definition_id,
        version=definition.version,
        definition_digest=candidate_prior_definition_sha256(definition),
    )


def serialize_candidate_prior_run_manifest(
    manifest: CandidatePriorRunManifestV0,
) -> str:
    return canonical_json(
        {
            "schema_version": CANDIDATE_PRIOR_RUN_SCHEMA_VERSION,
            "run": _to_payload(manifest),
        }
    )


def candidate_prior_run_identity_sha256(
    manifest: CandidatePriorRunManifestV0,
) -> str:
    causal_inputs = _to_payload(manifest)
    if not isinstance(causal_inputs, dict):  # pragma: no cover - dataclass guard
        raise TypeError("run manifest must serialize as an object")
    causal_inputs.pop("generated_at")
    return sha256_text(
        canonical_json(
            {
                "schema_version": CANDIDATE_PRIOR_RUN_IDENTITY_SCHEMA_VERSION,
                "identity": causal_inputs,
            }
        )
    )


def serialize_price_momentum_prior(prior: PriceMomentumPrior) -> str:
    return canonical_json(
        {
            "schema_version": PRICE_MOMENTUM_PRIOR_SCHEMA_VERSION,
            "prior": _to_payload(prior),
        }
    )


def build_price_momentum_prior_artifact(
    *,
    artifact_id: str,
    prior: PriceMomentumPrior,
) -> PriceMomentumPriorArtifact:
    prior_json = serialize_price_momentum_prior(prior)
    return PriceMomentumPriorArtifact(
        artifact_id=artifact_id,
        prior=prior,
        prior_json=prior_json,
        prior_digest=sha256_text(prior_json),
    )


def serialize_institutional_factor_prior(prior: InstitutionalFactorPrior) -> str:
    return canonical_json(
        {
            "schema_version": INSTITUTIONAL_FACTOR_PRIOR_SCHEMA_VERSION,
            "prior": _to_payload(prior),
        }
    )


def build_institutional_factor_prior_artifact(
    prior: InstitutionalFactorPrior,
) -> InstitutionalFactorPriorArtifact:
    prior_json = serialize_institutional_factor_prior(prior)
    return InstitutionalFactorPriorArtifact(
        prior=prior,
        prior_json=prior_json,
        prior_digest=sha256_text(prior_json),
    )


def serialize_candidate_prior_entry_payload(
    payload: CandidatePriorEntryPayload,
) -> str:
    return canonical_json(
        {
            "schema_version": CANDIDATE_PRIOR_ENTRY_SCHEMA_VERSION,
            "entry": _to_payload(payload),
        }
    )


def build_candidate_prior_entry(
    payload: CandidatePriorEntryPayload,
) -> CandidatePriorEntry:
    return CandidatePriorEntry(
        payload=payload,
        entry_digest=sha256_text(serialize_candidate_prior_entry_payload(payload)),
    )


def _entry_to_payload(entry: CandidatePriorEntry) -> dict[str, Any]:
    return {
        **_to_payload(entry.payload),
        "entry_digest": entry.entry_digest,
    }


def serialize_candidate_prior_entries(
    entries: tuple[CandidatePriorEntry, ...],
) -> str:
    return canonical_json(
        {
            "schema_version": CANDIDATE_PRIOR_ENTRIES_SCHEMA_VERSION,
            "entries": [_entry_to_payload(entry) for entry in entries],
        }
    )


def candidate_prior_entries_sha256(
    entries: tuple[CandidatePriorEntry, ...],
) -> str:
    return sha256_text(serialize_candidate_prior_entries(entries))


def serialize_candidate_prior_artifact(
    manifest: CandidatePriorArtifactManifestV0,
    entries: tuple[CandidatePriorEntry, ...],
) -> str:
    return canonical_json(
        {
            "schema_version": CANDIDATE_PRIOR_ARTIFACT_SCHEMA_VERSION,
            "manifest": _to_payload(manifest),
            "entries": [_entry_to_payload(entry) for entry in entries],
        }
    )


def build_candidate_prior_artifact(
    *,
    manifest: CandidatePriorArtifactManifestV0,
    entries: tuple[CandidatePriorEntry, ...],
) -> CandidatePriorArtifact:
    if manifest.entry_count != len(entries):
        raise ValueError("manifest entry_count does not match entries")
    if manifest.entries_digest != candidate_prior_entries_sha256(entries):
        raise ValueError("manifest entries_digest does not match entries")
    for entry in entries:
        expected = sha256_text(serialize_candidate_prior_entry_payload(entry.payload))
        if entry.entry_digest != expected:
            raise ValueError("entry_digest does not match entry payload")
    matched_entries = tuple(
        entry for entry in entries if entry.payload.matched_hypotheses
    )
    if manifest.projected_candidate_count != len(matched_entries):
        raise ValueError("manifest projected_candidate_count does not match entries")

    artifact_json = serialize_candidate_prior_artifact(manifest, entries)
    artifact_digest = sha256_text(artifact_json)
    artifact_id = f"institutional-candidate-prior-{artifact_digest[:16]}"
    projections = tuple(
        CandidatePriorProjection(
            artifact_id=artifact_id,
            artifact_digest=artifact_digest,
            entry_digest=entry.entry_digest,
            target_session=entry.payload.target_session,
            as_of_session=entry.payload.as_of_session,
            market=entry.payload.market,
            symbol=entry.payload.symbol,
            candidate_rank=entry.payload.candidate_rank,
            matched_hypotheses=entry.payload.matched_hypotheses,
            research_status=ResearchLabel.EXPLORATORY,
            strategy_ready=False,
            production_ready=False,
            live_admission_ready=False,
            execution_allowed=False,
        )
        for entry in matched_entries
        if entry.payload.candidate_rank is not None
    )
    return CandidatePriorArtifact(
        manifest=manifest,
        entries=entries,
        projections=projections,
        artifact_json=artifact_json,
        artifact_digest=artifact_digest,
    )


def deserialize_candidate_prior_artifact(
    artifact_json: str,
    *,
    expected_digest: str | None = None,
) -> CandidatePriorArtifact:
    """Parse canonical v0 bytes and rebuild the immutable domain artifact."""

    payload = _json_object(artifact_json)
    _reject_forbidden_fields(payload)
    _require_exact_fields(
        payload,
        {"schema_version", "manifest", "entries"},
        "Candidate Prior artifact",
    )
    if payload["schema_version"] != CANDIDATE_PRIOR_ARTIFACT_SCHEMA_VERSION:
        raise CandidatePriorSerializationError("unsupported artifact schema_version")
    if canonical_json(payload) != artifact_json:
        raise CandidatePriorSerializationError("artifact JSON must be canonical")
    manifest = _manifest_from_object(payload["manifest"])
    raw_entries = payload["entries"]
    if not isinstance(raw_entries, list):
        raise CandidatePriorSerializationError("artifact entries must be a list")
    entries = tuple(_entry_from_object(value) for value in raw_entries)
    try:
        artifact = build_candidate_prior_artifact(
            manifest=manifest,
            entries=entries,
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, CandidatePriorSerializationError):
            raise
        raise CandidatePriorSerializationError(
            f"invalid Candidate Prior artifact: {error}"
        ) from error
    if artifact.artifact_json != artifact_json:
        raise CandidatePriorSerializationError(
            "artifact bytes do not round-trip canonically"
        )
    if expected_digest is not None and artifact.artifact_digest != expected_digest:
        raise CandidatePriorSerializationError("artifact digest does not match")
    return artifact


_ARTIFACT_IDENTITY_FIELDS = frozenset({"artifact_id", "digest"})
_DEFINITION_IDENTITY_FIELDS = frozenset(
    {"definition_id", "version", "definition_digest"}
)
_RUN_FIELDS = frozenset(
    {
        "factor_prior",
        "price_momentum_prior",
        "universe",
        "calendar",
        "hypothesis_definitions",
        "target_session",
        "as_of_session",
        "generated_at",
    }
)
_MANIFEST_FIELDS = frozenset(
    {
        "run",
        "research_status",
        "strategy_ready",
        "production_ready",
        "live_admission_ready",
        "execution_allowed",
        "issue_codes",
        "entry_count",
        "projected_candidate_count",
        "entries_digest",
    }
)
_ENTRY_FIELDS = frozenset(
    {
        "target_session",
        "as_of_session",
        "market",
        "symbol",
        "cohorts",
        "matched_hypotheses",
        "candidate_rank",
        "price_rank",
        "foreign_5d_value",
        "foreign_5d_percentile",
        "trust_5d_value",
        "trust_5d_percentile",
        "selection_reason_codes",
        "entry_digest",
    }
)


def _manifest_from_object(value: object) -> CandidatePriorArtifactManifestV0:
    payload = _mapping(value, "artifact manifest")
    _require_exact_fields(payload, _MANIFEST_FIELDS, "artifact manifest")
    try:
        return CandidatePriorArtifactManifestV0(
            run=_run_from_object(payload["run"]),
            research_status=ResearchLabel(_string(payload, "research_status")),
            strategy_ready=_bool(payload, "strategy_ready"),
            production_ready=_bool(payload, "production_ready"),
            live_admission_ready=_bool(payload, "live_admission_ready"),
            execution_allowed=_bool(payload, "execution_allowed"),
            issue_codes=_string_tuple(payload, "issue_codes"),
            entry_count=_int(payload, "entry_count"),
            projected_candidate_count=_int(payload, "projected_candidate_count"),
            entries_digest=_string(payload, "entries_digest"),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, CandidatePriorSerializationError):
            raise
        raise CandidatePriorSerializationError(
            f"invalid artifact manifest: {error}"
        ) from error


def _run_from_object(value: object) -> CandidatePriorRunManifestV0:
    payload = _mapping(value, "run manifest")
    _require_exact_fields(payload, _RUN_FIELDS, "run manifest")
    definitions = payload["hypothesis_definitions"]
    if not isinstance(definitions, list):
        raise CandidatePriorSerializationError("hypothesis_definitions must be a list")
    try:
        return CandidatePriorRunManifestV0(
            factor_prior=_artifact_identity(payload["factor_prior"], "factor_prior"),
            price_momentum_prior=_artifact_identity(
                payload["price_momentum_prior"],
                "price_momentum_prior",
            ),
            universe=_artifact_identity(payload["universe"], "universe"),
            calendar=_artifact_identity(payload["calendar"], "calendar"),
            hypothesis_definitions=tuple(
                _definition_identity(item, "hypothesis definition")
                for item in definitions
            ),
            target_session=_date(payload, "target_session"),
            as_of_session=_date(payload, "as_of_session"),
            generated_at=_datetime(payload, "generated_at"),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, CandidatePriorSerializationError):
            raise
        raise CandidatePriorSerializationError(
            f"invalid run manifest: {error}"
        ) from error


def _entry_from_object(value: object) -> CandidatePriorEntry:
    payload = _mapping(value, "Candidate Prior entry")
    _require_exact_fields(payload, _ENTRY_FIELDS, "Candidate Prior entry")
    cohorts = payload["cohorts"]
    hypotheses = payload["matched_hypotheses"]
    if not isinstance(cohorts, list):
        raise CandidatePriorSerializationError("cohorts must be a list")
    if not isinstance(hypotheses, list):
        raise CandidatePriorSerializationError("matched_hypotheses must be a list")
    try:
        entry_payload = CandidatePriorEntryPayload(
            target_session=_date(payload, "target_session"),
            as_of_session=_date(payload, "as_of_session"),
            market=EquityMarket(_string(payload, "market")),
            symbol=_string(payload, "symbol"),
            cohorts=tuple(
                EvaluationCohort(_plain_string(item, "cohort")) for item in cohorts
            ),
            matched_hypotheses=tuple(
                CandidatePriorHypothesis(_plain_string(item, "hypothesis"))
                for item in hypotheses
            ),
            candidate_rank=_optional_int(payload, "candidate_rank"),
            price_rank=_optional_int(payload, "price_rank"),
            foreign_5d_value=_optional_decimal(payload, "foreign_5d_value"),
            foreign_5d_percentile=_optional_decimal(
                payload,
                "foreign_5d_percentile",
            ),
            trust_5d_value=_optional_decimal(payload, "trust_5d_value"),
            trust_5d_percentile=_optional_decimal(
                payload,
                "trust_5d_percentile",
            ),
            selection_reason_codes=_string_tuple(
                payload,
                "selection_reason_codes",
            ),
        )
        return CandidatePriorEntry(
            payload=entry_payload,
            entry_digest=_string(payload, "entry_digest"),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, CandidatePriorSerializationError):
            raise
        raise CandidatePriorSerializationError(
            f"invalid Candidate Prior entry: {error}"
        ) from error


def _artifact_identity(value: object, label: str) -> ArtifactIdentity:
    payload = _mapping(value, label)
    _require_exact_fields(payload, _ARTIFACT_IDENTITY_FIELDS, label)
    digest = payload["digest"]
    if not isinstance(digest, str):
        raise CandidatePriorSerializationError(f"{label}.digest must be a string")
    return ArtifactIdentity(
        artifact_id=_string(payload, "artifact_id"),
        digest=digest,
    )


def _definition_identity(value: object, label: str) -> DefinitionIdentity:
    payload = _mapping(value, label)
    _require_exact_fields(payload, _DEFINITION_IDENTITY_FIELDS, label)
    return DefinitionIdentity(
        definition_id=_string(payload, "definition_id"),
        version=_string(payload, "version"),
        definition_digest=_string(payload, "definition_digest"),
    )


def _json_object(payload_json: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise CandidatePriorSerializationError("artifact is not valid JSON") from error
    return _mapping(payload, "Candidate Prior artifact")


def _mapping(value: object, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise CandidatePriorSerializationError(f"{label} must be an object")
    return value


def _require_exact_fields(
    payload: Mapping[str, Any],
    expected: frozenset[str] | set[str],
    label: str,
) -> None:
    actual = set(payload)
    missing = sorted(set(expected) - actual)
    unexpected = sorted(actual - set(expected))
    if missing:
        raise CandidatePriorSerializationError(
            f"{label} missing fields: {', '.join(missing)}"
        )
    if unexpected:
        raise CandidatePriorSerializationError(
            f"{label} has unexpected fields: {', '.join(unexpected)}"
        )


def _reject_forbidden_fields(value: object) -> None:
    if isinstance(value, Mapping):
        for key, item in value.items():
            normalized = str(key).casefold()
            if normalized in FORBIDDEN_CANDIDATE_PRIOR_FIELDS:
                raise CandidatePriorSerializationError(
                    f"forbidden Candidate Prior field: {key}"
                )
            _reject_forbidden_fields(item)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_fields(item)


def _string(payload: Mapping[str, Any], field_name: str) -> str:
    return _plain_string(payload[field_name], field_name)


def _plain_string(value: object, label: str) -> str:
    if not isinstance(value, str):
        raise CandidatePriorSerializationError(f"{label} must be a string")
    return value


def _bool(payload: Mapping[str, Any], field_name: str) -> bool:
    value = payload[field_name]
    if not isinstance(value, bool):
        raise CandidatePriorSerializationError(f"{field_name} must be a boolean")
    return value


def _int(payload: Mapping[str, Any], field_name: str) -> int:
    value = payload[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise CandidatePriorSerializationError(f"{field_name} must be an integer")
    return value


def _optional_int(payload: Mapping[str, Any], field_name: str) -> int | None:
    return None if payload[field_name] is None else _int(payload, field_name)


def _optional_decimal(
    payload: Mapping[str, Any],
    field_name: str,
) -> Decimal | None:
    value = payload[field_name]
    if value is None:
        return None
    if not isinstance(value, str):
        raise CandidatePriorSerializationError(f"{field_name} must be a string")
    try:
        result = Decimal(value)
    except ArithmeticError as error:
        raise CandidatePriorSerializationError(
            f"{field_name} must be a decimal string"
        ) from error
    if not result.is_finite():
        raise CandidatePriorSerializationError(f"{field_name} must be finite")
    return result


def _string_tuple(payload: Mapping[str, Any], field_name: str) -> tuple[str, ...]:
    value = payload[field_name]
    if not isinstance(value, list):
        raise CandidatePriorSerializationError(f"{field_name} must be a list")
    return tuple(_plain_string(item, field_name) for item in value)


def _date(payload: Mapping[str, Any], field_name: str) -> date:
    value = _string(payload, field_name)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise CandidatePriorSerializationError(
            f"{field_name} must be ISO-8601"
        ) from error


def _datetime(payload: Mapping[str, Any], field_name: str) -> datetime:
    value = _string(payload, field_name)
    try:
        result = datetime.fromisoformat(value)
    except ValueError as error:
        raise CandidatePriorSerializationError(
            f"{field_name} must be ISO-8601"
        ) from error
    if result.tzinfo is None or result.utcoffset() is None:
        raise CandidatePriorSerializationError(f"{field_name} must include a timezone")
    return result
