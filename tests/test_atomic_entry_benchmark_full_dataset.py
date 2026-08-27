from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Callable

import pytest

from backtest.atomic_benchmark.application import PROTOCOL_CORE, amendment_a2_protocol_core
from backtest.atomic_benchmark.domain import (
    ALGORITHM_CONTRACT_DIGEST,
    AtomicBenchmarkIntegrityError,
    ObservedBar,
    canonical_object_bytes,
)
from backtest.atomic_benchmark.preflight import (
    AtomicBenchmarkEligibilityAuditService,
    AtomicBenchmarkPreflightService,
    PreflightSlotRuntime,
    verify_preflight_artifact,
)
from backtest.domain import EvaluationStatus, StrategyEvaluation, StrategySide, digest
from backtest.strategies import StrategyContext
from tests.test_atomic_entry_benchmark_domain import SHA, _bar


def _source_sha(bars: tuple[ObservedBar, ...]) -> str:
    return hashlib.sha256(
        b"".join(item.source_json + b"\n" for item in bars)
    ).hexdigest()


def _audit_scope() -> dict[str, object]:
    return {
        "family_id": "family-test",
        "active_matrix_id": "matrix-test-v2",
        "active_matrix_revision": 2,
        "active_matrix_registration_digest": SHA,
        "active_protocol_core_digest": SHA,
        "active_benchmark_build_binding_digest": SHA,
        "research_baseline_digest": SHA,
        "dataset_binding_revision": 1,
        "family_head_sequence": 0,
        "attempt_count": 0,
        "candidate_protocol_core_digest": SHA,
        "candidate_eligibility_audit_implementation_digest": SHA,
    }


class _Dataset:
    def __init__(self, bars: tuple[ObservedBar, ...]) -> None:
        self._bars = bars
        self.source_bar_count = 0
        self.source_bars_sha256 = hashlib.sha256(b"").hexdigest()
        self.source_eof_verified = False
        self._sha = _source_sha(bars)

    @property
    def manifest(self) -> dict[str, object]:
        return {
            "dataset_id": "dataset-test",
            "manifest_digest": SHA,
            "bars_sha256": self._sha,
            "bar_count": len(self._bars),
        }

    def iter_observed_bars(self):
        checksum = hashlib.sha256()
        for bar in self._bars:
            checksum.update(bar.source_json + b"\n")
            yield bar
        self.source_bar_count = len(self._bars)
        self.source_bars_sha256 = checksum.hexdigest()
        self.source_eof_verified = True


@dataclass
class _Runtime:
    slot: int
    trigger_at: str = "09:01"
    trigger_by_symbol: dict[str, str] | None = None
    reset_count: int = 0
    session: date | None = None
    begin_count: int = 0
    evaluated_symbols: list[str] | None = None

    def reset_runtime(self) -> None:
        self.reset_count += 1

    def begin_session(self, session_date: date) -> None:
        self.session = session_date
        self.begin_count += 1

    def evaluate_with_feature_evidence(self, context: StrategyContext):
        if self.evaluated_symbols is not None:
            self.evaluated_symbols.append(context.symbol)
        trigger_at = (
            self.trigger_by_symbol.get(context.symbol, "")
            if self.trigger_by_symbol is not None
            else self.trigger_at
        )
        triggered = context.bar.timestamp.strftime("%H:%M") == trigger_at
        return (
            StrategyEvaluation(
                strategy_id=f"strategy-{self.slot}",
                strategy_name=f"Strategy {self.slot}",
                strategy_version="1",
                side=StrategySide.ENTRY,
                status=(
                    EvaluationStatus.TRIGGERED
                    if triggered
                    else EvaluationStatus.NOT_TRIGGERED
                ),
                symbol=context.symbol,
                event_at=context.bar.timestamp,
                reason="fixture",
                observed={"close": str(context.bar.close)},
                threshold={"slot": self.slot},
                strategy_version_id=f"version-{self.slot}",
            ),
            {
                "schema_version": "r6-feature-input-evidence-v1",
                "input_digest": hashlib.sha256(
                    f"{self.slot}:{context.symbol}:{context.bar.timestamp.isoformat()}".encode()
                ).hexdigest(),
            },
        )


