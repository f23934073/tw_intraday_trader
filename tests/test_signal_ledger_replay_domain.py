from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime, timedelta
from decimal import Decimal, ROUND_HALF_EVEN, localcontext
from zoneinfo import ZoneInfo

import pytest

from backtest.domain import HistoricalBar, canonical_json
from backtest.research_replay.domain import (
    ResearchReplayIntegrityError,
    MatchPlanStreamState,
    ObservedBar,
    build_ledger,
    build_ledger_manifest,
    build_match_manifest,
    build_match_plan,
    build_order_derivation,
    build_postflight,
    build_replay,
    build_result_manifest,
    compare_layers,
    decimal_text,
    iter_match_plan_rows,
    require_decimal_text,
    verify_ledger_row,
    verify_ledger_manifest,
    verify_match_manifest,
    verify_match_row,
    verify_modeled_exit_row,
    verify_modeled_entry_row,
    verify_order_row,
    verify_postflight,
    verify_replay_consistency,
    verify_result_manifest,
    verify_episode_row,
)


_TAIPEI = ZoneInfo("Asia/Taipei")


def _decision(
    decision_id: str,
    symbol: str,
    at: datetime,
) -> dict[str, object]:
    return {
        "decision_id": decision_id,
        "symbol": symbol,
        "side": "ENTRY",
        "event_at": at.isoformat(),
        "policy": "ANY",
        "triggered_strategy_ids": ["above_vwap_entry_v1"],
        "primary_strategy_id": "above_vwap_entry_v1",
        "evaluations": [],
        "execution_horizon": "INTRADAY_NEXT_BAR",
    }


def _order(decision: dict[str, object], index: int) -> dict[str, object]:
    return {
        "order_id": f"order-{index}",
        "decision_id": decision["decision_id"],
        "symbol": decision["symbol"],
        "side": "ENTRY",
        "created_at": decision["event_at"],
        "execution_horizon": "INTRADAY_NEXT_BAR",
        "primary_strategy_id": decision["primary_strategy_id"],
        "triggered_strategy_ids": decision["triggered_strategy_ids"],
    }


def _bar(symbol: str, at: datetime, *, opened: str, closed: str):
    bar = HistoricalBar(
        symbol=symbol,
        timestamp=at,
        session_date=at.date(),
        open=Decimal(opened),
        high=max(Decimal(opened), Decimal(closed)),
        low=min(Decimal(opened), Decimal(closed)),
        close=Decimal(closed),
        volume=1,
    )
    from backtest.research_replay.domain import ObservedBar

    return ObservedBar.from_historical_bar(
        bar, source_json=canonical_json(bar.to_dict()).encode("utf-8")
    )


def _identity() -> dict[str, object]:
    return {
        "baseline_run_id": "run-baseline",
        "baseline_config_digest": "1" * 64,
        "baseline_result_digest": "2" * 64,
        "v1_preflight_digest": "3" * 64,
        "v1_signal_multiplicity_digest": "4" * 64,
        "v1_invalid_postflight_digest": "5" * 64,
        "atomic_strategy_run_snapshot_digest": "6" * 64,
        "dataset_id": "dataset-finmind",
        "dataset_digest": "7" * 64,
        "dataset_manifest_digest": "8" * 64,
        "dataset_bars_sha256": "9" * 64,
        "dataset_binding_revision": 1,
        "dataset_amount_contract_digest": "a" * 64,
    }


