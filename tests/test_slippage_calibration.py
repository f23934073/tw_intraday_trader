import json
import random
import shutil
from dataclasses import replace
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from market_data.provider import MockProvider
from market_data.late_delivery_evidence import LateDeliveryCohort
from simulation.service import SimulationService
from simulation.execution_costs import PRICE_TICK_POLICY_VERSION, SLIPPAGE_POLICY_VERSION
from trading.local_paper import journal_record_from_simulation_order
from trading.journal import InMemoryJournalRepository, JournalRecord, JournalSession
from trading.slippage_calibration import (
    ACTUAL_EXECUTION_STATUS,
    ANALYSIS_REPORT_SCHEMA,
    ANALYZER_VERSION,
    ANALYSIS_SCOPE,
    CLOCK_DISPOSITION_SCHEMA,
    CalibrationContractError,
    FILL_EXPORT_SCHEMA,
    INPUT_MANIFEST_SCHEMA,
    METRIC_POLICY_VERSION,
    PERCENTILE_METHOD,
    PROXY_INPUT_NOT_QUALIFIED,
    PROXY_INSUFFICIENT,
    PROXY_QUALIFIED,
    TIMESTAMP_POLICY_VERSION,
    _coverage_report,
    _distribution,
    _extract_proxy_samples,
    _proxy_qualification_status,
    build_analysis_report,
    file_sha256,
    journal_record_to_export_mapping,
    load_sealed_json,
    seal_clock_disposition,
    seal_fill_export,
    seal_fill_journal_snapshot_from_repository,
    seal_input_manifest,
    write_sealed_json_once,
    write_analysis_report_once,
)


ROOT = Path(__file__).resolve().parents[1]
SESSION = (
    ROOT
    / "records/market_events/2026-08-21/tm-postfix-20260821-2330"
)
COHORT = (
    ROOT
    / "research/late_delivery_evidence/cohorts/"
    "cohort_2026-08-21_twse_2026-08-20.json"
)
CALENDAR = ROOT / "config/twse_calendar_2026.json"
AT = datetime.fromisoformat("2026-08-21T10:00:00+08:00")
SETTINGS_DIGEST = "d" * 64


def _write_json(path: Path, payload: object) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )


def _clock_disposition(tmp_path: Path, session_id: str) -> Path:
    draft = tmp_path / f"{session_id}.clock.draft.json"
    output = tmp_path / f"{session_id}.clock.json"
    review_evidence = tmp_path / f"{session_id}.clock-review.json"
    _write_json(
        review_evidence,
        {
            "schema_version": "local-paper-slippage-clock-review-evidence.v1",
            "session_id": session_id,
            "disposition": "REVIEWED_COMPARABLE",
            "approved_max_abs_source_receive_skew_ms": "1000",
            "market_session_manifest_sha256": file_sha256(SESSION / "manifest.json"),
            "review_method": "SOURCE_RECEIVE_TIMESTAMP_COMPARABILITY_REVIEW",
            "reviewed_at": "2026-08-27T10:00:00+08:00",
            "reviewer": {
                "reviewer_id": "independent-fixture-reviewer",
                "authority": "INDEPENDENT_REVIEWER",
            },
        },
    )
    _write_json(
        draft,
        {
            "schema_version": CLOCK_DISPOSITION_SCHEMA,
            "session_id": session_id,
            "status": "REVIEWED_COMPARABLE",
            "max_abs_source_receive_skew_ms": "1000",
            "review_basis": "fixture-reviewed bounded source/receive clock comparison",
            "review_authority": "INDEPENDENT_REVIEWER",
            "review_evidence_path": str(review_evidence),
        },
    )
    seal_clock_disposition(draft, output)
    return output


def _policy() -> dict[str, object]:
    return {
        "analyzer_version": ANALYZER_VERSION,
        "metric_policy_version": METRIC_POLICY_VERSION,
        "timestamp_policy_version": TIMESTAMP_POLICY_VERSION,
        "percentile_method": PERCENTILE_METHOD,
        "local_paper_slippage_policy_version": SLIPPAGE_POLICY_VERSION,
        "price_tick_policy_version": PRICE_TICK_POLICY_VERSION,
        "adverse_horizon_ms": 1000,
        "horizon_observation_tolerance_ms": 1000,
        "maximum_source_receive_skew_ms": 1000,
        "maximum_book_age_ms": 3000,
        "minimum_distinct_trading_days": 5,
        "minimum_samples_per_group": 30,
        "minimum_unique_books_per_group": 30,
        "required_session_phases": ["OPENING", "CONTINUOUS", "CLOSE"],
        "required_phase_buckets": ["EARLY", "MIDDLE", "LATE"],
        "required_sides": ["BUY", "SELL"],
        "required_liquidity_tiers": ["high", "mid", "low"],
    }


