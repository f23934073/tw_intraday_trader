from __future__ import annotations

from datetime import datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

import backtest.atomic_benchmark.domain as benchmark_domain

from atomic_strategies.registry import AtomicStrategyRegistry
from backtest.atomic_benchmark.domain import (
    ALGORITHM_CONTRACT_DIGEST,
    ALGORITHM_CONTRACT_DIGEST_V1,
    COST_IDENTITY_DIGEST,
    AtomicBenchmarkIntegrityError,
    FirstTriggerAdmission,
    ObservedBar,
    _daily_equal_signal_max_drawdown,
    build_episode,
    build_match_plan,
    build_slot_binding,
    build_summary,
    build_version_binding,
    canonical_object_bytes,
    compare_layers,
    verify_episode_row,
    verify_ledger_row,
)
from backtest.domain import HistoricalBar, canonical_json
from scripts.publish_r6_g1_strategy_versions import FROZEN_ADMISSIONS, _verify_frozen


TAIPEI = ZoneInfo("Asia/Taipei")
SHA = "a" * 64


def _bar(
    at: str,
    *,
    symbol: str = "2330",
    open_price: str = "100",
    close: str = "100",
) -> ObservedBar:
    timestamp = datetime.fromisoformat(at).replace(tzinfo=TAIPEI)
    low = min(Decimal(open_price), Decimal(close))
    high = max(Decimal(open_price), Decimal(close))
    bar = HistoricalBar(
        symbol=symbol,
        timestamp=timestamp,
        open=Decimal(open_price),
        high=high,
        low=low,
        close=Decimal(close),
        volume=1000,
        session_date=timestamp.date(),
    )
    return ObservedBar(
        bar=bar,
        source_json=canonical_json(bar.to_dict()).encode("utf-8"),
    )


def _admit(
    owner: FirstTriggerAdmission,
    source_bar: ObservedBar,
    *,
    slot: int = 1,
    status: str = "TRIGGERED",
) -> dict | None:
    return owner.consider(
        matrix_id="r6-matrix-test",
        registration_digest=SHA,
        slot_sequence=slot,
        hypothesis_id=SHA,
        strategy_id="breakout_previous_high_entry",
        strategy_version_id="version-1",
        strategy_configuration_digest=SHA,
        strategy_implementation_digest=SHA,
        feature_request_identity_digest=SHA,
        source_bar=source_bar,
        evaluation_status=status,
        evaluation_document={"observed": {"price": "100"}, "threshold": {"price": "99"}},
        feature_input_evidence={"input_digest": SHA},
    )


def _one_episode(*, entry: str = "100", exit_price: str = "102"):
    owner = FirstTriggerAdmission()
    signal_bar = _bar("2026-01-05T09:01:00", close="100")
    signal = _admit(owner, signal_bar)
    assert signal is not None
    bars = (
        signal_bar,
        _bar("2026-01-05T09:02:00", open_price=entry, close=entry),
        _bar("2026-01-05T13:30:00", open_price=exit_price, close=exit_price),
    )
    match = build_match_plan(ledger_rows=(signal,), bars=bars)
    assert match.missing_entry_count == match.missing_exit_count == 0
    return signal, match, build_episode(match.rows[0])


def _positive_screen_episodes() -> tuple[dict, ...]:
    sessions = [datetime(2023, 10, day, tzinfo=TAIPEI) for day in range(1, 21)]
    sessions.extend(
        datetime.fromisoformat(value).replace(tzinfo=TAIPEI)
        for value in (
            "2024-01-02",
            "2024-04-02",
            "2024-07-02",
            "2024-10-02",
            "2025-01-02",
            "2025-04-02",
            "2025-07-02",
            "2025-10-02",
            "2026-01-02",
            "2026-04-02",
        )
    )
    owner = FirstTriggerAdmission()
    signals = []
    bars = []
    for session in sessions:
        day = session.date().isoformat()
        signal_bar = _bar(f"{day}T09:01:00", close="100")
        signal = _admit(owner, signal_bar)
        assert signal is not None
        signals.append(signal)
        bars.extend(
            (
                signal_bar,
                _bar(f"{day}T09:02:00", open_price="100", close="100"),
                _bar(f"{day}T13:30:00", open_price="102", close="102"),
            )
        )
    match = build_match_plan(ledger_rows=signals, bars=bars)
    return tuple(build_episode(row) for row in match.rows)