def _pipeline():
    decisions = [
        _decision("decision-1", "2317", datetime(2026, 8, 21, 9, 1, tzinfo=_TAIPEI)),
        _decision("decision-2", "2330", datetime(2026, 8, 21, 9, 1, tzinfo=_TAIPEI)),
    ]
    ledger = build_ledger(baseline_run_id="run-baseline", decisions=decisions)
    derivation = build_order_derivation(
        ledger_rows=ledger.rows,
        orders=[_order(decision, index) for index, decision in enumerate(decisions, start=1)],
    )
    ledger_manifest = build_ledger_manifest(
        identity=_identity(), ledger=ledger, order_derivation=derivation
    )
    bars = [
        _bar("2317", datetime(2026, 8, 21, 9, 2, tzinfo=_TAIPEI), opened="100", closed="100"),
        _bar("2330", datetime(2026, 8, 21, 9, 2, tzinfo=_TAIPEI), opened="100", closed="100"),
        _bar("2317", datetime(2026, 8, 21, 9, 3, tzinfo=_TAIPEI), opened="110", closed="110"),
        _bar("2330", datetime(2026, 8, 21, 9, 3, tzinfo=_TAIPEI), opened="90", closed="90"),
    ]
    match = build_match_plan(ledger_rows=ledger.rows, bars=bars)
    match_manifest = build_match_manifest(
        ledger_manifest=ledger_manifest, match_plan=match
    )
    replay = build_replay(
        match_rows=match.rows,
        min_lot_shares=1000,
        slippage_bps="5",
        commission_rate="0.001425",
        sell_tax_rate="0.003",
    )
    result_manifest = build_result_manifest(
        replay_id="replay-1",
        registration_revision=1,
        ledger_manifest=ledger_manifest,
        match_manifest=match_manifest,
        replay=replay,
        min_lot_shares=1000,
        slippage_bps="5",
        commission_rate="0.001425",
        sell_tax_rate="0.003",
    )
    return (
        decisions,
        ledger,
        derivation,
        ledger_manifest,
        match,
        match_manifest,
        replay,
        result_manifest,
    )


def test_authoritative_order_and_derived_order_have_opposite_reorder_contracts() -> None:
    earlier = _decision(
        "decision-a", "2330", datetime(2026, 8, 21, 9, 1, tzinfo=_TAIPEI)
    )
    later = _decision(
        "decision-b", "2317", datetime(2026, 8, 21, 9, 2, tzinfo=_TAIPEI)
    )

    first = build_ledger(baseline_run_id="run-baseline", decisions=[later, earlier])
    reordered = build_ledger(baseline_run_id="run-baseline", decisions=[earlier, later])

    assert first.decision_projection_digest != reordered.decision_projection_digest
    assert first.rows_sha256 == reordered.rows_sha256
    assert first.rows == reordered.rows


def test_order_derivation_requires_exact_bidirectional_mapping() -> None:
    decision = _decision(
        "decision-1", "2330", datetime(2026, 8, 21, 9, 1, tzinfo=_TAIPEI)
    )
    ledger = build_ledger(baseline_run_id="run-baseline", decisions=[decision])

    with pytest.raises(ResearchReplayIntegrityError, match="一對一"):
        build_order_derivation(ledger_rows=ledger.rows, orders=[])

    drifted = _order(decision, 1)
    drifted["symbol"] = "2317"
    with pytest.raises(ResearchReplayIntegrityError, match="symbol"):
        build_order_derivation(ledger_rows=ledger.rows, orders=[drifted])


def test_execution_horizon_defaults_only_for_missing_or_null() -> None:
    base = _decision(
        "decision-1", "2330", datetime(2026, 8, 21, 9, 1, tzinfo=_TAIPEI)
    )
    for allowed in ("missing", None):
        decision = deepcopy(base)
        if allowed == "missing":
            decision.pop("execution_horizon")
        else:
            decision["execution_horizon"] = None
        ledger = build_ledger(baseline_run_id="run-baseline", decisions=[decision])
        order = _order(base, 1)
        if allowed == "missing":
            order.pop("execution_horizon")
        else:
            order["execution_horizon"] = None
        build_order_derivation(ledger_rows=ledger.rows, orders=[order])

    for invalid in ("", False, 0):
        decision = deepcopy(base)
        decision["execution_horizon"] = invalid
        with pytest.raises(ResearchReplayIntegrityError, match="INTRADAY_NEXT_BAR"):
            build_ledger(baseline_run_id="run-baseline", decisions=[decision])

        ledger = build_ledger(baseline_run_id="run-baseline", decisions=[base])
        order = _order(base, 1)
        order["execution_horizon"] = invalid
        with pytest.raises(ResearchReplayIntegrityError, match="execution_horizon"):
            build_order_derivation(ledger_rows=ledger.rows, orders=[order])