def _sealed_manifest(
    tmp_path: Path,
    *,
    session: Path = SESSION,
    session_id: str = "tm-postfix-20260821-2330",
    clock: Path | None = None,
    cohort: Path = COHORT,
    calendar: Path = CALENDAR,
    fill_exports: list[Path] | None = None,
) -> Path:
    draft = tmp_path / "input.draft.json"
    output = tmp_path / "input.json"
    _write_json(
        draft,
        {
            "schema_version": INPUT_MANIFEST_SCHEMA,
            "manifest_id": "test-slippage-calibration-input",
            "analysis_scope": ANALYSIS_SCOPE,
            "policy": _policy(),
            "cohort": {"cohort_id": "test-cohort", "path": str(cohort)},
            "trading_calendar": {"path": str(calendar)},
            "market_sessions": [
                {
                    "path": str(session),
                    "session_id": session_id,
                    "session_phase": "CONTINUOUS",
                    "clock_disposition": (
                        {"path": str(clock)} if clock is not None else None
                    ),
                }
            ],
            "fill_exports": [
                {"path": str(path)} for path in (fill_exports or [])
            ],
        },
    )
    seal_input_manifest(draft, output)
    return output


def _custom_cohort(tmp_path: Path) -> Path:
    path = tmp_path / "cohort.json"
    _write_json(
        path,
        {
            "capture_timezone": "Asia/Taipei",
            "schema": "late-delivery-cohort-manifest-v1",
            "selection_source": {
                "provider": "FIXTURE",
                "source_date": "2026-08-20",
                "source_identity": "fixture:sha256:" + "a" * 64,
            },
            "session_windows": [
                {"end_local": "09:30", "phase": "OPEN", "start_local": "09:00"},
                {"end_local": "11:00", "phase": "MID", "start_local": "10:30"},
                {"end_local": "13:30", "phase": "CLOSE", "start_local": "13:00"},
            ],
            "status": "FROZEN_FOR_COLLECTION",
            "symbols": [
                {"liquidity_tier": "high", "selection_evidence": "fixture", "symbol": "2330"},
                {"liquidity_tier": "high", "selection_evidence": "fixture", "symbol": "3231"},
                {"liquidity_tier": "mid", "selection_evidence": "fixture", "symbol": "1455"},
                {"liquidity_tier": "mid", "selection_evidence": "fixture", "symbol": "3380"},
                {"liquidity_tier": "low", "selection_evidence": "fixture", "symbol": "6918"},
                {"liquidity_tier": "low", "selection_evidence": "fixture", "symbol": "8367"},
            ],
        },
    )
    return path


def _fill_export(tmp_path: Path) -> Path:
    service = SimulationService(
        MockProvider(),
        starting_cash=Decimal("100000"),
        max_daily_buy_notional=Decimal("1000000"),
        slippage_bps=Decimal("5"),
        cost_policy_enabled=True,
    )
    order, _ = service.submit_order(
        symbol="3231",
        side="BUY",
        quantity_shares=100,
        limit_price="106",
        idempotency_key="slippage-calibration-fixture",
    )
    record = journal_record_from_simulation_order(
        order,
        session_id="fill-export-fixture",
        settings_digest=SETTINGS_DIGEST,
    )
    assert record is not None
    record = replace(record, occurred_at=AT)
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=record.session_id,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"settings_digest": SETTINGS_DIGEST},
        )
    )
    append_result = journal.append(record)
    snapshot = tmp_path / "fill-source-journal-snapshot.json"
    seal_fill_journal_snapshot_from_repository(
        repository=journal,
        session_id=record.session_id,
        output_path=snapshot,
    )
    draft = tmp_path / "fills.draft.json"
    output = tmp_path / "fills.json"
    _write_json(
        draft,
        {
            "schema_version": FILL_EXPORT_SCHEMA,
            "export_id": "fill-export-fixture",
            "session_id": record.session_id,
            "session_date": AT.date().isoformat(),
            "settings_digest": SETTINGS_DIGEST,
            "source_journal": {
                "repository_kind": "IN_MEMORY_TEST_FIXTURE",
                "snapshot_path": str(snapshot),
                "sequence_start": append_result.sequence,
                "sequence_end": append_result.sequence,
            },
            "records": [
                {
                    "sequence": append_result.sequence,
                    "fingerprint": record.fingerprint,
                    "record": journal_record_to_export_mapping(record),
                }
            ],
        },
    )
    seal_fill_export(draft, output)
    return output


