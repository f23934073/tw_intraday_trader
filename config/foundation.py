"""Phase 0 foundation defaults.

These values document the approved architecture direction without activating
new runtime behavior.  In particular, this module does not create database
connections, write a journal, expose a network service, or contact a broker.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Final


FOUNDATION_CONTRACT_VERSION: Final = "foundation_v0"


class PersistentJournalAuthority(StrEnum):
    """Planned authority when persistent journaling is introduced."""

    POSTGRESQL = "postgresql"


class WebExposure(StrEnum):
    """Approved boundary for the future local dashboard service."""

    LOOPBACK_SINGLE_USER = "loopback_single_user"


class ProjectionTransport(StrEnum):
    """Initial transport choice before any future SSE upgrade."""

    POLLING = "polling"


@dataclass(frozen=True)
class FoundationDefaults:
    """Reviewable architecture defaults that do not alter current behavior."""

    contract_version: str = FOUNDATION_CONTRACT_VERSION
    persistent_journal_authority: PersistentJournalAuthority = (
        PersistentJournalAuthority.POSTGRESQL
    )
    raw_capture_retention: str = "review_required"
    web_exposure: WebExposure = WebExposure.LOOPBACK_SINGLE_USER
    initial_projection_transport: ProjectionTransport = ProjectionTransport.POLLING
    ci_python_versions: tuple[str, ...] = ("3.11", "3.12")
    pilot_symbols: tuple[str, ...] = ()


@dataclass(frozen=True)
class FoundationFeatureFlags:
    """Future foundation capabilities; every capability remains disabled."""

    event_runtime_enabled: bool = False
    journal_enabled: bool = False
    replay_enabled: bool = False
    risk_gate_enabled: bool = False
    shadow_enabled: bool = False
    projection_sse_enabled: bool = False


FOUNDATION_DEFAULTS: Final = FoundationDefaults()
FOUNDATION_FEATURE_FLAGS: Final = FoundationFeatureFlags()
