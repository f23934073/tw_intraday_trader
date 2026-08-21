"""Raw-first orchestration for official institutional-flow ingestion."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date

from institutional_data.artifacts import (
    InstitutionalRawArtifact,
    InstitutionalRawArtifactKey,
    InstitutionalRawArtifactStore,
    InstitutionalRawCapture,
)
from institutional_data.domain import (
    InstitutionalFlowDaily,
    InstitutionalPartitionManifest,
    PartitionStatus,
)
from institutional_data.serialization import (
    canonical_json,
    flow_rows_sha256,
    serialize_flow_rows,
    sha256_text,
)
from institutional_data.sources import (
    InstitutionalOfficialSourceAdapter,
    InstitutionalSourceContractError,
    InstitutionalSourceResponse,
)
from institutional_data.validation import (
    ValidationIssue,
    ValidationReport,
    validate_partition,
)


@dataclass(frozen=True)
class InstitutionalIngestionResult:
    """One replayable raw-to-normalized attempt, including quarantined attempts."""

    raw_artifact: InstitutionalRawArtifact
    manifest: InstitutionalPartitionManifest
    rows: tuple[InstitutionalFlowDaily, ...]
    normalized_json: str
    validation_report: ValidationReport

    @property
    def is_validated(self) -> bool:
        return (
            self.manifest.status is PartitionStatus.VALIDATED
            and self.validation_report.is_valid
        )


def _partition_id(
    artifact: InstitutionalRawArtifact,
    parser_version: str,
) -> str:
    identity = canonical_json(
        {
            "market": artifact.key.market.value,
            "session_date": artifact.key.session_date,
            "source_product": artifact.key.source_product,
            "trade_scope_id": artifact.key.trade_scope_id,
            "raw_artifact_id": artifact.artifact_id,
            "raw_sha256": artifact.raw_sha256,
            "parser_version": parser_version,
        }
    )
    return (
        f"institutional-{artifact.key.market.value.lower()}-"
        f"{artifact.key.session_date.isoformat()}-{sha256_text(identity)[:16]}"
    )


class InstitutionalIngestionService:
    """Seal raw bytes, normalize, validate, then publish or quarantine."""

    def __init__(self, raw_store: InstitutionalRawArtifactStore) -> None:
        self._raw_store = raw_store

    def acquire_and_ingest(
        self,
        adapter: InstitutionalOfficialSourceAdapter,
        *,
        requested_session: date,
        usable_from_session: date,
        requested_trade_scope_id: str,
        timeout_seconds: float = 30.0,
    ) -> InstitutionalIngestionResult:
        response = adapter.fetch(
            requested_session,
            timeout_seconds=timeout_seconds,
        )
        return self.ingest_response(
            adapter,
            response=response,
            requested_session=requested_session,
            usable_from_session=usable_from_session,
            requested_trade_scope_id=requested_trade_scope_id,
        )

    def ingest_response(
        self,
        adapter: InstitutionalOfficialSourceAdapter,
        *,
        response: InstitutionalSourceResponse,
        requested_session: date,
        usable_from_session: date,
        requested_trade_scope_id: str,
    ) -> InstitutionalIngestionResult:
        raw_artifact = self._raw_store.capture(
            InstitutionalRawCapture(
                key=InstitutionalRawArtifactKey(
                    market=adapter.market,
                    session_date=requested_session,
                    source_product=adapter.source_product,
                    trade_scope_id=adapter.trade_scope_id,
                ),
                source_url=response.source_url,
                request_method=response.request_method,
                request_parameters=response.request_parameters,
                response_headers=response.response_headers,
                content_type=response.content_type,
                parser_version=adapter.parser_version,
                retrieved_at=response.retrieved_at,
                first_observed_at=response.first_observed_at,
                payload=response.body,
            )
        )
        partition_id = _partition_id(raw_artifact, adapter.parser_version)

        source_issue: ValidationIssue | None = None
        rows: tuple[InstitutionalFlowDaily, ...] = ()
        source_row_count = 0
        if requested_trade_scope_id != adapter.trade_scope_id:
            source_issue = ValidationIssue(
                code="SCOPE_MISMATCH",
                message=(
                    "requested trade scope does not match the reviewed adapter scope"
                ),
                field="trade_scope_id",
            )
        else:
            try:
                parsed = adapter.parse(
                    raw_artifact,
                    partition_id=partition_id,
                    requested_session=requested_session,
                    usable_from_session=usable_from_session,
                )
                rows = parsed.rows
                source_row_count = parsed.source_row_count
            except InstitutionalSourceContractError as error:
                source_issue = ValidationIssue(
                    code=error.code,
                    message=str(error),
                )
            except (TypeError, ValueError) as error:
                source_issue = ValidationIssue(
                    code="NORMALIZATION_ERROR",
                    message=f"normalized row contract rejected source values: {error}",
                )

        normalized_json = serialize_flow_rows(rows)
        manifest = InstitutionalPartitionManifest(
            partition_id=partition_id,
            market=adapter.market,
            session_date=requested_session,
            source_product=adapter.source_product,
            trade_scope_id=adapter.trade_scope_id,
            correction_policy=adapter.correction_policy,
            response_scope_note=adapter.response_scope_note,
            raw_artifact_id=raw_artifact.artifact_id,
            raw_sha256=raw_artifact.raw_sha256,
            normalized_sha256=flow_rows_sha256(rows),
            retrieved_at=raw_artifact.retrieved_at,
            first_observed_at=raw_artifact.first_observed_at,
            usable_from_session=usable_from_session,
            source_row_count=source_row_count,
            normalized_row_count=len(rows),
            status=(
                PartitionStatus.QUARANTINED
                if source_issue is not None
                else PartitionStatus.NORMALIZED
            ),
        )
        partition_report = validate_partition(manifest, rows)
        issues = (
            (source_issue,) if source_issue is not None else ()
        ) + partition_report.issues
        report = ValidationReport(issues=issues, checks=partition_report.checks)
        manifest = replace(
            manifest,
            status=(
                PartitionStatus.VALIDATED
                if report.is_valid
                else PartitionStatus.QUARANTINED
            ),
        )
        return InstitutionalIngestionResult(
            raw_artifact=raw_artifact,
            manifest=manifest,
            rows=rows,
            normalized_json=normalized_json,
            validation_report=report,
        )