def _market_event_records(
    events: list[dict[str, object]],
) -> tuple[dict[str, object], ...]:
    records: list[dict[str, object]] = []
    for offset, event in enumerate(events):
        ingress_index = offset * 2 + 1
        records.extend(
            [
                {
                    "record_type": "INGRESS",
                    "record_index": ingress_index,
                    "event": event,
                },
                {
                    "record_type": "DISPOSITION",
                    "record_index": ingress_index + 1,
                    "ingress_record_index": ingress_index,
                    "result": {"projection_applied": True},
                },
            ]
        )
    return tuple(records)


def _book_event(
    *,
    received_at: str,
    event_at: str | None = None,
    bid: str = "100",
    ask: str = "100.5",
    identity: str = "book-1",
) -> dict[str, object]:
    return {
        "event_id": identity,
        "symbol": "2330",
        "stream_kind": "BIDASK",
        "received_at": received_at,
        "event_at": event_at or received_at,
        "payload": {
            "bid_prices": [bid],
            "ask_prices": [ask],
            "intraday_odd": False,
            "simulated_trade": False,
        },
    }


def _tick_event(
    *,
    received_at: str,
    event_at: str | None = None,
    price: str = "100.5",
    identity: str = "tick-1",
) -> dict[str, object]:
    return {
        "event_id": identity,
        "symbol": "2330",
        "stream_kind": "TICK",
        "received_at": received_at,
        "event_at": event_at or received_at,
        "payload": {
            "price": price,
            "intraday_odd": False,
            "simulated_trade": False,
        },
    }


def _extract_fixture_samples(
    tmp_path: Path,
    events: list[dict[str, object]],
) -> tuple[list[object], dict[str, int | Decimal]]:
    return _extract_proxy_samples(
        records=_market_event_records(events),
        cohort=LateDeliveryCohort.from_path(_custom_cohort(tmp_path)),
        session_date=date(2026, 8, 21),
        declared_phase="CONTINUOUS",
        horizon_ms=1000,
        horizon_tolerance_ms=100,
        maximum_book_age_ms=1000,
    )


def test_fixture_analysis_is_deterministic_and_never_qualifies_actual_execution(
    tmp_path: Path,
) -> None:
    manifest = _sealed_manifest(
        tmp_path,
        clock=_clock_disposition(tmp_path, "tm-postfix-20260821-2330"),
    )

    first = build_analysis_report(manifest)
    second = build_analysis_report(manifest)

    assert first == second
    assert first["qualification"]["actual_execution_calibration"]["status"] == (
        ACTUAL_EXECUTION_STATUS
    )
    assert first["qualification"]["model_stress_proxy"]["status"] == (
        PROXY_INSUFFICIENT
    )
    assert len(first["diagnostic_model_stress_metrics"]) == 2
    assert first["coverage"]["qualified_group_count"] == 0


def test_manifest_bound_cohort_uses_the_verified_read_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohort = _custom_cohort(tmp_path)
    manifest = _sealed_manifest(
        tmp_path,
        cohort=cohort,
        clock=_clock_disposition(tmp_path, "tm-postfix-20260821-2330"),
    )
    expected_digest = file_sha256(cohort)
    original_read_bytes = Path.read_bytes
    swapped = False

    def swap_after_read(path: Path) -> bytes:
        nonlocal swapped
        encoded = original_read_bytes(path)
        if not swapped and path.resolve() == cohort.resolve():
            replacement = json.loads(encoded)
            for item in replacement["symbols"]:
                if item["symbol"] == "2330":
                    item["liquidity_tier"] = "low"
            _write_json(cohort, replacement)
            swapped = True
        return encoded

    monkeypatch.setattr(Path, "read_bytes", swap_after_read)
    report = build_analysis_report(manifest)

    assert swapped is True
    assert file_sha256(cohort) != expected_digest
    assert {
        item["dimensions"]["liquidity_tier"]
        for item in report["diagnostic_model_stress_metrics"]
    } == {"high"}