def _slots(
    dataset_sha: str,
    runtime_factory: Callable[[int], _Runtime] = _Runtime,
) -> tuple[PreflightSlotRuntime, ...]:
    values = []
    for slot in range(1, 8):
        hypothesis = hashlib.sha256(f"hypothesis-{slot}".encode()).hexdigest()
        values.append(
            PreflightSlotRuntime(
                identity={
                    "matrix_id": "matrix-test",
                    "registration_digest": SHA,
                    "family_id": "family-test",
                    "research_baseline_digest": SHA,
                    "slot_sequence": slot,
                    "hypothesis_id": hypothesis,
                    "strategy_id": f"strategy-{slot}",
                    "strategy_version_id": f"version-{slot}",
                    "strategy_configuration_digest": SHA,
                    "strategy_implementation_digest": SHA,
                    "lifecycle_sequence": 1,
                    "lifecycle_event_id": f"event-{slot}",
                    "lifecycle_projection_digest": SHA,
                    "dataset_id": "dataset-test",
                    "dataset_digest": SHA,
                    "dataset_bars_sha256": dataset_sha,
                    "dataset_binding_revision": 1,
                    "protocol_core_digest": SHA,
                    "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
                    "algorithm_implementation_digest": SHA,
                },
                feature_request_identity_digest=SHA,
                strategy=runtime_factory(slot),
            )
        )
    return tuple(values)


def _bars() -> tuple[ObservedBar, ...]:
    return (
        _bar("2026-01-05T09:01:00", close="100"),
        _bar("2026-01-05T09:02:00", open_price="101", close="101"),
        _bar("2026-01-05T12:45:00", open_price="102", close="102"),
        _bar("2026-01-05T13:30:00", open_price="102", close="103"),
    )


def _build(
    root: Path,
    bars: tuple[ObservedBar, ...] | None = None,
    *,
    matrix_revision: int = 2,
):
    source = bars or _bars()
    dataset = _Dataset(source)
    return AtomicBenchmarkPreflightService(root).build(
        slots=_slots(_source_sha(source)),
        dataset=dataset,
        family_id="family-test",
        matrix_id="matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        dataset_binding_revision=1,
        algorithm_implementation_digest=SHA,
        preflight_implementation_digest=SHA,
        matrix_revision=matrix_revision,
    )


def test_g3_builds_seven_slots_once_and_replays_exactly(tmp_path: Path) -> None:
    first = _build(tmp_path)
    verified = verify_preflight_artifact(first.path, expected_manifest=first.manifest)
    assert verified.preflight_digest == first.preflight_digest
    assert len(verified.slot_roots) == 7
    assert [item["signal_count"] for item in verified.slot_roots] == [1] * 7
    assert [item["matched_count"] for item in verified.slot_roots] == [1] * 7
    assert not any("result" in path.name or "summary" in path.name for path in first.path.rglob("*"))

    second = _build(tmp_path)
    assert second.path == first.path
    assert second.manifest == first.manifest


def test_g3_preflight_rejects_canonical_row_tamper(tmp_path: Path) -> None:
    built = _build(tmp_path)
    ledger = built.path / "slot-01" / "ledger.jsonl"
    payload = ledger.read_bytes()
    ledger.write_bytes(payload.replace(b'"current_close":"100"', b'"current_close":"99"'))
    with pytest.raises(AtomicBenchmarkIntegrityError):
        verify_preflight_artifact(built.path)


def test_g3_ineligible_coverage_below_floor_publishes_nothing(tmp_path: Path) -> None:
    bars = (_bar("2026-01-05T09:01:00", close="100"),)
    with pytest.raises(
        AtomicBenchmarkIntegrityError,
        match=r"eligible symbol/session ratio below 0.95",
    ):
        _build(tmp_path, bars)
    assert not tuple(path for path in tmp_path.iterdir() if not path.name.startswith("."))