def test_observed_bar_requires_exact_authoritative_source_bytes() -> None:
    at = datetime(2026, 8, 21, 9, 2, tzinfo=_TAIPEI)
    observed = HistoricalBar(
        symbol="2330",
        timestamp=at,
        session_date=at.date(),
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("99"),
        close=Decimal("100"),
        volume=10,
    )
    other = HistoricalBar(
        symbol="2317",
        timestamp=datetime(2026, 8, 21, 10, 0, tzinfo=_TAIPEI),
        session_date=at.date(),
        open=Decimal("999"),
        high=Decimal("999"),
        low=Decimal("999"),
        close=Decimal("999"),
        volume=10,
    )

    with pytest.raises(ResearchReplayIntegrityError, match="HistoricalBar 不一致"):
        ObservedBar.from_historical_bar(
            observed,
            source_json=canonical_json(other.to_dict()).encode("utf-8"),
        )
    different_volume = HistoricalBar(
        **{**observed.__dict__, "volume": 11}
    )
    with pytest.raises(ResearchReplayIntegrityError, match="HistoricalBar 不一致"):
        ObservedBar.from_historical_bar(
            observed,
            source_json=canonical_json(different_volume.to_dict()).encode("utf-8"),
        )
    with pytest.raises(ResearchReplayIntegrityError, match="不可為空"):
        ObservedBar.from_historical_bar(observed, source_json=b"")
    with pytest.raises(TypeError):
        ObservedBar.from_historical_bar(observed)  # type: ignore[call-arg]

    unknown = {**observed.to_dict(), "locator": "/tmp/not-authority"}
    with pytest.raises(ResearchReplayIntegrityError, match="exact HistoricalBar"):
        ObservedBar.from_historical_bar(
            observed, source_json=canonical_json(unknown).encode("utf-8")
        )
    bool_volume = {**observed.to_dict(), "volume": True}
    with pytest.raises(ResearchReplayIntegrityError, match="exact HistoricalBar"):
        ObservedBar.from_historical_bar(
            observed, source_json=canonical_json(bool_volume).encode("utf-8")
        )


def test_matcher_uses_next_bar_and_same_session_close() -> None:
    _, ledger, _, _, match, _, _, _ = _pipeline()

    assert match.signal_count == 2
    assert match.missing_entry_count == 0
    assert match.missing_exit_count == 0
    assert [row["sequence"] for row in match.rows] == [1, 2]
    assert all(row["entry_bar_at"].endswith("09:02:00+08:00") for row in match.rows)
    assert all(row["exit_bar_at"].endswith("09:03:00+08:00") for row in match.rows)
    assert not any(row["cross_session_exit"] for row in match.rows)
    assert compare_layers(ledger.rows, match.rows).equal


def test_entry_on_session_close_exits_on_later_session_close() -> None:
    decision = _decision(
        "decision-1", "2330", datetime(2026, 8, 21, 13, 29, tzinfo=_TAIPEI)
    )
    ledger = build_ledger(baseline_run_id="run-baseline", decisions=[decision])
    bars = [
        _bar("2330", datetime(2026, 8, 21, 13, 30, tzinfo=_TAIPEI), opened="100", closed="101"),
        _bar("2330", datetime(2026, 8, 22, 9, 1, tzinfo=_TAIPEI), opened="102", closed="102"),
        _bar("2330", datetime(2026, 8, 22, 13, 30, tzinfo=_TAIPEI), opened="103", closed="104"),
    ]

    match = build_match_plan(ledger_rows=ledger.rows, bars=bars)

    assert match.missing_entry_count == match.missing_exit_count == 0
    assert match.rows[0]["entry_on_session_close"] is True
    assert match.rows[0]["cross_session_exit"] is True
    assert match.rows[0]["exit_session_date"] == "2026-08-22"


def test_cross_session_next_observed_entry_and_overlapping_signals() -> None:
    decisions = [
        _decision(
            "decision-1", "2330", datetime(2026, 8, 21, 13, 30, tzinfo=_TAIPEI)
        ),
        _decision(
            "decision-2", "2330", datetime(2026, 8, 22, 9, 1, tzinfo=_TAIPEI)
        ),
    ]
    ledger = build_ledger(baseline_run_id="run-baseline", decisions=decisions)
    match = build_match_plan(
        ledger_rows=ledger.rows,
        bars=[
            _bar(
                "2330",
                datetime(2026, 8, 21, 13, 30, tzinfo=_TAIPEI),
                opened="99",
                closed="99",
            ),
            _bar(
                "2330",
                datetime(2026, 8, 22, 9, 1, tzinfo=_TAIPEI),
                opened="100",
                closed="100",
            ),
            _bar(
                "2330",
                datetime(2026, 8, 22, 9, 2, tzinfo=_TAIPEI),
                opened="101",
                closed="101",
            ),
            _bar(
                "2330",
                datetime(2026, 8, 22, 13, 30, tzinfo=_TAIPEI),
                opened="102",
                closed="103",
            ),
        ],
    )

    assert len(match.rows) == 2
    assert match.rows[0]["entry_session_date"] == "2026-08-22"
    assert match.rows[0]["cross_session_entry"] is True
    assert match.rows[0]["entry_bar_at"].endswith("09:01:00+08:00")
    assert match.rows[1]["entry_bar_at"].endswith("09:02:00+08:00")
    assert {row["exit_bar_at"] for row in match.rows} == {
        "2026-08-22T13:30:00+08:00"
    }