def test_manifest_bound_session_uses_a_private_verified_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    copied = tmp_path / "session"
    shutil.copytree(SESSION, copied)
    clock = _clock_disposition(tmp_path, "tm-postfix-20260821-2330")
    manifest = _sealed_manifest(tmp_path, session=copied, clock=clock)
    baseline = build_analysis_report(manifest)
    records = copied / "records.jsonl"
    expected_digest = file_sha256(records)
    original_read_bytes = Path.read_bytes
    swapped = False

    def mutate_after_read(path: Path) -> bytes:
        nonlocal swapped
        encoded = original_read_bytes(path)
        if not swapped and path.resolve() == records.resolve():
            records.write_bytes(encoded + b" ")
            swapped = True
        return encoded

    monkeypatch.setattr(Path, "read_bytes", mutate_after_read)
    replayed = build_analysis_report(manifest)

    assert swapped is True
    assert file_sha256(records) != expected_digest
    assert replayed == baseline


def test_bound_clock_fill_and_snapshot_use_the_verified_read_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cohort = _custom_cohort(tmp_path)
    clock = _clock_disposition(tmp_path, "tm-postfix-20260821-2330")
    fill_export = _fill_export(tmp_path)
    snapshot = tmp_path / "fill-source-journal-snapshot.json"
    manifest = _sealed_manifest(
        tmp_path,
        cohort=cohort,
        clock=clock,
        fill_exports=[fill_export],
    )
    baseline = build_analysis_report(manifest)
    targets = {path.resolve(): path for path in (clock, fill_export, snapshot)}
    expected_digests = {
        resolved: file_sha256(path) for resolved, path in targets.items()
    }
    original_read_bytes = Path.read_bytes
    swapped: set[Path] = set()

    def mutate_after_read(path: Path) -> bytes:
        encoded = original_read_bytes(path)
        resolved = path.resolve()
        if resolved in targets and resolved not in swapped:
            targets[resolved].write_bytes(encoded + b" ")
            swapped.add(resolved)
        return encoded

    monkeypatch.setattr(Path, "read_bytes", mutate_after_read)
    replayed = build_analysis_report(manifest)

    assert swapped == set(targets)
    assert all(
        file_sha256(path) != expected_digests[resolved]
        for resolved, path in targets.items()
    )
    assert replayed == baseline


def test_golden_proxy_metric_shape(tmp_path: Path) -> None:
    manifest = _sealed_manifest(
        tmp_path,
        clock=_clock_disposition(tmp_path, "tm-postfix-20260821-2330"),
    )
    report = build_analysis_report(manifest)
    actual = report["diagnostic_model_stress_metrics"]
    expected = json.loads(
        (ROOT / "tests/fixtures/slippage_calibration_golden_groups.json").read_text()
    )
    assert actual == expected


def test_missing_clock_disposition_fails_closed(tmp_path: Path) -> None:
    report = build_analysis_report(_sealed_manifest(tmp_path))
    assert report["qualification"]["model_stress_proxy"]["status"] == (
        PROXY_INPUT_NOT_QUALIFIED
    )
    assert report["diagnostic_model_stress_metrics"] == []
    assert "CLOCK_DISPOSITION_MISSING" in {
        item["code"] for item in report["issues"]
    }


def test_deleted_bound_clock_disposition_fails_closed(tmp_path: Path) -> None:
    clock = _clock_disposition(tmp_path, "tm-postfix-20260821-2330")
    manifest = _sealed_manifest(tmp_path, clock=clock)
    clock.unlink()

    report = build_analysis_report(manifest)

    assert report["qualification"]["model_stress_proxy"]["status"] == (
        PROXY_INPUT_NOT_QUALIFIED
    )
    assert report["diagnostic_model_stress_metrics"] == []
    assert "CLOCK_DISPOSITION_INVALID" in {
        item["code"] for item in report["issues"]
    }


