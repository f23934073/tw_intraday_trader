"""Strict canonical codecs for point-in-time equity-universe artifacts."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from datetime import date, datetime
from typing import Any

from watchlist.reference_data import (
    DateEffectiveEquityRecord,
    EquityMarket,
    EquityUniverseManifest,
    EquityUniverseSnapshot,
    MarketCapCohort,
    SecurityType,
    UniverseArtifactStatus,
    UniverseEvidenceMode,
)


EQUITY_UNIVERSE_SNAPSHOT_SCHEMA_VERSION = "pit_equity_universe_snapshot_v1"
EQUITY_UNIVERSE_MANIFEST_SCHEMA_VERSION = "pit_equity_universe_manifest_v1"

EQUITY_RECORD_V1_FIELDS = frozenset(
    {
        "symbol",
        "name",
        "market",
        "security_type",
        "listed_from",
        "listed_until",
        "industry_code",
        "industry_name",
        "industry_as_of",
        "market_cap_twd",
        "market_cap_cohort",
        "market_cap_as_of",
        "effective_from",
        "effective_to",
        "source_digest",
    }
)

EQUITY_UNIVERSE_MANIFEST_V1_FIELDS = frozenset(
    {
        "snapshot_id",
        "evidence_mode",
        "source_id",
        "source_license",
        "source_revision",
        "parent_snapshot_id",
        "correction_policy_note",
        "immutable_revision_policy",
        "retrieved_at",
        "available_from_session",
        "coverage_start",
        "coverage_end",
        "covered_markets",
        "record_count",
        "source_digest",
        "content_digest",
        "status",
    }
)


class EquityUniverseSerializationError(ValueError):
    """A payload does not satisfy the frozen PIT universe contract."""


def _record_to_dict(record: DateEffectiveEquityRecord) -> dict[str, object]:
    return {
        "symbol": record.symbol,
        "name": record.name,
        "market": record.market.value,
        "security_type": record.security_type.value,
        "listed_from": record.listed_from.isoformat(),
        "listed_until": (
            record.listed_until.isoformat() if record.listed_until is not None else None
        ),
        "industry_code": record.industry_code,
        "industry_name": record.industry_name,
        "industry_as_of": record.industry_as_of.isoformat(),
        "market_cap_twd": record.market_cap_twd,
        "market_cap_cohort": record.market_cap_cohort.value,
        "market_cap_as_of": record.market_cap_as_of.isoformat(),
        "effective_from": record.effective_from.isoformat(),
        "effective_to": (
            record.effective_to.isoformat() if record.effective_to is not None else None
        ),
        "source_digest": record.source_digest,
    }


def serialize_snapshot(snapshot: EquityUniverseSnapshot) -> str:
    records = sorted(
        snapshot.records,
        key=lambda record: (
            record.market.value,
            record.symbol,
            record.effective_from,
            record.effective_to or date.max,
        ),
    )
    return _canonical_json(
        {
            "schema_version": EQUITY_UNIVERSE_SNAPSHOT_SCHEMA_VERSION,
            "snapshot_id": snapshot.snapshot_id,
            "records": [_record_to_dict(record) for record in records],
        }
    )


def snapshot_sha256(snapshot: EquityUniverseSnapshot) -> str:
    return hashlib.sha256(serialize_snapshot(snapshot).encode("utf-8")).hexdigest()


def deserialize_snapshot(payload_json: str) -> EquityUniverseSnapshot:
    payload = _json_object(payload_json)
    _require_exact_fields(
        payload,
        {"schema_version", "snapshot_id", "records"},
        "equity universe snapshot",
    )
    if payload["schema_version"] != EQUITY_UNIVERSE_SNAPSHOT_SCHEMA_VERSION:
        raise EquityUniverseSerializationError("unsupported snapshot schema_version")
    records = payload["records"]
    if not isinstance(records, list):
        raise EquityUniverseSerializationError("snapshot records must be a list")
    try:
        return EquityUniverseSnapshot(
            snapshot_id=_string(payload, "snapshot_id"),
            records=tuple(_record(value) for value in records),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, EquityUniverseSerializationError):
            raise
        raise EquityUniverseSerializationError(
            f"invalid equity universe snapshot: {error}"
        ) from error


def _record(value: object) -> DateEffectiveEquityRecord:
    if not isinstance(value, Mapping):
        raise EquityUniverseSerializationError("equity record must be an object")
    _require_exact_fields(value, EQUITY_RECORD_V1_FIELDS, "equity record")
    try:
        return DateEffectiveEquityRecord(
            symbol=_string(value, "symbol"),
            name=_string(value, "name"),
            market=EquityMarket(_string(value, "market")),
            security_type=SecurityType(_string(value, "security_type")),
            listed_from=_date(value, "listed_from"),
            listed_until=_optional_date(value, "listed_until"),
            industry_code=_string(value, "industry_code"),
            industry_name=_string(value, "industry_name"),
            industry_as_of=_date(value, "industry_as_of"),
            market_cap_twd=_int(value, "market_cap_twd"),
            market_cap_cohort=MarketCapCohort(_string(value, "market_cap_cohort")),
            market_cap_as_of=_date(value, "market_cap_as_of"),
            effective_from=_date(value, "effective_from"),
            effective_to=_optional_date(value, "effective_to"),
            source_digest=_string(value, "source_digest"),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, EquityUniverseSerializationError):
            raise
        raise EquityUniverseSerializationError(
            f"invalid equity record: {error}"
        ) from error


def serialize_manifest(manifest: EquityUniverseManifest) -> str:
    return _canonical_json(
        {
            "schema_version": EQUITY_UNIVERSE_MANIFEST_SCHEMA_VERSION,
            "snapshot_id": manifest.snapshot_id,
            "evidence_mode": manifest.evidence_mode.value,
            "source_id": manifest.source_id,
            "source_license": manifest.source_license,
            "source_revision": manifest.source_revision,
            "parent_snapshot_id": manifest.parent_snapshot_id,
            "correction_policy_note": manifest.correction_policy_note,
            "immutable_revision_policy": manifest.immutable_revision_policy,
            "retrieved_at": manifest.retrieved_at.isoformat(),
            "available_from_session": manifest.available_from_session.isoformat(),
            "coverage_start": (
                manifest.coverage_start.isoformat()
                if manifest.coverage_start is not None
                else None
            ),
            "coverage_end": (
                manifest.coverage_end.isoformat()
                if manifest.coverage_end is not None
                else None
            ),
            "covered_markets": sorted(
                market.value for market in manifest.covered_markets
            ),
            "record_count": manifest.record_count,
            "source_digest": manifest.source_digest,
            "content_digest": manifest.content_digest,
            "status": manifest.status.value,
        }
    )


def manifest_sha256(manifest: EquityUniverseManifest) -> str:
    return hashlib.sha256(serialize_manifest(manifest).encode("utf-8")).hexdigest()


def deserialize_manifest(payload_json: str) -> EquityUniverseManifest:
    payload = _json_object(payload_json)
    _require_exact_fields(
        payload,
        EQUITY_UNIVERSE_MANIFEST_V1_FIELDS | {"schema_version"},
        "equity universe manifest",
    )
    if payload["schema_version"] != EQUITY_UNIVERSE_MANIFEST_SCHEMA_VERSION:
        raise EquityUniverseSerializationError("unsupported manifest schema_version")
    covered_markets = payload["covered_markets"]
    if not isinstance(covered_markets, list):
        raise EquityUniverseSerializationError("covered_markets must be a list")
    try:
        return EquityUniverseManifest(
            snapshot_id=_string(payload, "snapshot_id"),
            evidence_mode=UniverseEvidenceMode(_string(payload, "evidence_mode")),
            source_id=_string(payload, "source_id"),
            source_license=_string(payload, "source_license"),
            source_revision=_int(payload, "source_revision"),
            parent_snapshot_id=_optional_string(payload, "parent_snapshot_id"),
            correction_policy_note=_string(payload, "correction_policy_note"),
            immutable_revision_policy=_string(
                payload,
                "immutable_revision_policy",
            ),
            retrieved_at=_datetime(payload, "retrieved_at"),
            available_from_session=_date(payload, "available_from_session"),
            coverage_start=_optional_date(payload, "coverage_start"),
            coverage_end=_optional_date(payload, "coverage_end"),
            covered_markets=frozenset(EquityMarket(value) for value in covered_markets),
            record_count=_int(payload, "record_count"),
            source_digest=_optional_string(payload, "source_digest"),
            content_digest=_optional_string(payload, "content_digest"),
            status=UniverseArtifactStatus(_string(payload, "status")),
        )
    except (TypeError, ValueError) as error:
        if isinstance(error, EquityUniverseSerializationError):
            raise
        raise EquityUniverseSerializationError(
            f"invalid equity universe manifest: {error}"
        ) from error


def _canonical_json(value: Mapping[str, object]) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _json_object(payload_json: str) -> Mapping[str, Any]:
    try:
        payload = json.loads(payload_json)
    except json.JSONDecodeError as error:
        raise EquityUniverseSerializationError("artifact is not valid JSON") from error
    if not isinstance(payload, Mapping):
        raise EquityUniverseSerializationError("artifact must contain one object")
    return payload


def _require_exact_fields(
    payload: Mapping[str, Any],
    expected: frozenset[str] | set[str],
    label: str,
) -> None:
    actual = set(payload)
    missing = sorted(set(expected) - actual)
    unexpected = sorted(actual - set(expected))
    if missing:
        raise EquityUniverseSerializationError(
            f"{label} missing fields: {', '.join(missing)}"
        )
    if unexpected:
        raise EquityUniverseSerializationError(
            f"{label} has unexpected fields: {', '.join(unexpected)}"
        )


def _string(payload: Mapping[str, Any], field_name: str) -> str:
    value = payload[field_name]
    if not isinstance(value, str):
        raise EquityUniverseSerializationError(f"{field_name} must be a string")
    return value


def _optional_string(payload: Mapping[str, Any], field_name: str) -> str | None:
    return None if payload[field_name] is None else _string(payload, field_name)


def _int(payload: Mapping[str, Any], field_name: str) -> int:
    value = payload[field_name]
    if isinstance(value, bool) or not isinstance(value, int):
        raise EquityUniverseSerializationError(f"{field_name} must be an integer")
    return value


def _date(payload: Mapping[str, Any], field_name: str) -> date:
    value = _string(payload, field_name)
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise EquityUniverseSerializationError(
            f"{field_name} must be ISO-8601"
        ) from error


def _optional_date(payload: Mapping[str, Any], field_name: str) -> date | None:
    return None if payload[field_name] is None else _date(payload, field_name)


def _datetime(payload: Mapping[str, Any], field_name: str) -> datetime:
    value = _string(payload, field_name)
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise EquityUniverseSerializationError(
            f"{field_name} must be ISO-8601"
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise EquityUniverseSerializationError(f"{field_name} must include a timezone")
    return parsed
