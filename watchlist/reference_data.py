"""Point-in-time equity-universe contracts shared by research/watchlist code."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Protocol


PIT_UNIVERSE_MISSING = "PIT_UNIVERSE_MISSING"
SURVIVORSHIP_LIMITED = "SURVIVORSHIP_LIMITED"


class EquityMarket(StrEnum):
    TWSE = "TWSE"
    TPEX = "TPEX"


class SecurityType(StrEnum):
    COMMON_STOCK = "COMMON_STOCK"
    PREFERRED_STOCK = "PREFERRED_STOCK"
    ETF = "ETF"
    ETN = "ETN"
    REIT = "REIT"
    WARRANT = "WARRANT"
    OTHER = "OTHER"


class MarketCapCohort(StrEnum):
    SMALL = "SMALL"
    MID = "MID"
    LARGE = "LARGE"


class UniverseEvidenceMode(StrEnum):
    DATE_EFFECTIVE = "DATE_EFFECTIVE"
    CURRENT_SNAPSHOT = "CURRENT_SNAPSHOT"


class UniverseArtifactStatus(StrEnum):
    VALIDATED = "VALIDATED"
    QUARANTINED = "QUARANTINED"


ELIGIBLE_SECURITY_TYPES = frozenset({SecurityType.COMMON_STOCK})


def _non_empty(value: str, field_name: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    return normalized


def _optional_non_empty(value: str | None, field_name: str) -> str | None:
    return None if value is None else _non_empty(value, field_name)


def _require_sha256(value: str, field_name: str) -> None:
    if len(value) != 64 or any(
        character not in "0123456789abcdef" for character in value
    ):
        raise ValueError(f"{field_name} must be a lowercase SHA256 digest")


def _optional_sha256(value: str | None, field_name: str) -> None:
    if value is not None:
        _require_sha256(value, field_name)


@dataclass(frozen=True)
class DateEffectiveEquityRecord:
    """One version of a security and its classifications over an interval.

    ``listed_until`` and ``effective_to`` are exclusive upper bounds.
    """

    symbol: str
    name: str
    market: EquityMarket
    security_type: SecurityType
    listed_from: date
    listed_until: date | None
    industry_code: str
    industry_name: str
    industry_as_of: date
    market_cap_twd: int
    market_cap_cohort: MarketCapCohort
    market_cap_as_of: date
    effective_from: date
    effective_to: date | None
    source_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "symbol", _non_empty(self.symbol, "symbol").upper())
        object.__setattr__(self, "name", _non_empty(self.name, "name"))
        object.__setattr__(self, "market", EquityMarket(self.market))
        object.__setattr__(self, "security_type", SecurityType(self.security_type))
        object.__setattr__(
            self,
            "industry_code",
            _non_empty(self.industry_code, "industry_code").upper(),
        )
        object.__setattr__(
            self,
            "industry_name",
            _non_empty(self.industry_name, "industry_name"),
        )
        object.__setattr__(
            self,
            "market_cap_cohort",
            MarketCapCohort(self.market_cap_cohort),
        )
        if isinstance(self.market_cap_twd, bool) or not isinstance(
            self.market_cap_twd, int
        ):
            raise ValueError("market_cap_twd must be an integer")
        if self.market_cap_twd <= 0:
            raise ValueError("market_cap_twd must be positive")
        _require_sha256(self.source_digest, "source_digest")

        if self.listed_until is not None and self.listed_until <= self.listed_from:
            raise ValueError("listed_until must be after listed_from")
        if self.effective_from < self.listed_from:
            raise ValueError("effective_from cannot precede listed_from")
        if self.effective_to is not None and self.effective_to <= self.effective_from:
            raise ValueError("effective_to must be after effective_from")
        if self.listed_until is not None:
            if self.effective_from >= self.listed_until:
                raise ValueError("effective_from must precede listed_until")
            if self.effective_to is None or self.effective_to > self.listed_until:
                raise ValueError("effective interval cannot extend beyond listed_until")
        if self.industry_as_of > self.effective_from:
            raise ValueError("industry_as_of cannot be after effective_from")
        if self.market_cap_as_of > self.effective_from:
            raise ValueError("market_cap_as_of cannot be after effective_from")

    @property
    def equity_eligible(self) -> bool:
        return self.security_type in ELIGIBLE_SECURITY_TYPES

    def active_on(self, session: date) -> bool:
        listed = self.listed_from <= session and (
            self.listed_until is None or session < self.listed_until
        )
        effective = self.effective_from <= session and (
            self.effective_to is None or session < self.effective_to
        )
        return listed and effective


@dataclass(frozen=True)
class EquityUniverseSnapshot:
    snapshot_id: str
    records: tuple[DateEffectiveEquityRecord, ...]

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "snapshot_id",
            _non_empty(self.snapshot_id, "snapshot_id"),
        )
        object.__setattr__(
            self,
            "records",
            tuple(
                sorted(
                    self.records,
                    key=lambda record: (
                        record.market.value,
                        record.symbol,
                        record.effective_from,
                        record.effective_to or date.max,
                    ),
                )
            ),
        )


@dataclass(frozen=True)
class EquityUniverseManifest:
    """Auditable source, revision, availability, coverage, and digest metadata."""

    snapshot_id: str
    evidence_mode: UniverseEvidenceMode
    source_id: str
    source_license: str
    source_revision: int
    parent_snapshot_id: str | None
    correction_policy_note: str
    immutable_revision_policy: str
    retrieved_at: datetime
    available_from_session: date
    coverage_start: date | None
    coverage_end: date | None
    covered_markets: frozenset[EquityMarket]
    record_count: int
    source_digest: str | None
    content_digest: str | None
    status: UniverseArtifactStatus

    def __post_init__(self) -> None:
        for field_name in (
            "snapshot_id",
            "source_id",
            "source_license",
            "correction_policy_note",
            "immutable_revision_policy",
        ):
            object.__setattr__(
                self,
                field_name,
                _non_empty(getattr(self, field_name), field_name),
            )
        object.__setattr__(
            self,
            "parent_snapshot_id",
            _optional_non_empty(self.parent_snapshot_id, "parent_snapshot_id"),
        )
        object.__setattr__(
            self,
            "evidence_mode",
            UniverseEvidenceMode(self.evidence_mode),
        )
        object.__setattr__(self, "status", UniverseArtifactStatus(self.status))
        object.__setattr__(
            self,
            "covered_markets",
            frozenset(EquityMarket(market) for market in self.covered_markets),
        )
        if isinstance(self.source_revision, bool) or not isinstance(
            self.source_revision, int
        ):
            raise ValueError("source_revision must be an integer")
        if self.source_revision <= 0:
            raise ValueError("source_revision must be positive")
        if self.source_revision == 1 and self.parent_snapshot_id is not None:
            raise ValueError("first source revision cannot have a parent_snapshot_id")
        if self.source_revision > 1 and self.parent_snapshot_id is None:
            raise ValueError("later source revisions require a parent_snapshot_id")
        if isinstance(self.record_count, bool) or not isinstance(
            self.record_count, int
        ):
            raise ValueError("record_count must be an integer")
        if self.record_count < 0:
            raise ValueError("record_count must be non-negative")
        if self.retrieved_at.tzinfo is None or self.retrieved_at.utcoffset() is None:
            raise ValueError("retrieved_at must be timezone-aware")
        if (
            self.coverage_start is not None
            and self.coverage_end is not None
            and self.coverage_end < self.coverage_start
        ):
            raise ValueError("coverage_end cannot precede coverage_start")
        _optional_sha256(self.source_digest, "source_digest")
        _optional_sha256(self.content_digest, "content_digest")


@dataclass(frozen=True)
class EquityUniverseArtifact:
    snapshot: EquityUniverseSnapshot
    manifest: EquityUniverseManifest

    def __post_init__(self) -> None:
        if self.snapshot.snapshot_id != self.manifest.snapshot_id:
            raise ValueError("snapshot and manifest identities must match")


@dataclass(frozen=True)
class EquityUniverseResolution:
    as_of_session: date
    snapshot_id: str
    evidence_mode: UniverseEvidenceMode
    content_digest: str | None
    active_records: tuple[DateEffectiveEquityRecord, ...]
    research_members: tuple[DateEffectiveEquityRecord, ...]
    research_eligible: bool
    issue_codes: tuple[str, ...]

    @property
    def cross_sectional_diagnostics_allowed(self) -> bool:
        return self.research_eligible

    @property
    def matched_controls_allowed(self) -> bool:
        return self.research_eligible

    @property
    def formal_research_allowed(self) -> bool:
        return self.research_eligible


class EquityUniversePort(Protocol):
    def resolve(self, as_of_session: date) -> EquityUniverseResolution:
        """Resolve an immutable snapshot for one historical session."""


class SnapshotEquityUniverse:
    """An immutable, explicitly pinned universe artifact query boundary."""

    def __init__(self, artifact: EquityUniverseArtifact) -> None:
        self._artifact = artifact

    @property
    def artifact(self) -> EquityUniverseArtifact:
        return self._artifact

    def resolve(self, as_of_session: date) -> EquityUniverseResolution:
        manifest = self._artifact.manifest
        snapshot = self._artifact.snapshot
        issues: list[str] = []

        if manifest.evidence_mode is UniverseEvidenceMode.CURRENT_SNAPSHOT:
            issues.extend((PIT_UNIVERSE_MISSING, SURVIVORSHIP_LIMITED))
        if manifest.status is not UniverseArtifactStatus.VALIDATED:
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_NOT_VALIDATED"))
        if (
            manifest.coverage_start is None
            or manifest.coverage_end is None
            or not manifest.covered_markets
        ):
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_COVERAGE_MISSING"))
        elif not manifest.coverage_start <= as_of_session <= manifest.coverage_end:
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_OUT_OF_COVERAGE"))
        if manifest.source_digest is None or manifest.content_digest is None:
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_DIGEST_MISSING"))
        elif any(
            record.source_digest != manifest.source_digest
            for record in snapshot.records
        ):
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_SOURCE_DIGEST_MISMATCH"))
        if manifest.record_count != len(snapshot.records):
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_ROW_COUNT_MISMATCH"))
        if any(
            record.market not in manifest.covered_markets for record in snapshot.records
        ):
            issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_MARKET_OUT_OF_SCOPE"))

        if manifest.content_digest is not None:
            from watchlist.serialization import snapshot_sha256

            if snapshot_sha256(snapshot) != manifest.content_digest:
                issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_DIGEST_MISMATCH"))

        active = tuple(
            sorted(
                (
                    record
                    for record in snapshot.records
                    if record.active_on(as_of_session)
                ),
                key=lambda record: (record.market.value, record.symbol),
            )
        )
        if not active:
            issues.extend((PIT_UNIVERSE_MISSING, "NO_ACTIVE_UNIVERSE_RECORDS"))
        active_symbols: set[tuple[EquityMarket, str]] = set()
        for record in active:
            identity = (record.market, record.symbol)
            if identity in active_symbols:
                issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_INTERVAL_OVERLAP"))
                break
            active_symbols.add(identity)
            if record.market not in manifest.covered_markets:
                issues.extend((PIT_UNIVERSE_MISSING, "UNIVERSE_MARKET_OUT_OF_SCOPE"))
                break

        issues = list(dict.fromkeys(issues))
        research_eligible = not issues and bool(active)
        members = (
            tuple(record for record in active if record.equity_eligible)
            if research_eligible
            else ()
        )
        if research_eligible and not members:
            issues.extend((PIT_UNIVERSE_MISSING, "NO_ELIGIBLE_EQUITIES"))
            research_eligible = False

        return EquityUniverseResolution(
            as_of_session=as_of_session,
            snapshot_id=snapshot.snapshot_id,
            evidence_mode=manifest.evidence_mode,
            content_digest=manifest.content_digest,
            active_records=active,
            research_members=members if research_eligible else (),
            research_eligible=research_eligible,
            issue_codes=tuple(dict.fromkeys(issues)),
        )
