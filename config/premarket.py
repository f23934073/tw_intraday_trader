"""Fail-closed configuration for the TAIFEX premarket context."""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path


def _flag(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PremarketContextConfig:
    schema_version: str
    readiness_predicate_version: str
    calendar_path: Path
    artifact_dir: Path
    query_delay: timedelta
    retry_interval: timedelta
    session_start_tolerance: timedelta
    session_end_tolerance: timedelta
    qualified_completion_evidence: tuple[tuple[str, str], ...]
    capture_enabled: bool
    dashboard_enabled: bool
    day_open_confirmation_enabled: bool = False
    affects_decisions: bool = False
    contract_alias: str = "TXFR1"
    product_root: str = "TXF"
    timezone: str = "Asia/Taipei"

    def __post_init__(self) -> None:
        if not self.schema_version.strip() or not self.readiness_predicate_version.strip():
            raise ValueError("premarket schema and readiness predicate versions are required")
        if self.query_delay < timedelta(0):
            raise ValueError("query delay cannot be negative")
        if self.retry_interval <= timedelta(0):
            raise ValueError("retry interval must be positive")
        if self.session_start_tolerance < timedelta(0) or self.session_end_tolerance < timedelta(0):
            raise ValueError("session tolerances cannot be negative")
        if not self.contract_alias.strip() or not self.product_root.strip():
            raise ValueError("contract alias and product root are required")
        if self.day_open_confirmation_enabled:
            raise ValueError("day-open confirmation is outside premarket context v0")
        if self.affects_decisions:
            raise ValueError("premarket context v0 must remain observation-only")

    def completion_is_qualified(self, source: str, evidence: tuple[str, ...]) -> bool:
        allowed = set(self.qualified_completion_evidence)
        return any((source, item) in allowed for item in evidence)


PREMARKET_CONTEXT_V0 = PremarketContextConfig(
    schema_version="taifex_night_context_v0",
    readiness_predicate_version="taifex_night_ready_v0",
    calendar_path=Path(__file__).with_name("taifex_calendar_2026.json"),
    artifact_dir=Path(os.environ.get("TAIFEX_PREMARKET_ARTIFACT_DIR", "data/premarket")),
    query_delay=timedelta(minutes=5),
    retry_interval=timedelta(minutes=1),
    session_start_tolerance=timedelta(minutes=1),
    session_end_tolerance=timedelta(minutes=1),
    # Only deterministic Mock fixtures are qualified in-repository. Shioaji
    # remains UNKNOWN until a reviewed real Kbar/Tick capture freezes evidence.
    qualified_completion_evidence=(
        ("MOCK_FIXTURE", "MOCK_FIXTURE_SESSION_COMPLETE"),
    ),
    capture_enabled=_flag("TAIFEX_PREMARKET_CAPTURE_ENABLED", True),
    dashboard_enabled=_flag("TAIFEX_PREMARKET_DASHBOARD_ENABLED", True),
    day_open_confirmation_enabled=_flag(
        "TAIFEX_DAY_OPEN_CONFIRMATION_ENABLED",
        False,
    ),
    affects_decisions=_flag("TAIFEX_CONTEXT_AFFECTS_DECISIONS", False),
)