def test_g3_root_rejects_unknown_artifact_member(tmp_path: Path) -> None:
    built = _build(tmp_path)
    (built.path / "performance.json").write_text("{}", encoding="utf-8")
    with pytest.raises(AtomicBenchmarkIntegrityError, match="member tree"):
        verify_preflight_artifact(built.path)


def test_g3_root_rejects_symlinked_artifact_member(tmp_path: Path) -> None:
    built = _build(tmp_path)
    manifest = built.path / "eligibility" / "manifest.json"
    external = tmp_path / "external-eligibility-manifest.json"
    external.write_bytes(manifest.read_bytes())
    manifest.unlink()
    manifest.symlink_to(external)

    with pytest.raises(AtomicBenchmarkIntegrityError, match="symlinks"):
        verify_preflight_artifact(built.path)


def test_g3_match_output_preserves_signal_sequence_when_entries_reorder(
    tmp_path: Path,
) -> None:
    bars = (
        _bar("2026-01-05T09:01:00", symbol="2330"),
        _bar("2026-01-05T09:02:00", symbol="2317"),
        _bar("2026-01-05T09:03:00", symbol="2317"),
        _bar("2026-01-05T09:10:00", symbol="2330"),
        _bar("2026-01-05T12:45:00", symbol="2317"),
        _bar("2026-01-05T12:45:00", symbol="2330"),
        _bar("2026-01-05T13:30:00", symbol="2317"),
        _bar("2026-01-05T13:30:00", symbol="2330"),
    )
    dataset = _Dataset(bars)
    build = AtomicBenchmarkPreflightService(tmp_path).build(
        slots=_slots(
            _source_sha(bars),
            runtime_factory=lambda slot: _Runtime(
                slot,
                trigger_by_symbol={"2330": "09:01", "2317": "09:02"},
            ),
        ),
        dataset=dataset,
        family_id="family-test",
        matrix_id="matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        dataset_binding_revision=1,
        algorithm_implementation_digest=SHA,
        preflight_implementation_digest=SHA,
    )
    verified = verify_preflight_artifact(build.path)
    assert [item["matched_count"] for item in verified.slot_roots] == [2] * 7


def test_a1_signal_1244_enters_1245_and_exits_exact_1330(tmp_path: Path) -> None:
    bars = (
        _bar("2026-01-05T12:44:00"),
        _bar("2026-01-05T12:45:00", open_price="101", close="101"),
        _bar("2026-01-05T13:30:00", open_price="102", close="103"),
    )
    dataset = _Dataset(bars)
    build = AtomicBenchmarkPreflightService(tmp_path).build(
        slots=_slots(
            _source_sha(bars),
            runtime_factory=lambda slot: _Runtime(slot, trigger_at="12:44"),
        ),
        dataset=dataset,
        family_id="family-test",
        matrix_id="matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        dataset_binding_revision=1,
        algorithm_implementation_digest=SHA,
        preflight_implementation_digest=SHA,
    )
    match = json.loads(
        (build.path / "slot-01" / "matches.jsonl").read_text().splitlines()[0]
    )
    assert match["entry_at"].endswith("T12:45:00+08:00")
    assert match["exit_at"].endswith("T13:30:00+08:00")


def test_a1_exact_1245_is_never_evaluated_as_signal(tmp_path: Path) -> None:
    bars = (
        _bar("2026-01-05T12:45:00"),
        _bar("2026-01-05T13:30:00"),
    )
    build = AtomicBenchmarkPreflightService(tmp_path).build(
        slots=_slots(
            _source_sha(bars),
            runtime_factory=lambda slot: _Runtime(slot, trigger_at="12:45"),
        ),
        dataset=_Dataset(bars),
        family_id="family-test",
        matrix_id="matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        dataset_binding_revision=1,
        algorithm_implementation_digest=SHA,
        preflight_implementation_digest=SHA,
    )
    assert [item["signal_count"] for item in build.slot_roots] == [0] * 7


