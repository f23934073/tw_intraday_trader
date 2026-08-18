"""Run an explicit, data-only Shioaji Momentum Shadow session."""

from __future__ import annotations

import argparse
import json
import signal
import sys
from datetime import timedelta
from pathlib import Path
from threading import Event
from time import monotonic

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from candidate.pool import CandidatePool, CandidatePoolConfig
from candidate.sources import ManualCandidateSource, MarketScannerCandidateSource
from config.momentum import QuoteSubscriptionMode, SubscriptionCapacityConfig
from market_data.scanner import ScannerRankType
from market_data.shioaji_momentum_stream import ShioajiMomentumStream
from market_data.subscriptions import SubscriptionManager, SubscriptionPolicy
from runtime.clock import SystemClock
from runtime.momentum_shadow import (
    MomentumShadowRuntime,
    MomentumShadowRuntimeConfig,
    MomentumShadowSnapshot,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run realtime Momentum detection in alert-only Shadow mode. "
            "All capacity and cadence choices are explicit research inputs."
        )
    )
    parser.add_argument(
        "--account-subscription-limit",
        type=int,
        required=True,
    )
    parser.add_argument("--reserved-headroom", type=int, required=True)
    parser.add_argument("--scanner-cadence-seconds", type=float, required=True)
    parser.add_argument("--scanner-count", type=int, required=True)
    parser.add_argument("--candidate-ttl-seconds", type=float, required=True)
    parser.add_argument("--scanner-min-observations", type=int, required=True)
    parser.add_argument("--queue-capacity", type=int, required=True)
    parser.add_argument(
        "--required-stream-max-age-seconds",
        type=float,
        required=True,
    )
    parser.add_argument(
        "--scanner-rank",
        action="append",
        choices=[item.value for item in ScannerRankType],
        required=True,
    )
    parser.add_argument("--manual-symbol", action="append", default=[])
    parser.add_argument("--grace-seconds", type=float, default=30)
    parser.add_argument("--ack-timeout-seconds", type=float, default=5)
    parser.add_argument("--retry-backoff-seconds", type=float, default=5)
    parser.add_argument("--minimum-dwell-seconds", type=float, default=30)
    parser.add_argument("--retention-minutes", type=float, default=20)
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=0,
        help="0 means run until SIGINT/SIGTERM.",
    )
    return parser


def main(argv: list[str] | None = None) -> None:
    args = build_parser().parse_args(argv)
    _validate_args(args)
    clock = SystemClock()
    started_at = clock.now()
    session_id = f"momentum-shadow-{started_at:%Y%m%d-%H%M%S%z}"
    stream = ShioajiMomentumStream.connect_from_env(
        session_id=session_id,
        clock=clock,
    )
    runtime = MomentumShadowRuntime(
        config=MomentumShadowRuntimeConfig(
            version="momentum_shadow_hypothesis_v0",
            session_id=session_id,
            session_date=started_at.date(),
            queue_capacity=args.queue_capacity,
            retention=timedelta(minutes=args.retention_minutes),
            required_stream_max_age=timedelta(
                seconds=args.required_stream_max_age_seconds
            ),
            source_name="shioaji_tick_bidask",
            is_live_source=True,
            aggressor_mapping_verified=False,
        ),
        stream=stream,
        candidate_pool=CandidatePool(
            CandidatePoolConfig(
                version="shadow_candidate_pool_hypothesis_v0",
                grace_period=timedelta(seconds=args.grace_seconds),
                scanner_min_observations=args.scanner_min_observations,
            )
        ),
        subscriptions=SubscriptionManager(
            SubscriptionPolicy(
                version="shadow_tick_bidask_policy_hypothesis_v0",
                capacity=SubscriptionCapacityConfig(
                    account_subscription_limit=(
                        args.account_subscription_limit
                    ),
                    reserved_headroom=args.reserved_headroom,
                    mode=QuoteSubscriptionMode.TICK_BIDASK,
                ),
                ack_timeout=timedelta(seconds=args.ack_timeout_seconds),
                retry_backoff=timedelta(
                    seconds=args.retry_backoff_seconds
                ),
                minimum_dwell=timedelta(
                    seconds=args.minimum_dwell_seconds
                ),
            )
        ),
        clock=clock,
    )
    scanner_source = MarketScannerCandidateSource(
        stream.scanner_client(),
        rank_types=tuple(ScannerRankType(value) for value in args.scanner_rank),
        count_per_rank=args.scanner_count,
        ttl=timedelta(seconds=args.candidate_ttl_seconds),
        priority=30,
        instrument_eligible=lambda symbol: _eligible(stream, symbol, clock),
    )
    manual_source = ManualCandidateSource(priority=100)
    stopped = Event()
    for signal_number in (signal.SIGINT, signal.SIGTERM):
        signal.signal(signal_number, lambda *_: stopped.set())

    started = monotonic()
    next_scan_at = started
    seen_alerts: set[str] = set()
    runtime.start()
    try:
        while not stopped.is_set():
            now_monotonic = monotonic()
            if (
                args.duration_seconds
                and now_monotonic - started >= args.duration_seconds
            ):
                break
            if now_monotonic >= next_scan_at:
                discoveries = list(scanner_source.discover())
                observed_at = clock.now()
                discoveries.extend(
                    manual_source.discover(
                        args.manual_symbol,
                        observed_at=observed_at,
                    )
                )
                runtime.update_candidates(
                    discoveries,
                    evaluated_at=clock.now(),
                )
                _print_json(_status_payload(runtime.snapshot()))
                next_scan_at = now_monotonic + args.scanner_cadence_seconds
            for alert in runtime.pending_alerts():
                if alert.alert_id in seen_alerts:
                    continue
                projection = runtime.projection(alert.symbol)
                if projection is None:
                    continue
                seen_alerts.add(alert.alert_id)
                _print_json(
                    {
                        "type": "momentum_alert",
                        "symbol": alert.symbol,
                        "stage": alert.stage_or_lock_transition,
                        "occurred_at": alert.occurred_at.isoformat(),
                        "signal_family": alert.signal_family.value,
                        "config_version": alert.config_version,
                        "evidence_score": (
                            projection.signal_result.evidence_score
                        ),
                        "evidence_max_score": (
                            projection.signal_result.evidence_max_score
                        ),
                        "entry_status": (
                            projection.entry_opportunity.status.value
                            if projection.entry_opportunity is not None
                            else None
                        ),
                        "disclaimer": (
                            "Evidence Score is rule evidence, not limit-up "
                            "probability or an order instruction."
                        ),
                    }
                )
            stopped.wait(0.25)
    finally:
        runtime.close()
        _print_json(_status_payload(runtime.snapshot()))