def test_matcher_fails_closed_with_missing_entry_or_exit() -> None:
    decision = _decision(
        "decision-1", "2330", datetime(2026, 8, 21, 13, 29, tzinfo=_TAIPEI)
    )
    ledger = build_ledger(baseline_run_id="run-baseline", decisions=[decision])

    missing_exit = build_match_plan(
        ledger_rows=ledger.rows,
        bars=[
            _bar("2330", datetime(2026, 8, 21, 13, 30, tzinfo=_TAIPEI), opened="100", closed="100")
        ],
    )
    missing_entry = build_match_plan(ledger_rows=ledger.rows, bars=[])

    assert missing_exit.missing_exit_count == 1
    assert missing_entry.missing_entry_count == 1


def test_match_manifest_distinguishes_entry_from_completed_exit() -> None:
    decision = _decision(
        "decision-1", "2330", datetime(2026, 8, 21, 13, 29, tzinfo=_TAIPEI)
    )
    ledger = build_ledger(baseline_run_id="run-baseline", decisions=[decision])
    derivation = build_order_derivation(
        ledger_rows=ledger.rows, orders=[_order(decision, 1)]
    )
    ledger_manifest = build_ledger_manifest(
        identity=_identity(), ledger=ledger, order_derivation=derivation
    )
    match = build_match_plan(
        ledger_rows=ledger.rows,
        bars=[
            _bar(
                "2330",
                datetime(2026, 8, 21, 13, 30, tzinfo=_TAIPEI),
                opened="100",
                closed="100",
            )
        ],
    )

    manifest = build_match_manifest(
        ledger_manifest=ledger_manifest, match_plan=match
    )

    assert manifest["signal_count"] == 1
    assert manifest["matched_entry_count"] == 1
    assert manifest["matched_exit_count"] == 0
    assert manifest["missing_entry_count"] == 0
    assert manifest["missing_exit_count"] == 1


def test_multi_session_match_stream_keeps_only_current_state() -> None:
    start = date(2025, 1, 1)
    decisions = [
        _decision(
            f"decision-{index}",
            "2330",
            datetime.combine(start + timedelta(days=index), datetime.min.time(), _TAIPEI)
            .replace(hour=9),
        )
        for index in range(400)
    ]
    ledger = build_ledger(baseline_run_id="run-baseline", decisions=decisions)

    def bars():
        for index in range(400):
            session = start + timedelta(days=index)
            yield _bar(
                "2330",
                datetime.combine(session, datetime.min.time(), _TAIPEI).replace(
                    hour=9, minute=1
                ),
                opened="100",
                closed="100",
            )
            yield _bar(
                "2330",
                datetime.combine(session, datetime.min.time(), _TAIPEI).replace(
                    hour=13, minute=30
                ),
                opened="100",
                closed="101",
            )

    state = MatchPlanStreamState()
    count = sum(
        1
        for _ in iter_match_plan_rows(
            ledger_rows=iter(ledger.rows), bars=bars(), state=state
        )
    )

    assert count == state.signal_count == 400
    assert state.complete is True
    assert state.missing_entry_count == state.missing_exit_count == 0
    assert state.max_waiting_count == state.max_pending_count == 1


def test_one_lot_math_and_finite_profit_factor_are_exact() -> None:
    *_, replay, _ = _pipeline()
    winning = replay.episodes[0]

    assert winning["raw_entry_open"] == "100"
    assert winning["raw_exit_close"] == "110"
    assert winning["pre_slippage_price_pnl"] == "10000"
    assert winning["post_slippage_gross_pnl"] == "9895"
    assert winning["explicit_costs"] == "629.077875"
    assert winning["net_pnl"] == "9265.922125"
    assert replay.summary["profit_factor_state"] == "FINITE"

    gains = sum(
        (Decimal(row["net_pnl"]) for row in replay.episodes if Decimal(row["net_pnl"]) > 0),
        Decimal(0),
    )
    losses = abs(
        sum(
            (Decimal(row["net_pnl"]) for row in replay.episodes if Decimal(row["net_pnl"]) < 0),
            Decimal(0),
        )
    )
    with localcontext() as context:
        context.prec = 38
        context.rounding = ROUND_HALF_EVEN
        expected = (gains / losses).quantize(
            Decimal("0.000000000000000001"), rounding=ROUND_HALF_EVEN
        )
    assert replay.summary["profit_factor"] == decimal_text(expected, "expected PF")


