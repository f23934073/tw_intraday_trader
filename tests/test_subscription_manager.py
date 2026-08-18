"""Deterministic capacity and subscription lifecycle tests."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest

from candidate.models import CandidateSource
from candidate.pool import CandidatePoolEntry
from config.momentum import QuoteSubscriptionMode, SubscriptionCapacityConfig
from market_data.subscriptions import (
    MissReason,
    ProtectedCapacityError,
    SubscriptionManager,
    SubscriptionPolicy,
    SubscriptionState,
)


TAIPEI = ZoneInfo("Asia/Taipei")


def at(second: int) -> datetime:
    return datetime(2026, 8, 18, 9, 0, second, tzinfo=TAIPEI)


def entry(
    symbol: str,
    *,
    priority: int,
    rank: int | None = None,
    pinned: bool = False,
    active_episode: bool = False,
) -> CandidatePoolEntry:
    source = CandidateSource.MANUAL if pinned else CandidateSource.SCANNER
    return CandidatePoolEntry(
        symbol=symbol,
        sources=(source,),
        rank_types=("VOLUME",),
        best_rank=rank,
        first_discovered_at=at(0),
        last_discovered_at=at(0),
        expires_at=None if pinned else at(30),
        priority=priority,
        scanner_observations=2,
        admitted=True,
        in_grace=False,
        pinned=pinned,
        active_episode=active_episode,
    )


def policy(
    *,
    account_limit: int = 4,
    headroom: int = 0,
    mode: QuoteSubscriptionMode = QuoteSubscriptionMode.QUOTE,
    minimum_dwell: timedelta = timedelta(0),
) -> SubscriptionPolicy:
    return SubscriptionPolicy(
        version="subscription_policy_test_v0",
        capacity=SubscriptionCapacityConfig(
            account_subscription_limit=account_limit,
            reserved_headroom=headroom,
            mode=mode,
        ),
        ack_timeout=timedelta(seconds=5),
        retry_backoff=timedelta(seconds=2),
        minimum_dwell=minimum_dwell,
    )


def test_policy_fails_closed_without_reviewed_headroom_and_mode():
    with pytest.raises(ValueError, match="reviewed headroom and mode"):
        SubscriptionPolicy(
            version="not-ready",
            capacity=SubscriptionCapacityConfig(
                account_subscription_limit=200,
                reserved_headroom=None,
                mode=None,
            ),
            ack_timeout=timedelta(seconds=5),
            retry_backoff=timedelta(seconds=1),
            minimum_dwell=timedelta(0),
        )


def test_capacity_formula_and_eviction_never_exceed_subscription_limit():
    manager = SubscriptionManager(
        policy(
            account_limit=6,
            headroom=2,
            mode=QuoteSubscriptionMode.TICK_BIDASK,
        )
    )
    candidates = [
        entry(f"{index:04d}", priority=index, rank=10 - index)
        for index in range(1, 6)
    ]

    decision = manager.reconcile(candidates, evaluated_at=at(0))

    assert decision.max_symbols == 2
    assert decision.desired_symbols == ("0005", "0004")
    assert decision.capacity_evicted_symbols == ("0001", "0002", "0003")
    assert manager.subscriptions_in_use == 4
    assert manager.subscriptions_in_use <= 6 - 2


def test_only_provider_acked_symbols_count_as_coverage():
    manager = SubscriptionManager(policy(account_limit=1))
    decision = manager.reconcile(
        [entry("8039", priority=30)],
        evaluated_at=at(0),
    )

    assert decision.request_symbols == ("8039",)
    assert manager.covered_symbols == frozenset()

    manager.ack_subscribe("8039", occurred_at=at(1))

    assert manager.covered_symbols == frozenset({"8039"})
    assert manager.records[0].acked_at == at(1)


def test_partial_subscribe_rollback_keeps_capacity_until_unsubscribe_ack():
    manager = SubscriptionManager(policy(account_limit=1))
    manager.reconcile([entry("8039", priority=30)], evaluated_at=at(0))

    manager.begin_subscribe_rollback(
        "8039",
        occurred_at=at(1),
        reason="paired_stream_partial_failure",
    )

    assert manager.consuming_symbols == frozenset({"8039"})
    assert manager.records[0].state is SubscriptionState.UNSUBSCRIBE_REQUESTED
    assert manager.subscriptions_in_use == 1

    manager.ack_unsubscribe("8039", occurred_at=at(2))
    assert manager.consuming_symbols == frozenset()


def test_replacement_waits_for_unsubscribe_ack_before_using_capacity():
    manager = SubscriptionManager(policy(account_limit=1))
    manager.reconcile([entry("A", priority=10)], evaluated_at=at(0))
    manager.ack_subscribe("A", occurred_at=at(1))

    replacing = manager.reconcile(
        [entry("B", priority=100)],
        evaluated_at=at(2),
    )

    assert replacing.unsubscribe_symbols == ("A",)
    assert replacing.request_symbols == ()
    assert replacing.deferred_symbols == ("B",)
    assert manager.consuming_symbols == frozenset({"A"})

    manager.ack_unsubscribe("A", occurred_at=at(3))
    requested = manager.reconcile(
        [entry("B", priority=100)],
        evaluated_at=at(4),
    )

    assert requested.request_symbols == ("B",)
    assert manager.consuming_symbols == frozenset({"B"})


def test_minimum_dwell_prevents_small_rank_churn_then_allows_replacement():
    manager = SubscriptionManager(
        policy(account_limit=1, minimum_dwell=timedelta(seconds=10))
    )
    manager.reconcile([entry("A", priority=10)], evaluated_at=at(0))
    manager.ack_subscribe("A", occurred_at=at(1))

    sticky = manager.reconcile(
        [entry("A", priority=10), entry("B", priority=100)],
        evaluated_at=at(5),
    )
    after_dwell = manager.reconcile(
        [entry("A", priority=10), entry("B", priority=100)],
        evaluated_at=at(11),
    )

    assert sticky.desired_symbols == ("A",)
    assert sticky.capacity_evicted_symbols == ("B",)
    assert after_dwell.desired_symbols == ("B",)
    assert after_dwell.unsubscribe_symbols == ("A",)


def test_pinned_and_active_episode_candidates_cannot_be_evicted():
    manager = SubscriptionManager(policy(account_limit=1))

    with pytest.raises(ProtectedCapacityError, match="protected symbols"):
        manager.reconcile(
            [
                entry("8039", priority=1, pinned=True),
                entry("2454", priority=1, active_episode=True),
            ],
            evaluated_at=at(0),
            active_episode_symbols=frozenset({"2454"}),
        )

    assert manager.records == ()


def test_ack_timeout_is_not_coverage_and_still_consumes_capacity():
    manager = SubscriptionManager(policy(account_limit=1))
    candidates = [entry("8039", priority=30)]
    manager.reconcile(candidates, evaluated_at=at(0))

    timed_out = manager.reconcile(candidates, evaluated_at=at(5))

    assert manager.records[0].state is SubscriptionState.ACK_TIMEOUT
    assert timed_out.covered_symbols == ()
    assert manager.consuming_symbols == frozenset({"8039"})
    assert manager.classify_miss(
        "8039",
        discovered_symbols=frozenset({"8039"}),
        admitted_symbols=frozenset({"8039"}),
        capacity_evicted_symbols=frozenset(),
        data_complete=True,
        signal_emitted=False,
    ) is MissReason.SUBSCRIPTION_NOT_ACKED

    manager.ack_subscribe("8039", occurred_at=at(6))
    assert manager.covered_symbols == frozenset({"8039"})


def test_disconnect_releases_confirmed_connection_capacity_and_reconciles():
    manager = SubscriptionManager(policy(account_limit=1))
    candidates = [entry("8039", priority=30)]
    manager.reconcile(candidates, evaluated_at=at(0))
    manager.ack_subscribe("8039", occurred_at=at(1))

    manager.mark_disconnected(occurred_at=at(2))
    replayed = manager.reconcile(candidates, evaluated_at=at(3))

    assert replayed.request_symbols == ("8039",)
    assert manager.covered_symbols == frozenset()
    assert manager.records[0].attempts == 2


def test_failed_unsubscribe_retries_after_backoff_without_freeing_capacity():
    manager = SubscriptionManager(policy(account_limit=1))
    manager.reconcile([entry("A", priority=10)], evaluated_at=at(0))
    manager.ack_subscribe("A", occurred_at=at(1))
    manager.reconcile([entry("B", priority=100)], evaluated_at=at(2))
    manager.fail_unsubscribe("A", occurred_at=at(3), reason="provider_error")

    before_backoff = manager.reconcile(
        [entry("B", priority=100)],
        evaluated_at=at(4),
    )
    retried = manager.reconcile(
        [entry("B", priority=100)],
        evaluated_at=at(5),
    )

    assert before_backoff.unsubscribe_symbols == ()
    assert before_backoff.request_symbols == ()
    assert retried.unsubscribe_symbols == ("A",)
    assert retried.request_symbols == ()
    assert manager.consuming_symbols == frozenset({"A"})


def test_subscription_transitions_reject_backward_timestamps():
    manager = SubscriptionManager(policy(account_limit=1))
    manager.reconcile([entry("8039", priority=30)], evaluated_at=at(2))

    with pytest.raises(ValueError, match="backward in time"):
        manager.ack_subscribe("8039", occurred_at=at(1))


def test_missed_reason_funnel_preserves_failure_stage():
    manager = SubscriptionManager(policy(account_limit=1))
    manager.reconcile([entry("8039", priority=30)], evaluated_at=at(0))
    manager.ack_subscribe("8039", occurred_at=at(1))

    common = {
        "discovered_symbols": frozenset({"8039", "2454", "2330"}),
        "admitted_symbols": frozenset({"8039", "2454"}),
        "capacity_evicted_symbols": frozenset({"2454"}),
    }
    assert manager.classify_miss(
        "9999",
        **common,
        data_complete=False,
        signal_emitted=False,
    ) is MissReason.NOT_DISCOVERED
    assert manager.classify_miss(
        "2330",
        **common,
        data_complete=False,
        signal_emitted=False,
    ) is MissReason.ADMISSION_PENDING
    assert manager.classify_miss(
        "2454",
        **common,
        data_complete=False,
        signal_emitted=False,
    ) is MissReason.CAPACITY_EVICTED
    assert manager.classify_miss(
        "8039",
        **common,
        data_complete=False,
        signal_emitted=False,
    ) is MissReason.DATA_INCOMPLETE
    assert manager.classify_miss(
        "8039",
        **common,
        data_complete=True,
        signal_emitted=False,
    ) is MissReason.SIGNAL_FALSE
    assert manager.classify_miss(
        "8039",
        **common,
        data_complete=True,
        signal_emitted=True,
    ) is None


def test_subscription_decision_digest_replays_identically():
    candidates = [
        entry("8039", priority=30, rank=1),
        entry("2330", priority=20, rank=2),
    ]

    def run_once() -> str:
        manager = SubscriptionManager(policy(account_limit=1))
        return manager.reconcile(candidates, evaluated_at=at(0)).digest

    assert run_once() == run_once()