def _eligible(
    stream: ShioajiMomentumStream,
    symbol: str,
    clock: SystemClock,
) -> bool:
    try:
        return stream.instrument_reference(
            symbol,
            clock.session_date(),
        ).eligible_for_limit_up_momentum
    except (KeyError, TypeError, ValueError):
        return False


def _status_payload(snapshot: MomentumShadowSnapshot) -> dict[str, object]:
    return {
        "type": "momentum_shadow_status",
        "as_of": snapshot.health.as_of.isoformat(),
        "session_id": snapshot.session_id,
        "source": snapshot.source_name,
        "connection_state": snapshot.connection_state.value,
        "data_health": snapshot.health.state.value,
        "data_health_reasons": [item.value for item in snapshot.health.reasons],
        "discovered": len(snapshot.discovered_symbols),
        "admitted": len(snapshot.admitted_symbols),
        "covered": len(snapshot.covered_symbols),
        "capacity_evicted": len(snapshot.capacity_evicted_symbols),
        "subscriptions_in_use": snapshot.subscriptions_in_use,
        "subscription_max_symbols": snapshot.subscription_max_symbols,
        "queue_depth": snapshot.queue_depth,
        "queue_high_watermark": snapshot.health.queue_high_watermark,
        "queue_overflow_count": snapshot.health.queue_overflow_count,
        "silent_drop_events": snapshot.counters.silent_drop_events,
        "acceleration_signals": snapshot.counters.acceleration_signals,
        "pending_alerts": snapshot.pending_alert_count,
        "miss_reason_counts": {
            reason.value: count
            for reason, count in snapshot.miss_reason_counts
        },
        "runtime_errors": list(snapshot.runtime_errors),
        "adapter_callback_errors": list(snapshot.adapter_callback_errors),
    }


def _validate_args(args: argparse.Namespace) -> None:
    positive = {
        "account_subscription_limit": args.account_subscription_limit,
        "scanner_cadence_seconds": args.scanner_cadence_seconds,
        "scanner_count": args.scanner_count,
        "candidate_ttl_seconds": args.candidate_ttl_seconds,
        "scanner_min_observations": args.scanner_min_observations,
        "queue_capacity": args.queue_capacity,
        "required_stream_max_age_seconds": (
            args.required_stream_max_age_seconds
        ),
        "ack_timeout_seconds": args.ack_timeout_seconds,
        "retention_minutes": args.retention_minutes,
    }
    invalid = [name for name, value in positive.items() if value <= 0]
    if invalid:
        raise ValueError(f"positive arguments required: {','.join(invalid)}")
    if not 1 <= args.scanner_count <= 200:
        raise ValueError("scanner_count must be between 1 and 200")
    non_negative = {
        "reserved_headroom": args.reserved_headroom,
        "grace_seconds": args.grace_seconds,
        "retry_backoff_seconds": args.retry_backoff_seconds,
        "minimum_dwell_seconds": args.minimum_dwell_seconds,
        "duration_seconds": args.duration_seconds,
    }
    invalid = [name for name, value in non_negative.items() if value < 0]
    if invalid:
        raise ValueError(f"non-negative arguments required: {','.join(invalid)}")
    if args.reserved_headroom >= args.account_subscription_limit:
        raise ValueError("reserved_headroom must be below account limit")
    if args.retention_minutes < 20:
        raise ValueError("retention_minutes must be at least 20")


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, sort_keys=True), flush=True)


if __name__ == "__main__":
    main()
