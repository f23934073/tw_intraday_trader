"""Exploratory institutional factor diagnostics; no execution semantics.

Layer:     L1-A (Diagnostics)
Lineage:   A  (institutional_data -> institutional_research -> institutional_prior)
Depends:   institutional_data, watchlist, market_data
Consumed:  institutional_prior
Status:    EXPLORATORY

Lineage B (institutional_mvp) is a separate stack built on `backtest` and must
not be imported from here. See
architecture/contracts/institutional_bounded_context.md.
"""

from .application import InstitutionalFactorDiagnostics
from .domain import (
    ArtifactIdentity,
    BaselineFactorDefinition,
    DefinitionIdentity,
    FactorMetric,
    InstitutionalComponent,
    InstitutionalFactorReportArtifact,
    ResearchLabel,
    ResearchRunManifestV0,
)
from .inputs import (
    DailyAdjustedClose,
    InstitutionalResearchInput,
    PriceResearchInput,
    ResearchInputError,
    institutional_bundle_sha256,
    price_rows_sha256,
)
from .serialization import factor_definition_sha256

__all__ = [
    "ArtifactIdentity",
    "BaselineFactorDefinition",
    "DailyAdjustedClose",
    "DefinitionIdentity",
    "FactorMetric",
    "InstitutionalComponent",
    "InstitutionalFactorDiagnostics",
    "InstitutionalFactorReportArtifact",
    "InstitutionalResearchInput",
    "PriceResearchInput",
    "ResearchInputError",
    "ResearchLabel",
    "ResearchRunManifestV0",
    "factor_definition_sha256",
    "institutional_bundle_sha256",
    "price_rows_sha256",
]
