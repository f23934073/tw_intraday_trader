"""PR-007 previous-session adapter and data-only shadow admission gates."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from candidate.models import CandidateSource
from candidate.pool import CandidatePool, CandidatePoolConfig
from candidate.previous_session import (
    PreviousSessionCandidateSourceError,
    PreviousSessionWatchlistCandidateSource,
)
from candidate.shadow_admission import (
    InstitutionalCandidateShadowAdmission,
    InstitutionalShadowAdmissionPolicy,
    ShadowAdmissionError,
    ShadowAdmissionMode,
)
from candidate.sources import CandidateDiscovery, ManualCandidateSource
from config.momentum import QuoteSubscriptionMode, SubscriptionCapacityConfig
from institutional_prior.domain import CandidatePriorArtifact
from market_data.events import InstrumentReference
from market_data.instrument_reference import InstrumentReferenceStore
from tests.test_institutional_candidate_prior import TARGET, _build


TAIPEI = ZoneInfo("Asia/Taipei")


class _MemoryCandidatePriorRepository:
    def __init__(self, artifact: CandidatePriorArtifact) -> None:
        self.artifact = artifact

    def get(self, artifact_id: str) -> CandidatePriorArtifact | None:
        if artifact_id == self.artifact.artifact_id:
            return self.artifact
        return None


def _at(hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 8, 20, hour, minute, tzinfo=TAIPEI)


def _reference(
    symbol: str,
    *,
    session: date = TARGET,
    eligible: bool = True,
) -> InstrumentReference:
    return InstrumentReference(
        symbol=symbol,
        exchange="TSE",
        session_date=session,
        reference_price=Decimal("100"),
        limit_up_price=Decimal("110") if eligible else None,
        limit_down_price=Decimal("90") if eligible else None,
        price_limit_applies=eligible,
        trading_unit_shares=1_000,
        source_updated_at=session if eligible else None,
    )


def _source(
    *,
    eligible_symbols: tuple[str, ...] = ("A001", "C003"),
) -> tuple[
    PreviousSessionWatchlistCandidateSource,
    CandidatePriorArtifact,
    InstrumentReferenceStore,
]:
    artifact = _build()
    references = InstrumentReferenceStore(TARGET)
    for symbol in eligible_symbols:
        references.put(_reference(symbol))
    references.put(_reference("B002", eligible=False))
    return (
        PreviousSessionWatchlistCandidateSource(
            _MemoryCandidatePriorRepository(artifact),
            references,
            priority=25,
        ),
        artifact,
        references,
    )


def _ordinary_discovery(
    symbol: str,
    source: CandidateSource,
    *,
    priority: int,
) -> CandidateDiscovery:
    return CandidateDiscovery(
        symbol=symbol,
        source=source,
        rank_types=(),
        best_rank=None,
        discovered_at=_at(8),
        expires_at=None,
        priority=priority,
    )


def _pool() -> CandidatePool:
    return CandidatePool(
        CandidatePoolConfig(
            version="institutional_shadow_pool_v0",
            grace_period=timedelta(seconds=30),
            scanner_min_observations=1,
        )
    )


def _policy(
    *,
    account_limit: int,
    headroom: int,
    max_institutional: int,
) -> InstitutionalShadowAdmissionPolicy:
    return InstitutionalShadowAdmissionPolicy(
        version="institutional_shadow_admission_v0",
        capacity=SubscriptionCapacityConfig(
            account_subscription_limit=account_limit,
            reserved_headroom=headroom,
            mode=QuoteSubscriptionMode.TICK_BIDASK,
        ),
        max_institutional_candidates=max_institutional,
    )


def test_previous_session_source_projects_only_current_session_eligible_rows() -> None:
    source, artifact, _ = _source()

    batch = source.discover(artifact.artifact_id, expires_at=_at(13, 30))

    assert batch.artifact_id == artifact.artifact_id
    assert batch.target_session == TARGET
    assert batch.source_candidate_count == 3
    assert batch.current_session_eligible_count == 2
    assert batch.current_session_ineligible_symbols == ("B002",)
    assert tuple(item.symbol for item in batch.discoveries) == ("A001", "C003")
    first = batch.discoveries[0]
    assert first.source is CandidateSource.PREVIOUS_SESSION_WATCHLIST
    assert first.best_rank == 1
    assert first.rank_types == (
        "candidate.institutional_foreign_trust_consensus_5d_v0",
        "candidate.institutional_momentum_confirmation_v0",
    )
    assert dict(first.evidence) == {}
    assert first.contribution_ref is not None
    assert first.contribution_ref.artifact_id == artifact.artifact_id
    assert first.contribution_ref.entry_digest == artifact.projections[0].entry_digest
    assert (
        batch.digest
        == source.discover(
            artifact.artifact_id,
            expires_at=_at(13, 30),
        ).digest
    )


def test_previous_session_source_fails_closed_for_missing_or_wrong_session() -> None:
    source, artifact, references = _source()

    with pytest.raises(PreviousSessionCandidateSourceError) as missing:
        source.discover("missing", expires_at=_at(13, 30))
    assert missing.value.code == "CANDIDATE_PRIOR_NOT_FOUND"

    references.begin_session(TARGET + timedelta(days=1))
    with pytest.raises(PreviousSessionCandidateSourceError) as mismatch:
        source.discover(artifact.artifact_id, expires_at=_at(13, 30))
    assert mismatch.value.code == "TARGET_SESSION_MISMATCH"


def test_pool_preserves_previous_session_source_and_bounded_evidence_reference() -> (
    None
):
    source, artifact, _ = _source(eligible_symbols=("A001",))
    batch = source.discover(artifact.artifact_id, expires_at=_at(13, 30))
    manual = ManualCandidateSource(priority=100).discover(
        ("A001",),
        observed_at=_at(8),
    )

    decision = _pool().ingest(
        list(batch.discoveries) + list(manual),
        evaluated_at=_at(8, 5),
    )

    entry = decision.entries[0]
    assert entry.sources == (
        CandidateSource.MANUAL,
        CandidateSource.PREVIOUS_SESSION_WATCHLIST,
    )
    assert CandidateSource.AUTO not in entry.sources
    assert len(entry.contribution_refs) == 1
    assert entry.contribution_refs[0].artifact_id == artifact.artifact_id
    assert entry.contribution_refs[0].entry_digest == (
        artifact.projections[0].entry_digest
    )


def test_shadow_admission_uses_only_residual_capacity_and_institutional_budget() -> (
    None
):
    source, artifact, _ = _source()
    batch = source.discover(artifact.artifact_id, expires_at=_at(13, 30))
    pool = _pool()
    pool_decision = pool.ingest(
        [
            _ordinary_discovery("M001", CandidateSource.MANUAL, priority=100),
            _ordinary_discovery("X001", CandidateSource.AUTO, priority=30),
            *batch.discoveries,
        ],
        evaluated_at=_at(8, 5),
    )

    admission = InstitutionalCandidateShadowAdmission(
        _policy(account_limit=8, headroom=2, max_institutional=1)
    ).evaluate(pool_decision)

    assert admission.mode is ShadowAdmissionMode.SHADOW
    assert admission.subscription_allowed is False
    assert admission.execution_allowed is False
    assert admission.max_symbols == 3
    assert admission.protected_symbols == ("M001",)
    assert admission.base_selected_symbols == ("M001", "X001")
    assert admission.institutional_proposed_symbols == ("A001", "C003")
    assert admission.institutional_admitted_symbols == ("A001",)
    assert admission.institutional_budget_rejected_symbols == ("C003",)
    assert admission.institutional_capacity_rejected_symbols == ()
    assert admission.selected_symbols == ("M001", "X001", "A001")
    assert admission.metrics.selected_symbol_count <= admission.max_symbols
    assert admission.metrics.institutional_admitted_count == 1
    assert not hasattr(admission, "request_symbols")


def test_protected_symbols_consume_capacity_before_institutional_candidates() -> None:
    source, artifact, _ = _source()
    batch = source.discover(artifact.artifact_id, expires_at=_at(13, 30))
    pool_decision = _pool().ingest(
        [
            _ordinary_discovery("M001", CandidateSource.MANUAL, priority=100),
            _ordinary_discovery("P001", CandidateSource.POSITION, priority=200),
            *batch.discoveries,
        ],
        evaluated_at=_at(8, 5),
    )

    admission = InstitutionalCandidateShadowAdmission(
        _policy(account_limit=6, headroom=2, max_institutional=2)
    ).evaluate(pool_decision)

    assert admission.max_symbols == 2
    assert admission.protected_symbols == ("P001", "M001")
    assert admission.institutional_admitted_symbols == ()
    assert admission.institutional_capacity_rejected_symbols == ("A001", "C003")
    assert admission.selected_symbols == ("P001", "M001")


def test_existing_source_overlap_is_traceable_without_incremental_capacity() -> None:
    source, artifact, _ = _source(eligible_symbols=("A001", "C003"))
    batch = source.discover(artifact.artifact_id, expires_at=_at(13, 30))
    pool_decision = _pool().ingest(
        [
            _ordinary_discovery("A001", CandidateSource.MANUAL, priority=100),
            *batch.discoveries,
        ],
        evaluated_at=_at(8, 5),
    )

    admission = InstitutionalCandidateShadowAdmission(
        _policy(account_limit=4, headroom=2, max_institutional=0)
    ).evaluate(pool_decision)

    assert admission.max_symbols == 1
    assert admission.institutional_overlap_symbols == ("A001",)
    assert admission.institutional_admitted_symbols == ()
    assert admission.institutional_budget_rejected_symbols == ("C003",)
    assert admission.selected_symbols == ("A001",)


def test_active_episode_institutional_symbol_is_protected_without_duplication() -> None:
    source, artifact, _ = _source()
    batch = source.discover(artifact.artifact_id, expires_at=_at(13, 30))
    pool_decision = _pool().ingest(
        list(batch.discoveries),
        evaluated_at=_at(8, 5),
        active_episode_symbols=frozenset({"A001"}),
    )

    admission = InstitutionalCandidateShadowAdmission(
        _policy(account_limit=4, headroom=2, max_institutional=1)
    ).evaluate(pool_decision)

    assert admission.max_symbols == 1
    assert admission.protected_symbols == ("A001",)
    assert admission.institutional_overlap_symbols == ("A001",)
    assert admission.institutional_admitted_symbols == ()
    assert admission.institutional_capacity_rejected_symbols == ("C003",)
    assert admission.selected_symbols == ("A001",)


def test_shadow_policy_requires_reviewed_headroom_and_protects_capacity() -> None:
    with pytest.raises(ValueError, match="reviewed provider headroom and mode"):
        InstitutionalShadowAdmissionPolicy(
            version="not-reviewed",
            capacity=SubscriptionCapacityConfig(
                account_subscription_limit=200,
                reserved_headroom=None,
                mode=None,
            ),
            max_institutional_candidates=10,
        )

    pool_decision = _pool().ingest(
        [
            _ordinary_discovery("M001", CandidateSource.MANUAL, priority=100),
            _ordinary_discovery("P001", CandidateSource.POSITION, priority=200),
        ],
        evaluated_at=_at(8, 5),
    )
    evaluator = InstitutionalCandidateShadowAdmission(
        _policy(account_limit=4, headroom=2, max_institutional=0)
    )
    with pytest.raises(ShadowAdmissionError, match="protected symbols"):
        evaluator.evaluate(pool_decision)


def test_shadow_decision_digest_is_deterministic() -> None:
    source, artifact, _ = _source()
    batch = source.discover(artifact.artifact_id, expires_at=_at(13, 30))
    pool_decision = _pool().ingest(
        list(batch.discoveries),
        evaluated_at=_at(8, 5),
    )
    evaluator = InstitutionalCandidateShadowAdmission(
        _policy(account_limit=6, headroom=2, max_institutional=2)
    )

    assert evaluator.evaluate(pool_decision).digest == (
        evaluator.evaluate(pool_decision).digest
    )


def test_shadow_decision_digest_pins_non_actionable_contract() -> None:
    source, artifact, _ = _source()
    batch = source.discover(artifact.artifact_id, expires_at=_at(13, 30))
    decision = InstitutionalCandidateShadowAdmission(
        _policy(account_limit=6, headroom=2, max_institutional=2)
    ).evaluate(_pool().ingest(list(batch.discoveries), evaluated_at=_at(8, 5)))

    assert decision.mode.value == "SHADOW"
    assert decision.subscription_allowed is False
    assert decision.execution_allowed is False