def test_frozen_algorithm_and_cost_digests() -> None:
    assert ALGORITHM_CONTRACT_DIGEST == "d0d3b66395a06f600c698bad7890ad39f2dceec2963727814e5d3198643df0b6"
    assert ALGORITHM_CONTRACT_DIGEST_V1 == "ab68f293290ca9e0263c4381ad0984133773f28112c636fe5def6db27210a200"
    assert COST_IDENTITY_DIGEST == "487aed133395c7e4b4dec814de80166ebaa1bf67d98a0e399a945389aea0baf7"


def test_version_and_slot_binding_rebuild_lifecycle_projection() -> None:
    event_id = "event-1"
    version_id = "version-1"
    projection = __import__("hashlib").sha256(
        canonical_json(
            {
                "strategy_version_id": version_id,
                "status": "PUBLISHED",
                "last_sequence": 1,
                "last_event_id": event_id,
            }
        ).encode()
    ).hexdigest()
    binding = build_version_binding(
        hypothesis_spec_digest=SHA,
        strategy_version_id=version_id,
        version_number=1,
        strategy_configuration_digest=SHA,
        lifecycle_status="PUBLISHED",
        lifecycle_sequence=1,
        lifecycle_event_id=event_id,
        lifecycle_projection_digest=projection,
    )
    slot = build_slot_binding(
        slot_sequence=1,
        hypothesis_spec_digest=SHA,
        version_binding=binding,
    )
    assert slot["slot_sequence"] == 1
    assert len(slot["hypothesis_id"]) == 64


def test_version_binding_rejects_non_published_lifecycle() -> None:
    with pytest.raises(AtomicBenchmarkIntegrityError, match="PUBLISHED"):
        build_version_binding(
            hypothesis_spec_digest=SHA,
            strategy_version_id="version-1",
            version_number=1,
            strategy_configuration_digest=SHA,
            lifecycle_status="REVIEWED",
            lifecycle_sequence=2,
            lifecycle_event_id="event-2",
            lifecycle_projection_digest=SHA,
        )


def test_observed_bar_binds_exact_canonical_bytes() -> None:
    observed = _bar("2026-01-05T09:01:00")
    with pytest.raises(AtomicBenchmarkIntegrityError, match="canonical"):
        ObservedBar(observed.bar, b'{"symbol": "2330"}')


def test_first_trigger_admission_is_once_per_symbol_session_and_bounded() -> None:
    owner = FirstTriggerAdmission()
    first = _admit(owner, _bar("2026-01-05T09:01:00"))
    repeat = _admit(owner, _bar("2026-01-05T09:02:00"))
    ignored = _admit(
        owner,
        _bar("2026-01-05T09:03:00", symbol="2317"),
        status="NOT_TRIGGERED",
    )
    next_session = _admit(owner, _bar("2026-01-06T09:01:00"))
    assert first is not None and repeat is None and ignored is None
    assert next_session is not None
    assert owner.state_count == 1
    assert owner.max_symbols_in_session == 1


def test_hundred_sessions_do_not_accumulate_admission_state() -> None:
    owner = FirstTriggerAdmission()
    start = datetime(2025, 1, 1, 9, 1, tzinfo=TAIPEI)
    for offset in range(100):
        at = start + timedelta(days=offset)
        assert _admit(owner, _bar(at.isoformat())) is not None
        assert owner.state_count == 1
    assert owner.sequence == 100


def test_matcher_uses_next_bar_and_last_later_same_session_bar() -> None:
    signal, match, _ = _one_episode(entry="101", exit_price="103")
    row = match.rows[0]
    assert row["signal_id"] == signal["signal_id"]
    assert row["entry_at"] == "2026-01-05T09:02:00+08:00"
    assert row["exit_at"] == "2026-01-05T13:30:00+08:00"
    assert row["raw_entry_open"] == "101"
    assert row["raw_exit_close"] == "103"
    assert match.max_waiting_count <= 1
    assert match.max_active_count <= 1


def test_matcher_fails_closed_on_cross_session_entry() -> None:
    owner = FirstTriggerAdmission()
    signal = _admit(owner, _bar("2026-01-05T13:30:00"))
    assert signal is not None
    match = build_match_plan(
        ledger_rows=(signal,),
        bars=(
            _bar("2026-01-05T13:30:00"),
            _bar("2026-01-06T09:01:00"),
        ),
    )
    assert match.rows == ()
    assert match.missing_entry_count == 1


def test_matcher_marks_entry_without_later_close_as_missing_exit() -> None:
    owner = FirstTriggerAdmission()
    signal = _admit(owner, _bar("2026-01-05T09:01:00"))
    assert signal is not None
    match = build_match_plan(
        ledger_rows=(signal,),
        bars=(
            _bar("2026-01-05T09:01:00"),
            _bar("2026-01-05T13:30:00"),
        ),
    )
    assert match.rows == ()
    assert match.missing_exit_count == 1