def test_replay_manifest_and_postflight_reject_cost_identity_substitution() -> None:
    (
        _,
        ledger,
        derivation,
        ledger_manifest,
        match,
        match_manifest,
        replay,
        result_manifest,
    ) = _pipeline()
    expensive_replay = build_replay(
        match_rows=match.rows,
        min_lot_shares=1000,
        slippage_bps="500",
        commission_rate="0.02",
        sell_tax_rate="0.01",
    )

    with pytest.raises(ResearchReplayIntegrityError, match="cost identity"):
        build_result_manifest(
            replay_id="replay-substituted",
            registration_revision=1,
            ledger_manifest=ledger_manifest,
            match_manifest=match_manifest,
            replay=expensive_replay,
            min_lot_shares=1000,
            slippage_bps="5",
            commission_rate="0.001425",
            sell_tax_rate="0.003",
        )

    with pytest.raises(ResearchReplayIntegrityError, match="lineage"):
        build_postflight(
            replay_id="replay-1",
            registration_revision=1,
            baseline_result_digest="2" * 64,
            ledger_manifest=ledger_manifest,
            match_manifest=match_manifest,
            result_manifest=result_manifest,
            decision_rows=ledger.rows,
            order_rows=derivation.rows,
            ledger_rows=ledger.rows,
            match_rows=match.rows,
            episode_rows=replay.episodes,
            modeled_entry_rows=replay.modeled_entries,
            modeled_exit_rows=replay.modeled_exits,
            min_lot_shares=1000,
            slippage_bps="500",
            commission_rate="0.02",
            sell_tax_rate="0.01",
            baseline_identity_valid=True,
            v1_invalid_lineage_valid=True,
            order_inception_seal_valid=True,
            ledger_artifact_valid=True,
            match_plan_artifact_valid=True,
            result_artifact_valid=True,
            v1_signal_multiplicity_valid=True,
        )


def test_strict_row_rejects_unknown_decimal_and_timestamp_aliases() -> None:
    _, ledger, *_ = _pipeline()
    unknown = deepcopy(ledger.rows[0])
    unknown["current_equity"] = "10000000"
    with pytest.raises(ResearchReplayIntegrityError, match="unknown"):
        verify_ledger_row(unknown)

    alias = deepcopy(ledger.rows[0])
    alias["signal_at"] = alias["signal_at"].replace("+08:00", "+0800")
    with pytest.raises(ResearchReplayIntegrityError):
        verify_ledger_row(alias)

    with pytest.raises(ResearchReplayIntegrityError):
        decimal_text(1.2, "binary float")

    exponent = deepcopy(ledger.rows[0])
    exponent["signal_at"] = "2026-08-21T01:01:00Z"
    with pytest.raises(ResearchReplayIntegrityError):
        verify_ledger_row(exponent)

    non_nfc = deepcopy(ledger.rows[0])
    non_nfc["symbol"] = "e\u0301"
    with pytest.raises(ResearchReplayIntegrityError, match="NFC"):
        verify_ledger_row(non_nfc)

    with pytest.raises(ResearchReplayIntegrityError, match="canonical"):
        require_decimal_text("1.0", "trailing zero")

    with pytest.raises(ResearchReplayIntegrityError, match="canonical"):
        require_decimal_text("1e2", "exponent")

    with pytest.raises(ValueError, match="OHLC"):
        HistoricalBar(
            symbol="2330",
            timestamp=datetime(2026, 8, 21, 9, 1, tzinfo=_TAIPEI),
            session_date=date(2026, 8, 21),
            open=Decimal("0"),
            high=Decimal("1"),
            low=Decimal("0"),
            close=Decimal("1"),
            volume=1,
        )


