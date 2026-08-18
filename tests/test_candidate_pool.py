"""CandidatePool union, TTL, and hysteresis tests."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from candidate.models import CandidateSource
from candidate.pool import CandidatePool, CandidatePoolConfig
from candidate.sources import CandidateDiscovery


TAIPEI = ZoneInfo("Asia/Taipei")


def at(minute: int, second: int = 0) -> datetime:
    return datetime(2026, 8, 18, 9, minute, second, tzinfo=TAIPEI)


def discovery(
    symbol: str,
    source: CandidateSource,
    minute: int,
    *,
    ttl_seconds: int | None = 60,
    priority: int = 30,
    best_rank: int | None = 1,
) -> CandidateDiscovery:
    observed_at = at(minute)
    return CandidateDiscovery(
        symbol=symbol,
        source=source,
        rank_types=("VOLUME",) if source is CandidateSource.SCANNER else (),
        best_rank=best_rank,
        discovered_at=observed_at,
        expires_at=(
            observed_at + timedelta(seconds=ttl_seconds)
            if ttl_seconds is not None
            else None
        ),
        priority=priority,
    )


def pool() -> CandidatePool:
    return CandidatePool(
        CandidatePoolConfig(
            version="candidate_pool_test_v0",
            grace_period=timedelta(seconds=30),
            scanner_min_observations=2,
        )
    )


def test_scanner_requires_repeated_observation_before_admission():
    candidate_pool = pool()

    first = candidate_pool.ingest(
        [discovery("8039", CandidateSource.SCANNER, 0)],
        evaluated_at=at(0),
    )
    duplicate = candidate_pool.ingest(
        [discovery("8039", CandidateSource.SCANNER, 0)],
        evaluated_at=at(0, 10),
    )
    second = candidate_pool.ingest(
        [discovery("8039", CandidateSource.SCANNER, 1)],
        evaluated_at=at(1),
    )

    assert first.pending_symbols == ("8039",)
    assert duplicate.entries[0].scanner_observations == 1
    assert second.admitted_symbols == ("8039",)
    assert second.entries[0].scanner_observations == 2


def test_ttl_grace_keeps_candidate_then_expires_it():
    candidate_pool = pool()
    candidate_pool.ingest(
        [discovery("8039", CandidateSource.AUTO, 0)],
        evaluated_at=at(0),
    )

    in_grace = candidate_pool.evaluate(evaluated_at=at(1, 15))
    expired = candidate_pool.evaluate(evaluated_at=at(1, 31))
    already_expired = candidate_pool.evaluate(evaluated_at=at(2))

    assert in_grace.admitted_symbols == ("8039",)
    assert in_grace.entries[0].in_grace is True
    assert expired.entries == ()
    assert expired.expired_symbols == ("8039",)
    assert already_expired.expired_symbols == ()


def test_manual_and_position_sources_are_pinned_and_union_with_scanner():
    candidate_pool = pool()
    decision = candidate_pool.ingest(
        [
            discovery("8039", CandidateSource.SCANNER, 0),
            discovery(
                "8039",
                CandidateSource.MANUAL,
                0,
                ttl_seconds=None,
                priority=100,
                best_rank=None,
            ),
            discovery(
                "2454",
                CandidateSource.POSITION,
                0,
                ttl_seconds=None,
                priority=200,
                best_rank=None,
            ),
        ],
        evaluated_at=at(0),
    )
    by_symbol = {entry.symbol: entry for entry in decision.entries}

    assert by_symbol["8039"].sources == (
        CandidateSource.MANUAL,
        CandidateSource.SCANNER,
    )
    assert by_symbol["8039"].admitted is True
    assert by_symbol["8039"].pinned is True
    assert by_symbol["2454"].protected is True


def test_active_episode_protects_an_expired_discovery_without_faking_source():
    candidate_pool = pool()
    candidate_pool.ingest(
        [discovery("8039", CandidateSource.AUTO, 0)],
        evaluated_at=at(0),
    )

    protected = candidate_pool.evaluate(
        evaluated_at=at(2),
        active_episode_symbols=frozenset({"8039"}),
    )

    assert protected.entries[0].active_episode is True
    assert protected.entries[0].protected is True
    assert protected.entries[0].sources == (CandidateSource.AUTO,)


def test_withdrawing_manual_source_leaves_scanner_pending():
    candidate_pool = pool()
    candidate_pool.ingest(
        [
            discovery("8039", CandidateSource.SCANNER, 0),
            discovery(
                "8039",
                CandidateSource.MANUAL,
                0,
                ttl_seconds=None,
                priority=100,
                best_rank=None,
            ),
        ],
        evaluated_at=at(0),
    )

    decision = candidate_pool.withdraw(
        "8039",
        CandidateSource.MANUAL,
        evaluated_at=at(0, 10),
    )

    assert decision.pending_symbols == ("8039",)
    assert decision.entries[0].pinned is False


def test_candidate_pool_decision_digest_replays_identically():
    def run_once() -> str:
        candidate_pool = pool()
        candidate_pool.ingest(
            [discovery("8039", CandidateSource.SCANNER, 0)],
            evaluated_at=at(0),
        )
        return candidate_pool.ingest(
            [
                discovery("8039", CandidateSource.SCANNER, 1),
                discovery("2330", CandidateSource.AUTO, 1, priority=10),
            ],
            evaluated_at=at(1),
        ).digest

    assert run_once() == run_once()
