"""Deterministic CandidatePool with TTL, grace, and admission hysteresis."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timedelta

from candidate.models import CandidateSource
from candidate.sources import CandidateDiscovery


@dataclass(frozen=True)
class CandidatePoolConfig:
    version: str
    grace_period: timedelta
    scanner_min_observations: int

    def __post_init__(self) -> None:
        if not self.version.strip():
            raise ValueError("CandidatePool config version must not be empty")
        if self.grace_period < timedelta(0):
            raise ValueError("CandidatePool grace_period cannot be negative")
        if self.scanner_min_observations <= 0:
            raise ValueError("scanner_min_observations must be positive")


@dataclass(frozen=True)
class CandidatePoolEntry:
    symbol: str
    sources: tuple[CandidateSource, ...]
    rank_types: tuple[str, ...]
    best_rank: int | None
    first_discovered_at: datetime
    last_discovered_at: datetime
    expires_at: datetime | None
    priority: int
    scanner_observations: int
    admitted: bool
    in_grace: bool
    pinned: bool
    active_episode: bool

    @property
    def protected(self) -> bool:
        return self.pinned or self.active_episode

    def selection_key(self) -> tuple[object, ...]:
        return (
            0 if self.protected else 1,
            -self.priority,
            self.best_rank if self.best_rank is not None else 2**31,
            1 if self.in_grace else 0,
            -self.last_discovered_at.timestamp(),
            self.symbol,
        )


@dataclass(frozen=True)
class CandidatePoolDecision:
    evaluated_at: datetime
    config_version: str
    entries: tuple[CandidatePoolEntry, ...]
    admitted_symbols: tuple[str, ...]
    pending_symbols: tuple[str, ...]
    expired_symbols: tuple[str, ...]

    @property
    def digest(self) -> str:
        payload = {
            "evaluated_at": self.evaluated_at.isoformat(),
            "config_version": self.config_version,
            "entries": [
                {
                    "symbol": entry.symbol,
                    "sources": [source.value for source in entry.sources],
                    "rank_types": list(entry.rank_types),
                    "best_rank": entry.best_rank,
                    "first_discovered_at": entry.first_discovered_at.isoformat(),
                    "last_discovered_at": entry.last_discovered_at.isoformat(),
                    "expires_at": (
                        entry.expires_at.isoformat()
                        if entry.expires_at is not None
                        else None
                    ),
                    "priority": entry.priority,
                    "scanner_observations": entry.scanner_observations,
                    "admitted": entry.admitted,
                    "in_grace": entry.in_grace,
                    "pinned": entry.pinned,
                    "active_episode": entry.active_episode,
                }
                for entry in self.entries
            ],
            "admitted_symbols": list(self.admitted_symbols),
            "pending_symbols": list(self.pending_symbols),
            "expired_symbols": list(self.expired_symbols),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


@dataclass
class _Contribution:
    discovery: CandidateDiscovery
    first_discovered_at: datetime
    last_discovered_at: datetime
    observation_count: int


class CandidatePool:
    """Merge source contributions without turning discovery into a signal."""

    _PINNED_SOURCES = frozenset(
        {CandidateSource.MANUAL, CandidateSource.POSITION}
    )

    def __init__(self, config: CandidatePoolConfig) -> None:
        self.config = config
        self._contributions: dict[tuple[str, CandidateSource], _Contribution] = {}
        self._visible_symbols: set[str] = set()
        self._decisions: list[CandidatePoolDecision] = []

    @property
    def decisions(self) -> tuple[CandidatePoolDecision, ...]:
        return tuple(self._decisions)

    def ingest(
        self,
        discoveries: tuple[CandidateDiscovery, ...] | list[CandidateDiscovery],
        *,
        evaluated_at: datetime,
        active_episode_symbols: frozenset[str] = frozenset(),
    ) -> CandidatePoolDecision:
        self._require_aware(evaluated_at)
        for discovery in sorted(
            discoveries,
            key=lambda item: (item.discovered_at, item.symbol, item.source.value),
        ):
            if discovery.discovered_at > evaluated_at:
                raise ValueError("candidate discovery cannot be in the future")
            key = (discovery.symbol, discovery.source)
            previous = self._contributions.get(key)
            if previous is not None and discovery.discovered_at <= previous.last_discovered_at:
                continue

            observation_count = 1
            first_discovered_at = discovery.discovered_at
            if previous is not None:
                expired_before_new = (
                    previous.discovery.expires_at is not None
                    and discovery.discovered_at
                    > previous.discovery.expires_at + self.config.grace_period
                )
                if not expired_before_new:
                    observation_count = previous.observation_count + 1
                    first_discovered_at = previous.first_discovered_at

            self._contributions[key] = _Contribution(
                discovery=discovery,
                first_discovered_at=first_discovered_at,
                last_discovered_at=discovery.discovered_at,
                observation_count=observation_count,
            )

        return self.evaluate(
            evaluated_at=evaluated_at,
            active_episode_symbols=active_episode_symbols,
        )

    def withdraw(
        self,
        symbol: str,
        source: CandidateSource,
        *,
        evaluated_at: datetime,
        active_episode_symbols: frozenset[str] = frozenset(),
    ) -> CandidatePoolDecision:
        self._require_aware(evaluated_at)
        normalized = symbol.strip().upper()
        self._contributions.pop((normalized, source), None)
        return self.evaluate(
            evaluated_at=evaluated_at,
            active_episode_symbols=active_episode_symbols,
        )

    def evaluate(
        self,
        *,
        evaluated_at: datetime,
        active_episode_symbols: frozenset[str] = frozenset(),
    ) -> CandidatePoolDecision:
        self._require_aware(evaluated_at)
        active = {
            str(symbol).strip().upper()
            for symbol in active_episode_symbols
            if str(symbol).strip()
        }
        grouped: dict[str, list[_Contribution]] = {}
        removable: list[tuple[str, CandidateSource]] = []

        for key, contribution in self._contributions.items():
            expires_at = contribution.discovery.expires_at
            visible = (
                expires_at is None
                or evaluated_at <= expires_at + self.config.grace_period
                or contribution.discovery.symbol in active
            )
            if visible:
                grouped.setdefault(contribution.discovery.symbol, []).append(contribution)
            else:
                removable.append(key)

        entries = tuple(
            sorted(
                (
                    self._build_entry(symbol, values, evaluated_at, active)
                    for symbol, values in grouped.items()
                ),
                key=CandidatePoolEntry.selection_key,
            )
        )
        visible_symbols = {entry.symbol for entry in entries}
        expired_symbols = tuple(sorted(self._visible_symbols - visible_symbols))
        self._visible_symbols = visible_symbols
        for key in removable:
            self._contributions.pop(key, None)

        decision = CandidatePoolDecision(
            evaluated_at=evaluated_at,
            config_version=self.config.version,
            entries=entries,
            admitted_symbols=tuple(
                entry.symbol for entry in entries if entry.admitted
            ),
            pending_symbols=tuple(
                entry.symbol for entry in entries if not entry.admitted
            ),
            expired_symbols=expired_symbols,
        )
        self._decisions.append(decision)
        return decision

    def _build_entry(
        self,
        symbol: str,
        contributions: list[_Contribution],
        evaluated_at: datetime,
        active_episode_symbols: set[str],
    ) -> CandidatePoolEntry:
        sources = tuple(
            sorted(
                {item.discovery.source for item in contributions},
                key=lambda source: source.value,
            )
        )
        rank_types = tuple(
            sorted(
                {
                    rank_type
                    for item in contributions
                    for rank_type in item.discovery.rank_types
                }
            )
        )
        ranks = [
            item.discovery.best_rank
            for item in contributions
            if item.discovery.best_rank is not None
        ]
        scanner_observations = max(
            (
                item.observation_count
                for item in contributions
                if item.discovery.source is CandidateSource.SCANNER
            ),
            default=0,
        )
        pinned = any(source in self._PINNED_SOURCES for source in sources)
        active_episode = symbol in active_episode_symbols
        immediate_source = any(
            source is not CandidateSource.SCANNER for source in sources
        )
        admitted = (
            pinned
            or active_episode
            or immediate_source
            or scanner_observations >= self.config.scanner_min_observations
        )
        expiring = [
            item.discovery.expires_at
            for item in contributions
            if item.discovery.expires_at is not None
        ]
        permanent = any(
            item.discovery.expires_at is None for item in contributions
        )
        in_grace = (
            not permanent
            and bool(expiring)
            and all(evaluated_at > value for value in expiring)
        )
        return CandidatePoolEntry(
            symbol=symbol,
            sources=sources,
            rank_types=rank_types,
            best_rank=min(ranks) if ranks else None,
            first_discovered_at=min(
                item.first_discovered_at for item in contributions
            ),
            last_discovered_at=max(
                item.last_discovered_at for item in contributions
            ),
            expires_at=None if permanent else max(expiring),
            priority=max(item.discovery.priority for item in contributions),
            scanner_observations=scanner_observations,
            admitted=admitted,
            in_grace=in_grace,
            pinned=pinned,
            active_episode=active_episode,
        )

    @staticmethod
    def _require_aware(value: datetime) -> None:
        if value.tzinfo is None:
            raise ValueError("CandidatePool evaluated_at must be timezone-aware")