def test_a1_common_mask_excludes_missing_anchor_before_runtime(tmp_path: Path) -> None:
    bars: list[ObservedBar] = []
    symbols = [f"{1000 + index}" for index in range(20)]
    excluded = symbols[-1]
    for symbol in symbols:
        bars.append(_bar("2026-01-05T09:01:00", symbol=symbol))
        if symbol != excluded:
            bars.append(_bar("2026-01-05T12:45:00", symbol=symbol))
        bars.append(_bar("2026-01-05T13:30:00", symbol=symbol))
    ordered = tuple(sorted(bars, key=lambda item: (item.timestamp, item.symbol)))
    runtimes = [_Runtime(slot, evaluated_symbols=[]) for slot in range(1, 8)]
    build = AtomicBenchmarkPreflightService(tmp_path).build(
        slots=_slots(_source_sha(ordered), runtime_factory=lambda slot: runtimes[slot - 1]),
        dataset=_Dataset(ordered),
        family_id="family-test",
        matrix_id="matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        dataset_binding_revision=1,
        algorithm_implementation_digest=SHA,
        preflight_implementation_digest=SHA,
    )
    eligibility = json.loads(
        (build.path / "eligibility" / "manifest.json").read_text()
    )
    assert eligibility["eligible_symbol_session_ratio"] == "0.950000000000000000"
    assert eligibility["missing_entry_reserve_count"] == 1
    assert [item["signal_count"] for item in build.slot_roots] == [19] * 7
    assert all(excluded not in runtime.evaluated_symbols for runtime in runtimes)
    assert all(runtime.begin_count == 1 for runtime in runtimes)


def test_a2_sparse_session_uses_last_observed_bar_before_deadline(
    tmp_path: Path,
) -> None:
    bars = (
        _bar("2026-01-05T09:01:00"),
        _bar("2026-01-05T12:44:00", open_price="101", close="101"),
        _bar("2026-01-05T13:30:00", open_price="102", close="103"),
    )
    dataset = _Dataset(bars)
    build = AtomicBenchmarkPreflightService(tmp_path).build(
        slots=_slots(
            _source_sha(bars),
            runtime_factory=lambda slot: _Runtime(slot, trigger_at="09:01"),
        ),
        dataset=dataset,
        family_id="family-test",
        matrix_id="matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        dataset_binding_revision=1,
        algorithm_implementation_digest=SHA,
        preflight_implementation_digest=SHA,
        matrix_revision=3,
    )
    row = json.loads(
        (build.path / "eligibility" / "rows.jsonl").read_text().splitlines()[0]
    )
    match = json.loads(
        (build.path / "slot-01" / "matches.jsonl").read_text().splitlines()[0]
    )
    assert build.manifest["matrix_revision"] == 3
    assert row["entry_reserve_at"].endswith("T12:44:00+08:00")
    assert row["signal_observation_count_before_reserve"] == 1
    assert row["eligibility_status"] == "ELIGIBLE"
    assert match["entry_at"].endswith("T12:44:00+08:00")
    assert match["exit_at"].endswith("T13:30:00+08:00")
    verify_preflight_artifact(build.path, expected_manifest=build.manifest)


def test_a2_dynamic_reserve_bar_is_never_evaluated_as_signal(
    tmp_path: Path,
) -> None:
    bars = (
        _bar("2026-01-05T09:01:00"),
        _bar("2026-01-05T12:44:00"),
        _bar("2026-01-05T13:30:00"),
    )
    dataset = _Dataset(bars)
    build = AtomicBenchmarkPreflightService(tmp_path).build(
        slots=_slots(
            _source_sha(bars),
            runtime_factory=lambda slot: _Runtime(slot, trigger_at="12:44"),
        ),
        dataset=dataset,
        family_id="family-test",
        matrix_id="matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        dataset_binding_revision=1,
        algorithm_implementation_digest=SHA,
        preflight_implementation_digest=SHA,
        matrix_revision=3,
    )
    assert [item["signal_count"] for item in build.slot_roots] == [0] * 7


