"""Canonical bytes and digests for institutional research artifacts."""

from __future__ import annotations

from dataclasses import fields, is_dataclass
from typing import Any

from institutional_data.serialization import canonical_json, sha256_text

from .domain import (
    BaselineFactorDefinition,
    InstitutionalFactorReport,
    InstitutionalFactorReportArtifact,
)


FACTOR_DEFINITION_SCHEMA_VERSION = "institutional_baseline_factor_definition_v0"
FACTOR_REPORT_SCHEMA_VERSION = "institutional_factor_report_v0"


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


def serialize_factor_definition(definition: BaselineFactorDefinition) -> str:
    return canonical_json(
        {
            "schema_version": FACTOR_DEFINITION_SCHEMA_VERSION,
            "definition": _to_payload(definition),
        }
    )


def factor_definition_sha256(definition: BaselineFactorDefinition) -> str:
    return sha256_text(serialize_factor_definition(definition))


def serialize_factor_report(report: InstitutionalFactorReport) -> str:
    return canonical_json(
        {
            "schema_version": FACTOR_REPORT_SCHEMA_VERSION,
            "report": _to_payload(report),
        }
    )


def build_report_artifact(
    report: InstitutionalFactorReport,
) -> InstitutionalFactorReportArtifact:
    report_json = serialize_factor_report(report)
    return InstitutionalFactorReportArtifact(
        report=report,
        report_json=report_json,
        report_digest=sha256_text(report_json),
    )