def test_journal_tamper_is_detected_without_touching_source(tmp_path: Path) -> None:
    copied = tmp_path / "session"
    shutil.copytree(SESSION, copied)
    clock = _clock_disposition(tmp_path, "tm-postfix-20260821-2330")
    manifest = _sealed_manifest(tmp_path, session=copied, clock=clock)
    records = copied / "records.jsonl"
    records.write_bytes(records.read_bytes() + b" ")

    report = build_analysis_report(manifest)

    assert report["qualification"]["model_stress_proxy"]["status"] == (
        PROXY_INPUT_NOT_QUALIFIED
    )
    assert "ARTIFACT_SHA256_MISMATCH" in {
        item["code"] for item in report["issues"]
    }


def test_out_of_order_session_is_not_used(tmp_path: Path) -> None:
    session = (
        ROOT
        / "records/market_events/2026-08-21/hqual-20260821T093358-841c8ca7"
    )
    session_id = "hqual-20260821T093358-841c8ca7"
    report = build_analysis_report(
        _sealed_manifest(
            tmp_path,
            session=session,
            session_id=session_id,
            clock=_clock_disposition(tmp_path, session_id),
        )
    )
    codes = {item["code"] for item in report["issues"]}
    assert "OUT_OF_ORDER_OR_REJECTED_EVENTS" in codes
    assert "CAPTURE_QUALITY_NOT_PASSED" in codes
    assert "CLOCK_DISPOSITION_INVALID" in codes
    assert report["diagnostic_model_stress_metrics"] == []


def test_fill_v3_export_is_model_output_diagnostic_only(tmp_path: Path) -> None:
    cohort = _custom_cohort(tmp_path)
    fill_export = _fill_export(tmp_path)
    report = build_analysis_report(
        _sealed_manifest(
            tmp_path,
            cohort=cohort,
            clock=_clock_disposition(tmp_path, "tm-postfix-20260821-2330"),
            fill_exports=[fill_export],
        )
    )
    diagnostics = report["local_paper_fill_v3_model_output_diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["interpretation"] == (
        "LOCAL_PAPER_MODEL_OUTPUT_NOT_BROKER_EXECUTION"
    )
    assert "FILL_EXPORT_TEST_FIXTURE_ONLY" in {
        item["code"] for item in report["issues"]
    }
    assert report["qualification"]["actual_execution_calibration"]["status"] == (
        ACTUAL_EXECUTION_STATUS
    )


def test_distribution_property_is_order_invariant_and_monotonic() -> None:
    randomizer = random.Random(20260827)
    values = [Decimal(randomizer.randrange(0, 10000)) / 100 for _ in range(101)]
    forward = _distribution(values)
    randomizer.shuffle(values)
    shuffled = _distribution(values)

    assert forward == shuffled
    ordered = [
        Decimal(str(forward[name]))
        for name in ("min", "p50", "p90", "p95", "p99", "max")
    ]
    assert ordered == sorted(ordered)


def test_analysis_report_and_sidecar_are_write_once(tmp_path: Path) -> None:
    manifest = _sealed_manifest(
        tmp_path,
        clock=_clock_disposition(tmp_path, "tm-postfix-20260821-2330"),
    )
    output = tmp_path / "report.json"

    first = write_analysis_report_once(manifest, output)

    loaded = load_sealed_json(output, expected_schema=ANALYSIS_REPORT_SCHEMA)
    assert loaded == first
    assert output.with_suffix(".canonical.sha256").read_text().strip() == (
        first["content_sha256"]
    )
    with pytest.raises(FileExistsError):
        write_analysis_report_once(manifest, output)


def test_manifest_canonical_tamper_fails_before_analysis(tmp_path: Path) -> None:
    manifest = _sealed_manifest(tmp_path)
    payload = json.loads(manifest.read_text())
    payload["manifest_id"] = "tampered"
    _write_json(manifest, payload)

    with pytest.raises(CalibrationContractError, match="content_sha256"):
        build_analysis_report(manifest)


def test_policy_cannot_weaken_structural_floor(tmp_path: Path) -> None:
    _sealed_manifest(tmp_path)
    draft_path = tmp_path / "input.draft.json"
    draft = json.loads(draft_path.read_text())
    draft["policy"]["minimum_distinct_trading_days"] = 4
    _write_json(draft_path, draft)

    with pytest.raises(CalibrationContractError, match="weakens floor"):
        seal_input_manifest(draft_path, tmp_path / "weakened.json")


