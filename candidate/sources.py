"""Candidate discovery sources for the Momentum subscription universe."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from types import MappingProxyType
from typing import Callable, Iterable, Mapping

from candidate.models import Candidate, CandidateSource
from market_data.scanner import ScannerClient, ScannerRankType, ScannerResponse


@dataclass(frozen=True, order=True)
class CandidateContributionReference:
    """Bounded pointer to source evidence; never embeds source-domain details."""

    source: CandidateSource
    artifact_id: str
    entry_digest: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "source", CandidateSource(self.source))
        artifact_id = self.artifact_id.strip()
        if not artifact_id:
            raise ValueError("candidate evidence artifact_id must not be empty")
        if len(self.entry_digest) != 64 or any(
            character not in "0123456789abcdef" for character in self.entry_digest
        ):
            raise ValueError(
                "candidate evidence entry_digest must be a lowercase SHA256 digest"
            )
        object.__setattr__(self, "artifact_id", artifact_id)


@dataclass(frozen=True)
class CandidateDiscovery:
    symbol: str
    source: CandidateSource
    rank_types: tuple[str, ...]
    best_rank: int | None
    discovered_at: datetime
    expires_at: datetime | None
    priority: int
    contribution_ref: CandidateContributionReference | None = None
    evidence: Mapping[str, object] = field(default_factory=dict)

    def __post_init__(self) -> None:
        symbol = self.symbol.strip().upper()
        if not symbol:
            raise ValueError("candidate symbol must not be empty")
        if self.discovered_at.tzinfo is None:
            raise ValueError("candidate discovered_at must be timezone-aware")
        if self.expires_at is not None:
            if self.expires_at.tzinfo is None:
                raise ValueError("candidate expires_at must be timezone-aware")
            if self.expires_at < self.discovered_at:
                raise ValueError("candidate expires_at cannot predate discovery")
        if self.best_rank is not None and self.best_rank <= 0:
            raise ValueError("candidate best_rank must be positive")
        rank_types = tuple(
            sorted(
                {
                    str(value).strip()
                    for value in self.rank_types
                    if str(value).strip()
                }
            )
        )
        if (
            self.contribution_ref is not None
            and self.contribution_ref.source is not self.source
        ):
            raise ValueError("candidate contribution reference source mismatch")
        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "rank_types", rank_types)
        object.__setattr__(self, "evidence", _freeze_mapping(self.evidence))


class MarketScannerCandidateSource:
    """Union configured Scanner rankings into symbol-level discoveries."""

    def __init__(
        self,
        client: ScannerClient,
        *,
        rank_types: tuple[ScannerRankType, ...],
        count_per_rank: int,
        ttl: timedelta,
        priority: int,
        instrument_eligible: Callable[[str], bool],
    ) -> None:
        if not rank_types:
            raise ValueError("at least one Scanner rank type is required")
        if not 1 <= count_per_rank <= 200:
            raise ValueError("count_per_rank must be between 1 and 200")
        if ttl <= timedelta(0):
            raise ValueError("Scanner candidate ttl must be positive")
        self._client = client
        self._rank_types = tuple(dict.fromkeys(rank_types))
        self._count_per_rank = count_per_rank
        self._ttl = ttl
        self._priority = priority
        self._instrument_eligible = instrument_eligible
        self._responses: list[ScannerResponse] = []

    @property
    def responses(self) -> tuple[ScannerResponse, ...]:
        return tuple(self._responses)

    def discover(self) -> tuple[CandidateDiscovery, ...]:
        by_symbol: dict[str, list[tuple[ScannerResponse, int, Mapping[str, object]]]] = {}
        responses: list[ScannerResponse] = []
        for rank_type in self._rank_types:
            response = self._client.scan(
                rank_type,
                count=self._count_per_rank,
                ascending=False,
            )
            responses.append(response)
            for row in response.rows:
                if self._instrument_eligible(row.symbol):
                    by_symbol.setdefault(row.symbol, []).append(
                        (response, row.rank, row.fields)
                    )

        self._responses.extend(responses)
        discoveries: list[CandidateDiscovery] = []
        for symbol, observations in by_symbol.items():
            discovered_at = max(item[0].observed_at for item in observations)
            rank_by_type = {
                item[0].rank_type.value: item[1]
                for item in observations
            }
            response_digests = {
                item[0].rank_type.value: item[0].digest
                for item in observations
            }
            scanner_fields = {
                item[0].rank_type.value: dict(item[2])
                for item in observations
            }
            discoveries.append(
                CandidateDiscovery(
                    symbol=symbol,
                    source=CandidateSource.SCANNER,
                    rank_types=tuple(rank_by_type),
                    best_rank=min(rank_by_type.values()),
                    discovered_at=discovered_at,
                    expires_at=discovered_at + self._ttl,
                    priority=self._priority,
                    evidence={
                        "rank_by_type": rank_by_type,
                        "response_digests": response_digests,
                        "scanner_fields": scanner_fields,
                    },
                )
            )
        return tuple(sorted(discoveries, key=lambda item: item.symbol))


class AutoCandidateSource:
    def __init__(self, *, ttl: timedelta, priority: int) -> None:
        if ttl <= timedelta(0):
            raise ValueError("AUTO candidate ttl must be positive")
        self._ttl = ttl
        self._priority = priority

    def discover(
        self,
        candidates: Iterable[Candidate],
        *,
        observed_at: datetime,
    ) -> tuple[CandidateDiscovery, ...]:
        _require_aware(observed_at, "AUTO observed_at")
        discoveries = []
        for candidate in candidates:
            if CandidateSource.AUTO not in candidate.sources:
                continue
            discoveries.append(
                CandidateDiscovery(
                    symbol=candidate.symbol,
                    source=CandidateSource.AUTO,
                    rank_types=tuple(candidate.matched_rules),
                    best_rank=None,
                    discovered_at=observed_at,
                    expires_at=observed_at + self._ttl,
                    priority=self._priority,
                    evidence={"matched_rules": tuple(candidate.matched_rules)},
                )
            )
        return tuple(sorted(discoveries, key=lambda item: item.symbol))


class ManualCandidateSource:
    def __init__(self, *, priority: int) -> None:
        self._priority = priority

    def discover(
        self,
        symbols: Iterable[str],
        *,
        observed_at: datetime,
    ) -> tuple[CandidateDiscovery, ...]:
        return _permanent_discoveries(
            symbols,
            observed_at=observed_at,
            source=CandidateSource.MANUAL,
            priority=self._priority,
        )


class PositionCandidateSource:
    def __init__(self, *, priority: int) -> None:
        self._priority = priority

    def discover(
        self,
        symbols: Iterable[str],
        *,
        observed_at: datetime,
    ) -> tuple[CandidateDiscovery, ...]:
        return _permanent_discoveries(
            symbols,
            observed_at=observed_at,
            source=CandidateSource.POSITION,
            priority=self._priority,
        )


def _permanent_discoveries(
    symbols: Iterable[str],
    *,
    observed_at: datetime,
    source: CandidateSource,
    priority: int,
) -> tuple[CandidateDiscovery, ...]:
    _require_aware(observed_at, f"{source.value} observed_at")
    normalized = sorted(
        {
            str(symbol).strip().upper()
            for symbol in symbols
            if str(symbol).strip()
        }
    )
    return tuple(
        CandidateDiscovery(
            symbol=symbol,
            source=source,
            rank_types=(),
            best_rank=None,
            discovered_at=observed_at,
            expires_at=None,
            priority=priority,
        )
        for symbol in normalized
    )


def _require_aware(value: datetime, name: str) -> None:
    if value.tzinfo is None:
        raise ValueError(f"{name} must be timezone-aware")


def _freeze_mapping(values: Mapping[str, object]) -> Mapping[str, object]:
    return MappingProxyType(
        {str(key): _freeze_value(value) for key, value in values.items()}
    )


def _freeze_value(value: object) -> object:
    if isinstance(value, Mapping):
        return _freeze_mapping(value)
    if isinstance(value, (list, tuple, set, frozenset)):
        return tuple(_freeze_value(item) for item in value)
    return value