def test_a2_common_mask_excludes_session_without_pre_reserve_observation(
    tmp_path: Path,
) -> None:
    bars: list[ObservedBar] = []
    symbols = [f"{2000 + index}" for index in range(20)]
    excluded = symbols[-1]
    for symbol in symbols:
        if symbol != excluded:
            bars.append(_bar("2026-01-05T09:01:00", symbol=symbol))
        bars.append(_bar("2026-01-05T12:44:00", symbol=symbol))
        bars.append(_bar("2026-01-05T13:30:00", symbol=symbol))
    ordered = tuple(sorted(bars, key=lambda item: (item.timestamp, item.symbol)))
    runtimes = [_Runtime(slot, evaluated_symbols=[]) for slot in range(1, 8)]
    build = AtomicBenchmarkPreflightService(tmp_path).build(
        slots=_slots(
            _source_sha(ordered),
            runtime_factory=lambda slot: runtimes[slot - 1],
        ),
        dataset=_Dataset(ordered),
        family_id="family-test",
        matrix_id="matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        dataset_binding_revision=1,
        algorithm_implementation_digest=SHA,
        preflight_implementation_digest=SHA,
        matrix_revision=3,
    )
    manifest = json.loads(
        (build.path / "eligibility" / "manifest.json").read_text()
    )
    assert manifest["eligible_symbol_session_ratio"] == "0.950000000000000000"
    assert manifest["missing_signal_observation_count"] == 1
    assert all(excluded not in runtime.evaluated_symbols for runtime in runtimes)


@pytest.mark.parametrize(
    ("missing_kind", "expected_field"),
    [
        ("entry", "missing_entry_reserve_count"),
        ("exit", "missing_terminal_exit_count"),
    ],
)
def test_a2_common_mask_excludes_missing_required_source_boundary(
    tmp_path: Path,
    missing_kind: str,
    expected_field: str,
) -> None:
    bars: list[ObservedBar] = []
    symbols = [f"{3000 + index}" for index in range(20)]
    excluded = symbols[-1]
    for symbol in symbols:
        if symbol == excluded and missing_kind == "entry":
            bars.append(_bar("2026-01-05T13:00:00", symbol=symbol))
        else:
            bars.append(_bar("2026-01-05T09:01:00", symbol=symbol))
            bars.append(_bar("2026-01-05T12:44:00", symbol=symbol))
        if symbol != excluded or missing_kind != "exit":
            bars.append(_bar("2026-01-05T13:30:00", symbol=symbol))
    ordered = tuple(sorted(bars, key=lambda item: (item.timestamp, item.symbol)))
    runtimes = [_Runtime(slot, evaluated_symbols=[]) for slot in range(1, 8)]
    build = AtomicBenchmarkPreflightService(tmp_path).build(
        slots=_slots(
            _source_sha(ordered),
            runtime_factory=lambda slot: runtimes[slot - 1],
        ),
        dataset=_Dataset(ordered),
        family_id="family-test",
        matrix_id="matrix-test",
        registration_digest=SHA,
        research_baseline_digest=SHA,
        protocol_core_digest=SHA,
        dataset_binding_revision=1,
        algorithm_implementation_digest=SHA,
        preflight_implementation_digest=SHA,
        matrix_revision=3,
    )
    manifest = json.loads(
        (build.path / "eligibility" / "manifest.json").read_text()
    )
    assert manifest["eligible_symbol_session_ratio"] == "0.950000000000000000"
    assert manifest[expected_field] == 1
    assert all(excluded not in runtime.evaluated_symbols for runtime in runtimes)