def test_book_must_be_causal_fresh_and_tick_aligned(tmp_path: Path) -> None:
    _, future_quality = _extract_fixture_samples(
        tmp_path,
        [
            _book_event(
                received_at="2026-08-21T10:00:00+08:00",
                event_at="2026-08-21T10:00:01+08:00",
            ),
            _tick_event(
                received_at="2026-08-21T10:00:00.100000+08:00",
                event_at="2026-08-21T10:00:00.500000+08:00",
            ),
        ],
    )
    assert future_quality["causal_ordering_failure_count"] == 1

    samples, stale_quality = _extract_fixture_samples(
        tmp_path,
        [
            _book_event(received_at="2026-08-21T10:00:00+08:00"),
            _tick_event(received_at="2026-08-21T10:00:01.100000+08:00"),
        ],
    )
    assert samples == []
    assert stale_quality["stale_book_count"] == 1

    with pytest.raises(CalibrationContractError, match="off common-stock tick grid"):
        _extract_fixture_samples(
            tmp_path,
            [
                _book_event(
                    received_at="2026-08-21T10:00:00+08:00",
                    bid="100.1",
                )
            ],
        )


def test_right_censored_tick_before_target_does_not_complete_horizon(
    tmp_path: Path,
) -> None:
    samples, quality = _extract_fixture_samples(
        tmp_path,
        [
            _book_event(received_at="2026-08-21T10:00:00+08:00"),
            _tick_event(received_at="2026-08-21T10:00:00.100000+08:00"),
            _tick_event(
                received_at="2026-08-21T10:00:01+08:00",
                identity="tick-before-target",
            ),
        ],
    )
    assert quality["paired_book_count"] == 2
    assert all(sample.adverse_movement_bps is None for sample in samples)


def test_clock_disposition_requires_bounded_independent_evidence(
    tmp_path: Path,
) -> None:
    evidence = tmp_path / "review.json"
    _write_json(
        evidence,
        {
            "schema_version": "local-paper-slippage-clock-review-evidence.v1",
            "session_id": "fixture-session",
            "disposition": "REVIEWED_COMPARABLE",
            "approved_max_abs_source_receive_skew_ms": "1001",
            "market_session_manifest_sha256": "a" * 64,
            "review_method": "SOURCE_RECEIVE_TIMESTAMP_COMPARABILITY_REVIEW",
            "reviewed_at": "2026-08-27T10:00:00+08:00",
            "reviewer": {
                "reviewer_id": "fixture-reviewer",
                "authority": "INDEPENDENT_REVIEWER",
            },
        },
    )
    draft = tmp_path / "clock.draft.json"
    _write_json(
        draft,
        {
            "schema_version": CLOCK_DISPOSITION_SCHEMA,
            "session_id": "fixture-session",
            "status": "REVIEWED_COMPARABLE",
            "max_abs_source_receive_skew_ms": "1001",
            "review_basis": "fixture",
            "review_authority": "INDEPENDENT_REVIEWER",
            "review_evidence_path": str(evidence),
        },
    )
    with pytest.raises(CalibrationContractError, match="bounded contract"):
        seal_clock_disposition(draft, tmp_path / "clock.json")

    _write_json(evidence, {"review": "arbitrary"})
    draft_payload = json.loads(draft.read_text())
    draft_payload["max_abs_source_receive_skew_ms"] = "1000"
    _write_json(draft, draft_payload)
    with pytest.raises(CalibrationContractError, match="evidence fields"):
        seal_clock_disposition(draft, tmp_path / "invalid-evidence-clock.json")


def test_fill_export_rejects_records_not_in_repository_snapshot(tmp_path: Path) -> None:
    _fill_export(tmp_path)
    draft_path = tmp_path / "fills.draft.json"
    draft = json.loads(draft_path.read_text())
    duplicate = dict(draft["records"][0])
    duplicate["sequence"] = 2
    draft["records"].append(duplicate)
    draft["source_journal"]["sequence_end"] = 2
    _write_json(draft_path, draft)

    with pytest.raises(CalibrationContractError, match="outside Journal snapshot"):
        seal_fill_export(draft_path, tmp_path / "duplicate-fills.json")