def test_episode_economics_are_fixed_and_rebuildable() -> None:
    _, _, episode = _one_episode(entry="100", exit_price="102")
    assert episode["shares"] == 1000
    assert episode["entry_fill_price"] == "100.05"
    assert episode["exit_fill_price"] == "101.949"
    assert episode["cost_identity_digest"] == COST_IDENTITY_DIGEST
    assert verify_episode_row(episode) == episode
    tampered = {**episode, "net_pnl": "999"}
    with pytest.raises(AtomicBenchmarkIntegrityError, match="economics"):
        verify_episode_row(tampered)


def test_layer_parity_detects_same_count_substitution() -> None:
    first, _, episode = _one_episode()
    replacement = {**episode, "signal_id": "b" * 64}
    difference = compare_layers((first,), (replacement,))
    assert difference.left_minus_right_count == 1
    assert difference.right_minus_left_count == 1


def test_summary_with_insufficient_evidence_remains_exploratory_only() -> None:
    _, _, episode = _one_episode()
    summary = build_summary(
        (episode,), family_id="family-1", hypothesis_id=SHA
    )
    assert summary["disposition"] == "INSUFFICIENT_EVIDENCE"
    assert summary["limitations"][0] == "EXPLORATORY_ONLY_NO_PROMOTION"
    assert summary["episode_count"] == 1


def test_daily_drawdown_quantizes_each_return_before_threshold_compounding() -> None:
    drawdown = _daily_equal_signal_max_drawdown(
        {
            "2026-01-05": (Decimal("0"),),
            "2026-01-06": (Decimal("-0.2000000000000000005"),),
        }
    )
    assert drawdown == Decimal("0.2")


def test_summary_compares_the_same_canonical_drawdown_it_serializes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        benchmark_domain,
        "_daily_equal_signal_max_drawdown",
        lambda _: Decimal("0.200000000000000000400012"),
    )
    summary = build_summary(
        _positive_screen_episodes(), family_id="family-1", hypothesis_id=SHA
    )
    assert summary["daily_equal_signal_max_drawdown"] == "0.2"
    assert summary["disposition"] == "PASS_EXPLORATORY_SCREEN"


def test_bootstrap_and_positive_screen_are_deterministic_golden_vector() -> None:
    episodes = _positive_screen_episodes()
    first = build_summary(episodes, family_id="family-1", hypothesis_id=SHA)
    second = build_summary(episodes, family_id="family-1", hypothesis_id=SHA)
    assert first == second
    assert first["disposition"] == "PASS_EXPLORATORY_SCREEN"
    assert first["bootstrap"]["independent_date_count"] == 30
    assert first["bootstrap"]["lower_bound"] == episodes[0][
        "net_return_on_raw_entry_notional"
    ]
    assert first["positive_complete_quarter_count"] == 11


def test_matcher_state_is_bounded_across_hundred_sessions() -> None:
    owner = FirstTriggerAdmission()
    signals = []
    bars = []
    start = datetime(2025, 1, 1, tzinfo=TAIPEI)
    for offset in range(100):
        day = (start + timedelta(days=offset)).date().isoformat()
        signal_bar = _bar(f"{day}T09:01:00")
        signal = _admit(owner, signal_bar)
        assert signal is not None
        signals.append(signal)
        bars.extend(
            (
                signal_bar,
                _bar(f"{day}T09:02:00"),
                _bar(f"{day}T13:30:00"),
            )
        )
    match = build_match_plan(ledger_rows=signals, bars=bars)
    assert len(match.rows) == 100
    assert match.max_waiting_count <= 1
    assert match.max_active_count <= 1


def test_ledger_unknown_field_fails_closed() -> None:
    owner = FirstTriggerAdmission()
    row = _admit(owner, _bar("2026-01-05T09:01:00"))
    assert row is not None
    with pytest.raises(AtomicBenchmarkIntegrityError, match="unknown"):
        verify_ledger_row({**row, "created_at": "2026-01-05T09:01:00+08:00"})
    assert canonical_object_bytes(row).endswith(b"\n")


def test_g1_publication_admissions_match_current_frozen_implementations() -> None:
    registry = AtomicStrategyRegistry()
    assert tuple(item.strategy_id for item in FROZEN_ADMISSIONS) == (
        "breakout_previous_high_entry",
        "volume_acceleration_entry",
        "opening_range_breakout_entry",
        "ema_crossover_entry",
    )
    for frozen in FROZEN_ADMISSIONS:
        _verify_frozen(registry, frozen)
