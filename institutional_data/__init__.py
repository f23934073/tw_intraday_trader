"""Post-close institutional-flow data contracts.

Layer:     L0 (Contracts)
Lineage:   Shared base (institutional_data)
Depends:   none
Consumed:  institutional_research, institutional_prior, institutional_mvp,
           config.institutional_mvp
Status:    STABLE

Lineages A and B share these contracts, but this package must not import either
lineage or any execution layer. See
architecture/contracts/institutional_bounded_context.md.
"""

from institutional_data.application import (
    InstitutionalIngestionResult,
    InstitutionalIngestionService,
)
from institutional_data.artifacts import (
    DirectoryInstitutionalRawArtifactStore,
    InMemoryInstitutionalRawArtifactStore,
    InstitutionalRawArtifact,
    InstitutionalRawArtifactKey,
    InstitutionalRawArtifactStore,
    InstitutionalRawCapture,
)
from institutional_data.domain import (
    CorrectionPolicy,
    InstitutionalFlowDaily,
    InstitutionalMarket,
    InstitutionalPartitionManifest,
    PartitionStatus,
    PARTITION_STATUS_V1_VALUES,
    ScopeCompatibility,
    ScopeCompatibilityDecision,
    TradeCategory,
    TradeScope,
)
from institutional_data.serialization import (
    FLOW_ROWS_SCHEMA_VERSION,
    PARTITION_MANIFEST_SCHEMA_VERSION,
    PARTITION_MANIFEST_V1_FIELDS,
    InstitutionalSerializationError,
    deserialize_flow_rows,
    deserialize_partition_manifest,
    flow_rows_sha256,
    serialize_flow_rows,
    serialize_partition_manifest,
)
from institutional_data.sources import (
    TPEX_ENDPOINT,
    TPEX_PARSER_VERSION,
    TPEX_RESPONSE_SCOPE_NOTE,
    TPEX_SOURCE_PRODUCT,
    TPEX_TRADE_SCOPE_ID,
    TWSE_ENDPOINT,
    TWSE_PARSER_VERSION,
    TWSE_RESPONSE_SCOPE_NOTE,
    TWSE_SOURCE_PRODUCT,
    TWSE_TRADE_SCOPE_ID,
    InstitutionalOfficialSourceAdapter,
    InstitutionalSourceContractError,
    InstitutionalSourceResponse,
    ParsedInstitutionalSource,
    TpexInstitutionalSourceAdapter,
    TwseInstitutionalSourceAdapter,
)
from institutional_data.validation import (
    ValidationCheck,
    ValidationIssue,
    ValidationReport,
    ValidationStatus,
    assess_trade_scope_compatibility,
    validate_flow_row,
    validate_partition,
)

__all__ = [
    "TPEX_ENDPOINT",
    "TPEX_PARSER_VERSION",
    "TPEX_RESPONSE_SCOPE_NOTE",
    "TPEX_SOURCE_PRODUCT",
    "TPEX_TRADE_SCOPE_ID",
    "TWSE_ENDPOINT",
    "TWSE_PARSER_VERSION",
    "TWSE_RESPONSE_SCOPE_NOTE",
    "TWSE_SOURCE_PRODUCT",
    "TWSE_TRADE_SCOPE_ID",
    "FLOW_ROWS_SCHEMA_VERSION",
    "PARTITION_MANIFEST_SCHEMA_VERSION",
    "PARTITION_MANIFEST_V1_FIELDS",
    "PARTITION_STATUS_V1_VALUES",
    "CorrectionPolicy",
    "DirectoryInstitutionalRawArtifactStore",
    "InMemoryInstitutionalRawArtifactStore",
    "InstitutionalFlowDaily",
    "InstitutionalIngestionResult",
    "InstitutionalIngestionService",
    "InstitutionalMarket",
    "InstitutionalOfficialSourceAdapter",
    "InstitutionalPartitionManifest",
    "InstitutionalRawArtifact",
    "InstitutionalRawArtifactKey",
    "InstitutionalRawArtifactStore",
    "InstitutionalRawCapture",
    "InstitutionalSerializationError",
    "InstitutionalSourceContractError",
    "InstitutionalSourceResponse",
    "ParsedInstitutionalSource",
    "PartitionStatus",
    "ScopeCompatibility",
    "ScopeCompatibilityDecision",
    "TradeCategory",
    "TradeScope",
    "TpexInstitutionalSourceAdapter",
    "TwseInstitutionalSourceAdapter",
    "ValidationCheck",
    "ValidationIssue",
    "ValidationReport",
    "ValidationStatus",
    "assess_trade_scope_compatibility",
    "deserialize_flow_rows",
    "deserialize_partition_manifest",
    "flow_rows_sha256",
    "serialize_flow_rows",
    "serialize_partition_manifest",
    "validate_flow_row",
    "validate_partition",
]