def test_fill_export_rejects_synthetic_record_not_persisted_in_snapshot(
    tmp_path: Path,
) -> None:
    _fill_export(tmp_path)
    draft_path = tmp_path / "fills.draft.json"
    draft = json.loads(draft_path.read_text())
    draft["records"][0]["record"]["record_id"] = "synthetic-not-persisted"
    _write_json(draft_path, draft)

    with pytest.raises(CalibrationContractError, match="exactly match"):
        seal_fill_export(draft_path, tmp_path / "synthetic-fills.json")


def test_manifest_rejects_repeated_fill_export_paths(tmp_path: Path) -> None:
    fill_export = _fill_export(tmp_path)
    with pytest.raises(CalibrationContractError, match="path must be unique"):
        _sealed_manifest(
            tmp_path,
            fill_exports=[fill_export, fill_export],
        )


def test_unreviewed_calendar_authority_fails_closed(tmp_path: Path) -> None:
    unreviewed = tmp_path / "unreviewed-calendar.json"
    payload = json.loads(CALENDAR.read_text())
    payload["schema_version"] = "unreviewed-calendar.v0"
    payload["timezone"] = "UTC"
    payload["source_urls"] = ["https://example.invalid/fake-calendar"]
    _write_json(unreviewed, payload)

    manifest = _sealed_manifest(tmp_path, calendar=unreviewed)

    with pytest.raises(CalibrationContractError, match="approved reviewed TWSE"):
        build_analysis_report(manifest)