def test_a2_rejects_entry_reserve_after_deadline(tmp_path: Path) -> None:
    built = _build(tmp_path, matrix_revision=3)
    rows_path = built.path / "eligibility" / "rows.jsonl"
    row = json.loads(rows_path.read_text().splitlines()[0])
    row["entry_reserve_at"] = "2026-01-05T12:46:00+08:00"
    body = {key: value for key, value in row.items() if key != "eligibility_row_digest"}
    row["eligibility_row_digest"] = digest(body)
    rows_path.write_bytes(canonical_object_bytes(row))

    with pytest.raises(AtomicBenchmarkIntegrityError, match="anchor timestamp drift"):
        verify_preflight_artifact(built.path)


def test_a2_source_only_audit_uses_same_dynamic_reserve_semantics() -> None:
    bars = (
        _bar("2025-01-05T09:01:00"),
        _bar("2025-01-05T12:44:00"),
        _bar("2025-01-05T13:30:00"),
        _bar("2026-01-05T09:01:00"),
        _bar("2026-01-05T12:43:00"),
        _bar("2026-01-05T13:30:00"),
    )
    audit = AtomicBenchmarkEligibilityAuditService().audit(
        dataset=_Dataset(bars),
        audit_scope=_audit_scope(),
        matrix_revision=3,
    )

    assert audit["source_eof_verified"] is True
    assert audit["source_bar_count"] == len(bars)
    assert audit["observed_symbol_session_count"] == 2
    assert audit["eligible_symbol_session_count"] == 2
    assert audit["eligible_symbol_session_ratio"] == "1.000000000000000000"
    assert [item["year"] for item in audit["yearly"]] == [2025, 2026]
    assert audit["symbols"] == [
        {
            "symbol": "2330",
            "observed_symbol_session_count": 2,
            "eligible_symbol_session_count": 2,
            "eligible_symbol_session_ratio": "1.000000000000000000",
            "missing_entry_reserve_count": 0,
            "missing_signal_observation_count": 0,
            "missing_terminal_exit_count": 0,
        }
    ]
    assert len(audit["audit_digest"]) == 64


def test_a2_source_audit_and_preflight_share_exact_eligibility_projection(
    tmp_path: Path,
) -> None:
    bars: list[ObservedBar] = []
    symbols = [f"{6000 + index}" for index in range(40)]
    for index, symbol in enumerate(symbols):
        bars.append(_bar("2026-01-05T09:01:00", symbol=symbol))
        if index != 38:
            bars.append(_bar("2026-01-05T12:44:00", symbol=symbol))
        if index != 39:
            bars.append(_bar("2026-01-05T13:30:00", symbol=symbol))
    ordered = tuple(sorted(bars, key=lambda item: (item.timestamp, item.symbol)))
    audit = AtomicBenchmarkEligibilityAuditService().audit(
        dataset=_Dataset(ordered),
        audit_scope=_audit_scope(),
        matrix_revision=3,
    )
    build = _build(tmp_path, ordered, matrix_revision=3)
    manifest = json.loads(
        (build.path / "eligibility" / "manifest.json").read_text()
    )

    for field in (
        "observed_symbol_session_count",
        "eligible_symbol_session_count",
        "excluded_symbol_session_count",
        "eligible_symbol_session_ratio",
        "minimum_eligible_symbol_session_ratio",
        "missing_entry_reserve_count",
        "missing_signal_observation_count",
        "missing_terminal_exit_count",
    ):
        assert audit[field] == manifest[field]


def test_a2_protocol_is_additive_and_does_not_mutate_revision2() -> None:
    before = dict(PROTOCOL_CORE)
    candidate = amendment_a2_protocol_core()

    assert PROTOCOL_CORE == before
    assert PROTOCOL_CORE["schema_version"] == "r6-protocol-core-v2"
    assert candidate["schema_version"] == "r6-protocol-core-v3"
    assert candidate["entry_reserve_selection_semantics"].startswith(
        "LAST_OBSERVED_SAME_SYMBOL_KBAR"
    )
    assert "common_signal_cutoff_time" not in candidate
