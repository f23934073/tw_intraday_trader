"""Canonical immutable artifacts with in-memory and filesystem repositories."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from pathlib import Path
from threading import RLock
from typing import Any, Protocol

from premarket.models import (
    CompletenessStatus,
    ContextHealth,
    ContractIdentity,
    ContractIdentityStatus,
    RawSourceArtifact,
    ReconciliationStatus,
    TaifexNightContextArtifact,
    TaifexNightReconciliationArtifact,
)


class ArtifactIntegrityError(ValueError):
    """Stored content does not match its content-addressed identity."""


def _canonical(value: Any) -> Any:
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(_canonical(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha256_digest(value: dict[str, Any]) -> str:
    return sha256_text_digest(canonical_json(value))


def sha256_text_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def create_raw_source_artifact(
    *,
    source: str,
    captured_at: datetime,
    payload_json: str,
) -> RawSourceArtifact:
    return RawSourceArtifact(
        schema_version="premarket_raw_source_v0",
        source=source,
        raw_source_digest=sha256_text_digest(payload_json),
        captured_at=captured_at,
        payload_json=payload_json,
    )


def create_context_artifact(
    *,
    schema_version: str,
    readiness_predicate_version: str,
    trading_date: date,
    timezone: str,
    product_root: str,
    contract_alias: str,
    contract_identity: ContractIdentity,
    session_start: datetime,
    session_end: datetime,
    query_not_before: datetime,
    queried_at: datetime,
    received_at: datetime,
    provider_reference_price: Decimal | None,
    provider_reference_updated_at: datetime | None,
    provider_reference_source: str | None,
    open: Decimal,
    high: Decimal,
    low: Decimal,
    close: Decimal,
    volume: int,
    first_event_at: datetime,
    last_event_at: datetime,
    completeness_status: CompletenessStatus,
    completeness_evidence: tuple[str, ...],
    health: ContextHealth,
    reasons: tuple[str, ...],
    source: str,
    raw_source_digest: str,
) -> TaifexNightContextArtifact:
    session_move_pct = (close / open - Decimal("1")) * Decimal("100")
    session_range_pct = (high - low) / open * Decimal("100")
    provider_reference_change_pct = (
        (close / provider_reference_price - Decimal("1")) * Decimal("100")
        if provider_reference_price is not None
        else None
    )
    close_location = (close - low) / (high - low) if high != low else None
    body = {
        "schema_version": schema_version,
        "readiness_predicate_version": readiness_predicate_version,
        "trading_date": trading_date,
        "timezone": timezone,
        "product_root": product_root,
        "contract_alias": contract_alias,
        "contract_identity": {
            "status": contract_identity.status,
            "resolution_method": contract_identity.resolution_method,
            "resolved_contract_code": contract_identity.resolved_contract_code,
            "delivery_month": contract_identity.delivery_month,
            "last_trading_date": contract_identity.last_trading_date,
        },
        "session_start": session_start,
        "session_end": session_end,
        "query_not_before": query_not_before,
        "queried_at": queried_at,
        "received_at": received_at,
        "provider_reference_price": provider_reference_price,
        "provider_reference_updated_at": provider_reference_updated_at,
        "provider_reference_source": provider_reference_source,
        "open": open,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
        "first_event_at": first_event_at,
        "last_event_at": last_event_at,
        "session_move_pct": session_move_pct,
        "session_range_pct": session_range_pct,
        "provider_reference_change_pct": provider_reference_change_pct,
        "close_location": close_location,
        "completeness_status": completeness_status,
        "completeness_evidence": completeness_evidence,
        "health": health,
        "reasons": reasons,
        "source": source,
        "raw_source_digest": raw_source_digest,
    }
    digest = sha256_digest(body)
    return TaifexNightContextArtifact(
        artifact_id=f"taifex-context-{digest[:16]}",
        context_digest=digest,
        **{**body, "contract_identity": contract_identity},
    )


class PremarketArtifactRepository(Protocol):
    def save_raw(self, artifact: RawSourceArtifact) -> None: ...

    def save_context(self, artifact: TaifexNightContextArtifact) -> None: ...

    def save_reconciliation(self, artifact: TaifexNightReconciliationArtifact) -> None: ...

    def raw_source(self, raw_source_digest: str) -> RawSourceArtifact | None: ...

    def contexts(self) -> tuple[TaifexNightContextArtifact, ...]: ...

    def reconciliations(
        self,
        context_digest: str,
    ) -> tuple[TaifexNightReconciliationArtifact, ...]: ...

    def latest_reconciliation(
        self,
        context_digest: str,
    ) -> TaifexNightReconciliationArtifact | None: ...


class InMemoryPremarketArtifactRepository:
    """Append-only process-local artifact index used by the dashboard MVP."""

    def __init__(self) -> None:
        self._raw: dict[str, RawSourceArtifact] = {}
        self._contexts: dict[str, TaifexNightContextArtifact] = {}
        self._reconciliations: dict[str, list[TaifexNightReconciliationArtifact]] = {}
        self._lock = RLock()

    def save_raw(self, artifact: RawSourceArtifact) -> None:
        with self._lock:
            self._raw.setdefault(artifact.raw_source_digest, artifact)

    def save_context(self, artifact: TaifexNightContextArtifact) -> None:
        with self._lock:
            self._contexts.setdefault(artifact.context_digest, artifact)

    def save_reconciliation(self, artifact: TaifexNightReconciliationArtifact) -> None:
        with self._lock:
            values = self._reconciliations.setdefault(artifact.context_digest, [])
            if not any(item.reconciliation_digest == artifact.reconciliation_digest for item in values):
                values.append(artifact)

    def raw_source(self, raw_source_digest: str) -> RawSourceArtifact | None:
        with self._lock:
            return self._raw.get(raw_source_digest)

    def contexts(self) -> tuple[TaifexNightContextArtifact, ...]:
        with self._lock:
            return tuple(self._contexts.values())

    def reconciliations(self, context_digest: str) -> tuple[TaifexNightReconciliationArtifact, ...]:
        with self._lock:
            return tuple(self._reconciliations.get(context_digest, ()))

    def latest_reconciliation(self, context_digest: str) -> TaifexNightReconciliationArtifact | None:
        values = self.reconciliations(context_digest)
        return values[-1] if values else None


def _date_from_json(value: object, field: str) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as error:
        raise ArtifactIntegrityError(f"invalid stored {field}") from error


def _optional_date_from_json(value: object, field: str) -> date | None:
    return None if value is None else _date_from_json(value, field)


def _datetime_from_json(value: object, field: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(str(value))
    except ValueError as error:
        raise ArtifactIntegrityError(f"invalid stored {field}") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ArtifactIntegrityError(f"stored {field} must include a timezone")
    return parsed


def _optional_datetime_from_json(value: object, field: str) -> datetime | None:
    return None if value is None else _datetime_from_json(value, field)


def _decimal_from_json(value: object, field: str) -> Decimal:
    try:
        return Decimal(str(value))
    except Exception as error:
        raise ArtifactIntegrityError(f"invalid stored {field}") from error


def _optional_decimal_from_json(value: object, field: str) -> Decimal | None:
    return None if value is None else _decimal_from_json(value, field)


def _digest_path_component(value: str, field: str) -> str:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ArtifactIntegrityError(f"invalid {field}")
    return value


def _context_from_payload(payload: dict[str, Any]) -> TaifexNightContextArtifact:
    try:
        identity_payload = payload["contract_identity"]
        if not isinstance(identity_payload, dict):
            raise ArtifactIntegrityError("stored contract identity must be an object")
        identity = ContractIdentity(
            status=ContractIdentityStatus(str(identity_payload["status"])),
            resolution_method=str(identity_payload["resolution_method"]),
            resolved_contract_code=(
                str(identity_payload["resolved_contract_code"])
                if identity_payload.get("resolved_contract_code") is not None
                else None
            ),
            delivery_month=(
                str(identity_payload["delivery_month"])
                if identity_payload.get("delivery_month") is not None
                else None
            ),
            last_trading_date=_optional_date_from_json(
                identity_payload.get("last_trading_date"),
                "contract last_trading_date",
            ),
        )
        expected = create_context_artifact(
            schema_version=str(payload["schema_version"]),
            readiness_predicate_version=str(payload["readiness_predicate_version"]),
            trading_date=_date_from_json(payload["trading_date"], "trading_date"),
            timezone=str(payload["timezone"]),
            product_root=str(payload["product_root"]),
            contract_alias=str(payload["contract_alias"]),
            contract_identity=identity,
            session_start=_datetime_from_json(payload["session_start"], "session_start"),
            session_end=_datetime_from_json(payload["session_end"], "session_end"),
            query_not_before=_datetime_from_json(payload["query_not_before"], "query_not_before"),
            queried_at=_datetime_from_json(payload["queried_at"], "queried_at"),
            received_at=_datetime_from_json(payload["received_at"], "received_at"),
            provider_reference_price=_optional_decimal_from_json(
                payload.get("provider_reference_price"),
                "provider_reference_price",
            ),
            provider_reference_updated_at=_optional_datetime_from_json(
                payload.get("provider_reference_updated_at"),
                "provider_reference_updated_at",
            ),
            provider_reference_source=(
                str(payload["provider_reference_source"])
                if payload.get("provider_reference_source") is not None
                else None
            ),
            open=_decimal_from_json(payload["open"], "open"),
            high=_decimal_from_json(payload["high"], "high"),
            low=_decimal_from_json(payload["low"], "low"),
            close=_decimal_from_json(payload["close"], "close"),
            volume=int(payload["volume"]),
            first_event_at=_datetime_from_json(payload["first_event_at"], "first_event_at"),
            last_event_at=_datetime_from_json(payload["last_event_at"], "last_event_at"),
            completeness_status=CompletenessStatus(str(payload["completeness_status"])),
            completeness_evidence=tuple(str(item) for item in payload["completeness_evidence"]),
            health=ContextHealth(str(payload["health"])),
            reasons=tuple(str(item) for item in payload["reasons"]),
            source=str(payload["source"]),
            raw_source_digest=str(payload["raw_source_digest"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ArtifactIntegrityError):
            raise
        raise ArtifactIntegrityError("stored context artifact is invalid") from error
    if canonical_json(asdict(expected)) != canonical_json(payload):
        raise ArtifactIntegrityError("stored context artifact digest or derived fields do not match")
    return expected


def _reconciliation_from_payload(
    payload: dict[str, Any],
) -> TaifexNightReconciliationArtifact:
    try:
        field_deltas = tuple(
            (str(item[0]), _decimal_from_json(item[1], "field delta"))
            for item in payload["field_deltas"]
        )
        body = {
            "schema_version": str(payload["schema_version"]),
            "context_artifact_id": str(payload["context_artifact_id"]),
            "context_digest": str(payload["context_digest"]),
            "source": str(payload["source"]),
            "raw_source_digest": str(payload["raw_source_digest"]),
            "taifex_trading_date": _date_from_json(
                payload["taifex_trading_date"],
                "taifex_trading_date",
            ),
            "contract_code": str(payload["contract_code"]),
            "taifex_settlement_price": _optional_decimal_from_json(
                payload.get("taifex_settlement_price"),
                "taifex_settlement_price",
            ),
            "taifex_open": _optional_decimal_from_json(
                payload.get("taifex_open"), "taifex_open"
            ),
            "taifex_high": _optional_decimal_from_json(
                payload.get("taifex_high"), "taifex_high"
            ),
            "taifex_low": _optional_decimal_from_json(
                payload.get("taifex_low"), "taifex_low"
            ),
            "taifex_close": _optional_decimal_from_json(
                payload.get("taifex_close"), "taifex_close"
            ),
            "taifex_volume": (
                int(payload["taifex_volume"])
                if payload.get("taifex_volume") is not None
                else None
            ),
            "taifex_delivery_month": (
                str(payload["taifex_delivery_month"])
                if payload.get("taifex_delivery_month") is not None
                else None
            ),
            "taifex_volume_basis": (
                str(payload["taifex_volume_basis"])
                if payload.get("taifex_volume_basis") is not None
                else None
            ),
            "comparable_fields": tuple(
                str(item) for item in payload["comparable_fields"]
            ),
            "comparison_limitations": tuple(
                str(item) for item in payload["comparison_limitations"]
            ),
            "field_deltas": field_deltas,
            "status": ReconciliationStatus(str(payload["status"])),
            "reasons": tuple(str(item) for item in payload["reasons"]),
            "reconciled_at": _datetime_from_json(
                payload["reconciled_at"], "reconciled_at"
            ),
        }
        digest = sha256_digest(body)
        expected = TaifexNightReconciliationArtifact(
            reconciliation_id=f"taifex-reconciliation-{digest[:16]}",
            reconciliation_digest=digest,
            **body,
        )
    except (KeyError, TypeError, ValueError) as error:
        if isinstance(error, ArtifactIntegrityError):
            raise
        raise ArtifactIntegrityError("stored reconciliation artifact is invalid") from error
    if canonical_json(asdict(expected)) != canonical_json(payload):
        raise ArtifactIntegrityError("stored reconciliation artifact digest does not match")
    return expected


class FilePremarketArtifactRepository:
    """Content-addressed append-only files with fail-closed rehydration."""

    def __init__(self, root: Path) -> None:
        self._root = Path(root)
        self._lock = RLock()

    def save_raw(self, artifact: RawSourceArtifact) -> None:
        digest = _digest_path_component(artifact.raw_source_digest, "raw source digest")
        try:
            self._write_once(self._root / "raw" / f"{digest}.json", artifact)
        except ArtifactIntegrityError:
            existing = self.raw_source(digest)
            if existing is not None and (
                existing.schema_version,
                existing.source,
                existing.payload_json,
            ) == (
                artifact.schema_version,
                artifact.source,
                artifact.payload_json,
            ):
                return
            raise

    def save_context(self, artifact: TaifexNightContextArtifact) -> None:
        digest = _digest_path_component(artifact.context_digest, "context digest")
        self._write_once(self._root / "contexts" / f"{digest}.json", artifact)

    def save_reconciliation(self, artifact: TaifexNightReconciliationArtifact) -> None:
        context_digest = _digest_path_component(artifact.context_digest, "context digest")
        digest = _digest_path_component(artifact.reconciliation_digest, "reconciliation digest")
        self._write_once(
            self._root / "reconciliations" / context_digest / f"{digest}.json",
            artifact,
        )

    def raw_source(self, raw_source_digest: str) -> RawSourceArtifact | None:
        digest = _digest_path_component(raw_source_digest, "raw source digest")
        path = self._root / "raw" / f"{digest}.json"
        if not path.exists():
            return None
        payload = self._read_payload(path)
        try:
            artifact = RawSourceArtifact(
                schema_version=str(payload["schema_version"]),
                source=str(payload["source"]),
                raw_source_digest=str(payload["raw_source_digest"]),
                captured_at=_datetime_from_json(payload["captured_at"], "captured_at"),
                payload_json=str(payload["payload_json"]),
            )
        except (KeyError, TypeError, ValueError) as error:
            raise ArtifactIntegrityError(f"invalid raw source artifact: {path}") from error
        if (
            artifact.raw_source_digest != digest
            or canonical_json(asdict(artifact)) != canonical_json(payload)
        ):
            raise ArtifactIntegrityError(f"raw source artifact identity does not match path: {path}")
        return artifact

    def contexts(self) -> tuple[TaifexNightContextArtifact, ...]:
        directory = self._root / "contexts"
        if not directory.exists():
            return ()
        values = tuple(self._read_context(path) for path in sorted(directory.glob("*.json")))
        return tuple(
            sorted(
                values,
                key=lambda item: (
                    item.trading_date,
                    item.received_at,
                    item.context_digest,
                ),
            )
        )

    def reconciliations(
        self,
        context_digest: str,
    ) -> tuple[TaifexNightReconciliationArtifact, ...]:
        digest = _digest_path_component(context_digest, "context digest")
        directory = self._root / "reconciliations" / digest
        if not directory.exists():
            return ()
        values = tuple(
            self._read_reconciliation(path, digest)
            for path in sorted(directory.glob("*.json"))
        )
        return tuple(
            sorted(
                values,
                key=lambda item: (
                    item.reconciled_at,
                    item.reconciliation_digest,
                ),
            )
        )

    def latest_reconciliation(
        self,
        context_digest: str,
    ) -> TaifexNightReconciliationArtifact | None:
        values = self.reconciliations(context_digest)
        return values[-1] if values else None

    def _write_once(self, path: Path, artifact: object) -> None:
        content = canonical_json(asdict(artifact)) + "\n"  # type: ignore[arg-type]
        with self._lock:
            path.parent.mkdir(parents=True, exist_ok=True)
            try:
                descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                if path.read_text(encoding="utf-8") != content:
                    raise ArtifactIntegrityError(
                        f"existing artifact content does not match: {path}"
                    )
                return
            with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
                handle.write(content)
                handle.flush()
                os.fsync(handle.fileno())

    @staticmethod
    def _read_payload(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise ArtifactIntegrityError(f"cannot read artifact: {path}") from error
        if not isinstance(payload, dict):
            raise ArtifactIntegrityError(f"artifact must contain one object: {path}")
        return payload

    def _read_context(self, path: Path) -> TaifexNightContextArtifact:
        expected_digest = _digest_path_component(path.stem, "context path digest")
        artifact = _context_from_payload(self._read_payload(path))
        if artifact.context_digest != expected_digest:
            raise ArtifactIntegrityError(f"context artifact identity does not match path: {path}")
        return artifact

    def _read_reconciliation(
        self,
        path: Path,
        context_digest: str,
    ) -> TaifexNightReconciliationArtifact:
        expected_digest = _digest_path_component(path.stem, "reconciliation path digest")
        artifact = _reconciliation_from_payload(self._read_payload(path))
        if (
            artifact.reconciliation_digest != expected_digest
            or artifact.context_digest != context_digest
        ):
            raise ArtifactIntegrityError(
                f"reconciliation artifact identity does not match path: {path}"
            )
        return artifact