def test_malformed_calendar_fails_with_contract_error(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed-calendar.json"
    _write_json(
        malformed,
        {
            "schema_version": "twse_calendar_2026_v1",
            "timezone": "Asia/Taipei",
            "annual_non_trading_dates": [],
            "exceptional_closures": [],
            "source_urls": ["https://example.invalid/incomplete-calendar"],
        },
    )
    manifest = _sealed_manifest(tmp_path, calendar=malformed)

    with pytest.raises(CalibrationContractError, match="trading calendar is invalid"):
        build_analysis_report(manifest)


def test_malformed_sealed_fill_export_is_an_input_issue(tmp_path: Path) -> None:
    malformed = tmp_path / "malformed-fill.json"
    write_sealed_json_once(
        malformed,
        {
            "schema_version": FILL_EXPORT_SCHEMA,
            "export_id": "malformed-fill-export",
        },
    )

    report = build_analysis_report(
        _sealed_manifest(tmp_path, fill_exports=[malformed])
    )

    assert report["qualification"]["model_stress_proxy"]["status"] == (
        PROXY_INPUT_NOT_QUALIFIED
    )
    assert any(
        item["code"] == "FILL_EXPORT_INVALID"
        and "source_journal" in item["detail"]
        for item in report["issues"]
    )


def test_distinct_fill_exports_cannot_repeat_one_journal_range(
    tmp_path: Path,
) -> None:
    cohort = _custom_cohort(tmp_path)
    first = _fill_export(tmp_path)
    draft_path = tmp_path / "fills.draft.json"
    second = tmp_path / "fills-duplicate.json"
    duplicate = json.loads(draft_path.read_text())
    duplicate["export_id"] = "fill-export-fixture-duplicate"
    _write_json(draft_path, duplicate)
    seal_fill_export(draft_path, second)

    report = build_analysis_report(
        _sealed_manifest(
            tmp_path,
            cohort=cohort,
            clock=_clock_disposition(tmp_path, "tm-postfix-20260821-2330"),
            fill_exports=[first, second],
        )
    )

    diagnostics = report["local_paper_fill_v3_model_output_diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["sample_count"] == 1
    assert any(
        item["code"] == "FILL_EXPORT_INVALID"
        and "overlapping source Journal ranges" in item["detail"]
        for item in report["issues"]
    )


def test_distinct_fill_exports_cannot_repeat_record_at_different_sequence(
    tmp_path: Path,
) -> None:
    cohort = _custom_cohort(tmp_path)
    first = _fill_export(tmp_path)
    first_draft = json.loads((tmp_path / "fills.draft.json").read_text())
    raw_record = first_draft["records"][0]["record"]
    record = JournalRecord(
        record_id=raw_record["record_id"],
        session_id=raw_record["session_id"],
        kind=raw_record["kind"],
        occurred_at=datetime.fromisoformat(raw_record["occurred_at"]),
        payload=raw_record["payload"],
        idempotency_scope=raw_record["idempotency_scope"],
        idempotency_key=raw_record["idempotency_key"],
        schema_version=raw_record["schema_version"],
    )
    journal = InMemoryJournalRepository()
    journal.start_session(
        JournalSession(
            session_id=record.session_id,
            started_at=AT,
            mode="LOCAL_PAPER_SIMULATION",
            metadata={"settings_digest": SETTINGS_DIGEST},
        )
    )
    journal.append(
        replace(
            record,
            record_id="unrelated-record-before-replayed-fill",
            kind="unrelated.fixture.v1",
            payload={"settings_digest": SETTINGS_DIGEST},
            idempotency_scope=None,
            idempotency_key=None,
        )
    )
    shifted = journal.append(record)
    assert shifted.sequence == 2

    snapshot = tmp_path / "fill-source-journal-shifted-snapshot.json"
    seal_fill_journal_snapshot_from_repository(
        repository=journal,
        session_id=record.session_id,
        output_path=snapshot,
    )
    second_draft = tmp_path / "fills-shifted.draft.json"
    second = tmp_path / "fills-shifted.json"
    _write_json(
        second_draft,
        {
            "schema_version": FILL_EXPORT_SCHEMA,
            "export_id": "fill-export-fixture-shifted",
            "session_id": record.session_id,
            "session_date": AT.date().isoformat(),
            "settings_digest": SETTINGS_DIGEST,
            "source_journal": {
                "repository_kind": "IN_MEMORY_TEST_FIXTURE",
                "snapshot_path": str(snapshot),
                "sequence_start": shifted.sequence,
                "sequence_end": shifted.sequence,
            },
            "records": [
                {
                    "sequence": shifted.sequence,
                    "fingerprint": record.fingerprint,
                    "record": journal_record_to_export_mapping(record),
                }
            ],
        },
    )
    seal_fill_export(second_draft, second)

    report = build_analysis_report(
        _sealed_manifest(
            tmp_path,
            cohort=cohort,
            clock=_clock_disposition(tmp_path, "tm-postfix-20260821-2330"),
            fill_exports=[first, second],
        )
    )

    diagnostics = report["local_paper_fill_v3_model_output_diagnostics"]
    assert len(diagnostics) == 1
    assert diagnostics[0]["sample_count"] == 1
    assert any(
        item["code"] == "FILL_EXPORT_INVALID"
        and "duplicate Journal record identity" in item["detail"]
        for item in report["issues"]
    )


def test_sealed_json_pair_rolls_back_if_sidecar_publish_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import trading.slippage_calibration as calibration_module

    output = tmp_path / "atomic.json"
    original_link = calibration_module.os.link
    calls = 0

    def fail_second_link(source: Path, destination: Path) -> None:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise OSError("injected sidecar publish failure")
        original_link(source, destination)

    monkeypatch.setattr(calibration_module.os, "link", fail_second_link)
    with pytest.raises(OSError, match="injected"):
        write_sealed_json_once(output, {"schema_version": "fixture.v1"})
    assert not output.exists()
    assert not output.with_suffix(".canonical.sha256").exists()


def test_complete_structural_coverage_reaches_proxy_qualified_status(
    tmp_path: Path,
) -> None:
    cohort = LateDeliveryCohort.from_path(_custom_cohort(tmp_path))
    groups: list[dict[str, object]] = []
    for symbol in cohort.symbols:
        for phase in ("OPENING", "CONTINUOUS", "CLOSE"):
            for side, source in (("BUY", "BEST_ASK"), ("SELL", "BEST_BID")):
                groups.append(
                    {
                        "dimensions": {
                            "symbol": symbol,
                            "liquidity_tier": cohort.tier_for(symbol),
                            "session_phase": phase,
                            "side": side,
                            "reference_source": source,
                        },
                        "coverage": {
                            "reference_sample_count": 30,
                            "adverse_sample_count": 30,
                            "missing_horizon_sample_count": 0,
                            "unique_book_count": 30,
                            "observed_phase_buckets": ["EARLY", "MIDDLE", "LATE"],
                            "distinct_trading_days": 5,
                        },
                        "metrics_bps": {},
                    }
                )
    coverage, issues = _coverage_report(
        groups=groups,
        cohort=cohort,
        minimum_days=5,
        minimum_samples=30,
        minimum_unique_books=30,
    )
    assert issues == []
    assert coverage["qualified_group_count"] == coverage["expected_group_count"]
    assert _proxy_qualification_status([], issues) == PROXY_QUALIFIED