def test_row_id_and_economic_formula_reconstruction_fail_closed() -> None:
    *_, match, _, replay, _ = _pipeline()
    bad_match = deepcopy(match.rows[0])
    bad_match["match_id"] = "f" * 64
    with pytest.raises(ResearchReplayIntegrityError, match="match_id"):
        verify_match_row(bad_match)

    bad_entry = deepcopy(replay.modeled_entries[0])
    bad_entry["fill_price"] = "100"
    with pytest.raises(ResearchReplayIntegrityError, match="gross"):
        verify_modeled_entry_row(bad_entry)

    bad_episode = deepcopy(replay.episodes[0])
    bad_episode["net_pnl"] = "1"
    with pytest.raises(ResearchReplayIntegrityError, match="economic formula"):
        verify_replay_consistency(
            episode_rows=(bad_episode, *replay.episodes[1:]),
            modeled_entry_rows=replay.modeled_entries,
            modeled_exit_rows=replay.modeled_exits,
            summary=replay.summary,
        )


def test_every_g1_row_and_manifest_rejects_missing_or_unknown_fields() -> None:
    (
        _,
        ledger,
        derivation,
        ledger_manifest,
        match,
        match_manifest,
        replay,
        result_manifest,
    ) = _pipeline()
    cases = (
        (ledger.rows[0], verify_ledger_row),
        (derivation.rows[0], verify_order_row),
        (match.rows[0], verify_match_row),
        (replay.episodes[0], verify_episode_row),
        (replay.modeled_entries[0], verify_modeled_entry_row),
        (replay.modeled_exits[0], verify_modeled_exit_row),
        (ledger_manifest, verify_ledger_manifest),
        (match_manifest, verify_match_manifest),
        (result_manifest, verify_result_manifest),
    )
    for source, verifier in cases:
        missing = deepcopy(source)
        missing.pop(next(iter(missing)))
        with pytest.raises(ResearchReplayIntegrityError, match="schema"):
            verifier(missing)
        unknown = deepcopy(source)
        unknown["unknown_field"] = "not allowed"
        with pytest.raises(ResearchReplayIntegrityError, match="schema"):
            verifier(unknown)


def test_same_count_signal_substitution_fails_layer_parity() -> None:
    _, ledger, _, _, match, *_ = _pipeline()
    substituted = [dict(row) for row in match.rows]
    substituted[0]["semantic_key"] = "f" * 64

    difference = compare_layers(ledger.rows, substituted)

    assert difference.left_minus_right_count == 1
    assert difference.right_minus_left_count == 1
    assert not difference.equal


def test_postflight_is_exact_and_small_fixture_remains_fail_closed() -> None:
    (
        _,
        ledger,
        derivation,
        ledger_manifest,
        match,
        match_manifest,
        replay,
        result_manifest,
    ) = _pipeline()
    postflight = build_postflight(
        replay_id="replay-1",
        registration_revision=1,
        baseline_result_digest="2" * 64,
        ledger_manifest=ledger_manifest,
        match_manifest=match_manifest,
        result_manifest=result_manifest,
        decision_rows=ledger.rows,
        order_rows=derivation.rows,
        ledger_rows=ledger.rows,
        match_rows=match.rows,
        episode_rows=replay.episodes,
        modeled_entry_rows=replay.modeled_entries,
        modeled_exit_rows=replay.modeled_exits,
        min_lot_shares=1000,
        slippage_bps="5",
        commission_rate="0.001425",
        sell_tax_rate="0.003",
        baseline_identity_valid=True,
        v1_invalid_lineage_valid=True,
        order_inception_seal_valid=True,
        ledger_artifact_valid=True,
        match_plan_artifact_valid=True,
        result_artifact_valid=True,
        v1_signal_multiplicity_valid=True,
    )

    assert postflight["verdict"] == "INVALID"
    assert not postflight["conditions"]["frozen_signal_count_matches"]
    assert postflight["conditions"]["decision_ledger_bidirectional_parity"]
    assert verify_postflight(postflight) == postflight

    tampered = deepcopy(postflight)
    tampered["diagnostics"]["provider_call_count"] = 1
    with pytest.raises(ResearchReplayIntegrityError, match="digest"):
        verify_postflight(tampered)

    unknown = deepcopy(postflight)
    unknown["unknown_field"] = True
    with pytest.raises(ResearchReplayIntegrityError, match="schema"):
        verify_postflight(unknown)
    missing = deepcopy(postflight)
    missing.pop("conditions")
    with pytest.raises(ResearchReplayIntegrityError, match="schema"):
        verify_postflight(missing)
