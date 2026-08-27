"""Ports and transport-neutral values for daily institutional MVP operation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping, Protocol

from institutional_mvp.domain import (
    DailyRunStatus,
    InstitutionalMvpCandidateBatchV1,
)


@dataclass(frozen=True)
class InstitutionalFlowSnapshot:
    provider: str
    source_version: str
    retrieved_at: datetime
    wide_payload: bytes
    stock_info_payload: bytes
    wide_row_count: int
    stock_info_row_count: int
    usage_user_count_before: int
    usage_request_limit: int
    usage_remaining_before: int


@dataclass(frozen=True)
class InstitutionalMvpArtifactPublication:
    status: DailyRunStatus
    artifact_id: str
    artifact_digest: str
    source_session: date
    target_session: date
    path: Path


class InstitutionalFlowProvider(Protocol):
    def fetch_daily(self, source_session: date) -> InstitutionalFlowSnapshot:
        """Fetch exactly one daily flow payload and the current identity mapping."""


class InstitutionalMvpCandidateBatchRepository(Protocol):
    def put_immutable(
        self, batch: InstitutionalMvpCandidateBatchV1
    ) -> InstitutionalMvpArtifactPublication:
        """Publish, replay, or append one immutable batch revision."""

    def get_by_target_session(
        self, target_session: date
    ) -> Mapping[str, Any] | None:
        """Return the sole verified revision, or fail closed on ambiguity."""

    def get_by_digest(
        self, *, target_session: date, artifact_digest: str
    ) -> Mapping[str, Any] | None:
        """Return one exactly pinned and verified batch revision."""


class ReviewedEquitySessionCalendar(Protocol):
    schema_version: str
    timezone: str
    coverage_start: date
    coverage_end: date
    source_digest: str

    def next_trading_day(self, value: date) -> date:
        """Return the reviewed next equity session or fail closed."""
