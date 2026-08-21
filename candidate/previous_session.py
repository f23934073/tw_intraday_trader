"""Adapter from durable Candidate Prior evidence to generic pool discoveries."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime

from candidate.models import CandidateSource
from candidate.sources import CandidateContributionReference, CandidateDiscovery
from institutional_prior.repository import CandidatePriorRepository
from market_data.instrument_reference import InstrumentReferenceStore


class PreviousSessionCandidateSourceError(ValueError):
    """A persisted prior cannot safely enter current-session shadow admission."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(f"{code}: {message}")


@dataclass(frozen=True)
class PreviousSessionCandidateBatch:
    artifact_id: str
    target_session: date
    source_candidate_count: int
    current_session_eligible_count: int
    current_session_ineligible_symbols: tuple[str, ...]
    discoveries: tuple[CandidateDiscovery, ...]

    @property
    def digest(self) -> str:
        payload = {
            "artifact_id": self.artifact_id,
            "target_session": self.target_session.isoformat(),
            "source_candidate_count": self.source_candidate_count,
            "current_session_eligible_count": self.current_session_eligible_count,
            "current_session_ineligible_symbols": list(
                self.current_session_ineligible_symbols
            ),
            "discoveries": [
                {
                    "symbol": item.symbol,
                    "source": item.source.value,
                    "rank_types": list(item.rank_types),
                    "best_rank": item.best_rank,
                    "discovered_at": item.discovered_at.isoformat(),
                    "expires_at": (
                        item.expires_at.isoformat()
                        if item.expires_at is not None
                        else None
                    ),
                    "priority": item.priority,
                    "artifact_id": (
                        item.contribution_ref.artifact_id
                        if item.contribution_ref is not None
                        else None
                    ),
                    "entry_digest": (
                        item.contribution_ref.entry_digest
                        if item.contribution_ref is not None
                        else None
                    ),
                }
                for item in self.discoveries
            ],
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()


class PreviousSessionWatchlistCandidateSource:
    """Translate one frozen prior without exposing institutional calculations."""

    def __init__(
        self,
        repository: CandidatePriorRepository,
        instrument_references: InstrumentReferenceStore,
        *,
        priority: int,
    ) -> None:
        self._repository = repository
        self._instrument_references = instrument_references
        self._priority = priority

    def discover(
        self,
        artifact_id: str,
        *,
        expires_at: datetime,
    ) -> PreviousSessionCandidateBatch:
        if expires_at.tzinfo is None or expires_at.utcoffset() is None:
            raise PreviousSessionCandidateSourceError(
                "RUNTIME_EXPIRY_INVALID",
                "expires_at must be timezone-aware",
            )
        artifact = self._repository.get(artifact_id.strip())
        if artifact is None:
            raise PreviousSessionCandidateSourceError(
                "CANDIDATE_PRIOR_NOT_FOUND",
                "Candidate Prior artifact does not exist",
            )

        run = artifact.manifest.run
        target_session = self._instrument_references.session_date
        if run.target_session != target_session:
            raise PreviousSessionCandidateSourceError(
                "TARGET_SESSION_MISMATCH",
                "Candidate Prior target differs from current instrument session",
            )
        if expires_at <= run.generated_at:
            raise PreviousSessionCandidateSourceError(
                "RUNTIME_EXPIRY_INVALID",
                "expires_at must be after prior generation",
            )
        if expires_at.astimezone(run.generated_at.tzinfo).date() != target_session:
            raise PreviousSessionCandidateSourceError(
                "RUNTIME_EXPIRY_SESSION_MISMATCH",
                "expires_at must belong to the Candidate Prior target session",
            )
        if (
            artifact.manifest.strategy_ready
            or artifact.manifest.production_ready
            or artifact.manifest.live_admission_ready
            or artifact.manifest.execution_allowed
        ):
            raise PreviousSessionCandidateSourceError(
                "SHADOW_BOUNDARY_VIOLATION",
                "Candidate Prior claims actionability outside data-only shadow scope",
            )

        discoveries: list[CandidateDiscovery] = []
        ineligible: list[str] = []
        for projection in sorted(
            artifact.projections,
            key=lambda item: (item.candidate_rank, item.market.value, item.symbol),
        ):
            if not self._instrument_references.eligible(projection.symbol):
                ineligible.append(projection.symbol)
                continue
            discoveries.append(
                CandidateDiscovery(
                    symbol=projection.symbol,
                    source=CandidateSource.PREVIOUS_SESSION_WATCHLIST,
                    rank_types=tuple(
                        hypothesis.value for hypothesis in projection.matched_hypotheses
                    ),
                    best_rank=projection.candidate_rank,
                    discovered_at=run.generated_at,
                    expires_at=expires_at,
                    priority=self._priority,
                    contribution_ref=CandidateContributionReference(
                        source=CandidateSource.PREVIOUS_SESSION_WATCHLIST,
                        artifact_id=projection.artifact_id,
                        entry_digest=projection.entry_digest,
                    ),
                )
            )

        return PreviousSessionCandidateBatch(
            artifact_id=artifact.artifact_id,
            target_session=target_session,
            source_candidate_count=len(artifact.projections),
            current_session_eligible_count=len(discoveries),
            current_session_ineligible_symbols=tuple(sorted(ineligible)),
            discoveries=tuple(discoveries),
        )
