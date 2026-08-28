"""Provider-free G3 full-Dataset preflight for seven atomic ENTRY slots.

The module owns only non-performance evidence.  It streams one registered
Dataset once, evaluates seven isolated runtimes, and atomically publishes one
directory containing seven ledgers and seven match plans.  It never creates an
attempt, computes P&L, or calls a market-data/broker boundary.
"""

from __future__ import annotations

import hashlib
import heapq
import json
import os
import shutil
import stat
import tempfile
from collections.abc import Callable, Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Context, Decimal, ROUND_HALF_EVEN
from pathlib import Path
from typing import Any, Protocol
from uuid import uuid4

from backtest.atomic_strategy_adapter import AtomicBacktestStrategyAdapter
from backtest.dataset import HistoricalDatasetCatalog
from backtest.dataset_binding import canonical_registration_manifest
from backtest.domain import HistoricalBar, canonical_json, digest
from backtest.strategies import StrategyContext

from .artifacts import (
    LEDGER_MANIFEST_SCHEMA,
    MATCH_MANIFEST_SCHEMA,
    verify_ledger_manifest,
    verify_match_manifest,
)
from .domain import (
    ALGORITHM_CONTRACT_DIGEST,
    LEDGER_ROW_SCHEMA,
    MATCH_ROW_SCHEMA,
    AtomicBenchmarkIntegrityError,
    FirstTriggerAdmission,
    ObservedBar,
    _make_match,
    canonical_object_bytes,
    verify_ledger_row,
    verify_match_row,
)


PREFLIGHT_MANIFEST_SCHEMA = "r6-preflight-manifest-v2"
PREFLIGHT_SLOT_ROOT_SCHEMA = "r6-preflight-slot-root-v2"
PREFLIGHT_MANIFEST_SCHEMA_V3 = "r6-preflight-manifest-v3"
PREFLIGHT_SLOT_ROOT_SCHEMA_V3 = "r6-preflight-slot-root-v3"
FEATURE_EVIDENCE_SCHEMA = "r6-feature-input-evidence-v1"
ELIGIBILITY_ROW_SCHEMA = "r6-session-eligibility-row-v1"
ELIGIBILITY_MANIFEST_SCHEMA = "r6-session-eligibility-manifest-v1"
ELIGIBILITY_ROW_SCHEMA_V2 = "r6-session-eligibility-row-v2"
ELIGIBILITY_MANIFEST_SCHEMA_V2 = "r6-session-eligibility-manifest-v2"
COMMON_SIGNAL_CUTOFF = time(12, 45)
REQUIRED_TERMINAL_EXIT = time(13, 30)
MINIMUM_ELIGIBLE_RATIO = Decimal("0.95")
_RATIO_CONTEXT = Context(prec=38, rounding=ROUND_HALF_EVEN)
_RATIO_QUANTUM = Decimal("0.000000000000000001")
_SORT_CHUNK_SIZE = 20_000
_PREFLIGHT_FIELDS = frozenset(
    {
        "schema_version",
        "family_id",
        "matrix_id",
        "matrix_revision",
        "registration_digest",
        "research_baseline_digest",
        "dataset_id",
        "dataset_digest",
        "dataset_bars_sha256",
        "dataset_bar_count",
        "dataset_binding_revision",
        "source_bar_count",
        "source_bars_sha256",
        "source_eof_verified",
        "protocol_core_digest",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
        "preflight_implementation_digest",
        "eligibility_manifest_digest",
        "slots",
        "preflight_digest",
    }
)
_SLOT_ROOT_FIELDS = frozenset(
    {
        "schema_version",
        "slot_sequence",
        "hypothesis_id",
        "eligibility_manifest_digest",
        "ledger_manifest_digest",
        "match_manifest_digest",
        "signal_count",
        "matched_count",
    }
)

_ELIGIBILITY_ROW_FIELDS = frozenset(
    {
        "schema_version",
        "sequence",
        "symbol",
        "session_date",
        "entry_reserve_at",
        "entry_reserve_bar_digest",
        "terminal_exit_at",
        "terminal_exit_bar_digest",
        "eligibility_status",
        "exclusion_reason_codes",
        "eligibility_row_digest",
    }
)
_ELIGIBILITY_ROW_FIELDS_V2 = frozenset(
    {
        *_ELIGIBILITY_ROW_FIELDS,
        "signal_observation_count_before_reserve",
    }
)
_ELIGIBILITY_MANIFEST_FIELDS = frozenset(
    {
        "schema_version",
        "dataset_id",
        "dataset_digest",
        "dataset_bars_sha256",
        "common_signal_cutoff_time",
        "entry_fill_deadline_time",
        "required_terminal_exit_time",
        "eligibility_row_schema_version",
        "observed_symbol_session_count",
        "eligible_symbol_session_count",
        "excluded_symbol_session_count",
        "missing_entry_reserve_count",
        "missing_terminal_exit_count",
        "eligible_symbol_session_ratio",
        "minimum_eligible_symbol_session_ratio",
        "eligibility_rows_sha256",
        "eligibility_manifest_digest",
    }
)
_ELIGIBILITY_MANIFEST_FIELDS_V2 = frozenset(
    {
        "schema_version",
        "dataset_id",
        "dataset_digest",
        "dataset_bars_sha256",
        "entry_reserve_selection_semantics",
        "signal_admission_comparator",
        "entry_fill_deadline_time",
        "required_terminal_exit_time",
        "eligibility_row_schema_version",
        "observed_symbol_session_count",
        "eligible_symbol_session_count",
        "excluded_symbol_session_count",
        "missing_entry_reserve_count",
        "missing_signal_observation_count",
        "missing_terminal_exit_count",
        "eligible_symbol_session_ratio",
        "minimum_eligible_symbol_session_ratio",
        "eligibility_rows_sha256",
        "eligibility_manifest_digest",
    }
)


class PreflightStrategyRuntime(Protocol):
    def reset_runtime(self) -> None: ...

    def begin_session(self, session_date: date) -> None: ...

    def evaluate_with_feature_evidence(
        self, context: StrategyContext
    ) -> tuple[Any, dict[str, object]]: ...


class PreflightDatasetStream(Protocol):
    source_bar_count: int
    source_bars_sha256: str
    source_eof_verified: bool

    @property
    def manifest(self) -> dict[str, object]: ...

    def iter_observed_bars(self) -> Iterator[ObservedBar]: ...


@dataclass(frozen=True)
class PreflightSlotRuntime:
    identity: dict[str, object]
    feature_request_identity_digest: str
    strategy: PreflightStrategyRuntime

    @property
    def slot_sequence(self) -> int:
        return int(self.identity["slot_sequence"])


@dataclass(frozen=True)
class AtomicBenchmarkPreflightBuild:
    manifest: dict[str, object]
    slot_roots: tuple[dict[str, object], ...]
    slot_manifests: tuple[dict[str, dict[str, object]], ...]
    path: Path

    @property
    def preflight_digest(self) -> str:
        return str(self.manifest["preflight_digest"])


@dataclass(frozen=True)
class SessionEligibilityDecision:
    symbol: str
    entry_reserve: ObservedBar | None
    terminal_exit: ObservedBar | None
    signal_observation_count_before_reserve: int
    exclusion_reason_codes: tuple[str, ...]

    @property
    def eligible(self) -> bool:
        return not self.exclusion_reason_codes


@dataclass
class _SessionEligibilityAccumulator:
    """Collect the one authoritative source projection for one session."""

    dynamic_reserve: bool

    def __post_init__(self) -> None:
        self.symbols: set[str] = set()
        self.anchors: dict[str, dict[str, ObservedBar]] = {}
        self.signal_observations_before_reserve: dict[str, int] = {}

    def observe(self, observed: ObservedBar) -> None:
        self.symbols.add(observed.symbol)
        bar_time = observed.timestamp.time().replace(tzinfo=None)
        entry_candidate = (
            self.dynamic_reserve and bar_time <= COMMON_SIGNAL_CUTOFF
        ) or (not self.dynamic_reserve and bar_time == COMMON_SIGNAL_CUTOFF)
        symbol_anchors = self.anchors.setdefault(observed.symbol, {})
        if entry_candidate:
            if self.dynamic_reserve and "entry" in symbol_anchors:
                self.signal_observations_before_reserve[observed.symbol] = (
                    self.signal_observations_before_reserve.get(observed.symbol, 0)
                    + 1
                )
                symbol_anchors["entry"] = observed
            elif "entry" in symbol_anchors:
                raise AtomicBenchmarkIntegrityError(
                    "G3 duplicate eligibility entry anchor"
                )
            else:
                symbol_anchors["entry"] = observed
        if bar_time == REQUIRED_TERMINAL_EXIT:
            if "exit" in symbol_anchors:
                raise AtomicBenchmarkIntegrityError(
                    "G3 duplicate eligibility terminal exit"
                )
            symbol_anchors["exit"] = observed

    def decisions(self) -> tuple[SessionEligibilityDecision, ...]:
        return _session_eligibility_decisions(
            symbols=tuple(self.symbols),
            anchors=self.anchors,
            signal_observations_before_reserve=(
                self.signal_observations_before_reserve
            ),
            dynamic_reserve=self.dynamic_reserve,
        )


def _session_eligibility_decisions(
    *,
    symbols: Sequence[str],
    anchors: Mapping[str, Mapping[str, ObservedBar]],
    signal_observations_before_reserve: Mapping[str, int],
    dynamic_reserve: bool,
) -> tuple[SessionEligibilityDecision, ...]:
    decisions = []
    for symbol in sorted(symbols):
        observed_anchors = anchors.get(symbol, {})
        entry = observed_anchors.get("entry")
        terminal = observed_anchors.get("exit")
        signal_count = signal_observations_before_reserve.get(symbol, 0)
        reasons = []
        if entry is None:
            reasons.append(
                "NO_ENTRY_RESERVE_AT_OR_BEFORE_12_45"
                if dynamic_reserve
                else "MISSING_ENTRY_RESERVE_12_45"
            )
        if dynamic_reserve and entry is not None and signal_count == 0:
            reasons.append("NO_SIGNAL_OBSERVATION_BEFORE_ENTRY_RESERVE")
        if terminal is None:
            reasons.append("MISSING_TERMINAL_EXIT_13_30")
        decisions.append(
            SessionEligibilityDecision(
                symbol=symbol,
                entry_reserve=entry,
                terminal_exit=terminal,
                signal_observation_count_before_reserve=signal_count,
                exclusion_reason_codes=tuple(reasons),
            )
        )
    return tuple(decisions)


class CanonicalAtomicDatasetAdapter:
    """Stream exact Dataset JSONL bytes once and retain only source evidence."""

    def __init__(
        self,
        *,
        root: Path,
        registered_manifest: Mapping[str, object],
        progress_every: int = 1_000_000,
        progress: Callable[[int, int], None] | None = None,
    ) -> None:
        if progress_every < 1:
            raise ValueError("progress_every must be positive")
        self._root = Path(root)
        self._manifest = canonical_registration_manifest(registered_manifest)
        self._progress_every = progress_every
        self._progress = progress
        local = HistoricalDatasetCatalog(self._root).get_manifest(
            str(self._manifest["dataset_id"])
        )
        if canonical_registration_manifest(local.to_dict()) != self._manifest:
            raise AtomicBenchmarkIntegrityError(
                "G3 local Dataset manifest differs from PostgreSQL registration"
            )
        if (
            self._manifest.get("storage_format") != "JSONL_FULL_V1"
            or self._manifest.get("payload_order") != "TIMESTAMP_SYMBOL"
        ):
            raise AtomicBenchmarkIntegrityError(
                "G3 requires timestamp-major canonical full Dataset"
            )
        self.source_bar_count = 0
        self.source_bars_sha256 = hashlib.sha256(b"").hexdigest()
        self.source_eof_verified = False

    @property
    def manifest(self) -> dict[str, object]:
        return dict(self._manifest)

    def iter_observed_bars(self) -> Iterator[ObservedBar]:
        dataset_id = str(self._manifest["dataset_id"])
        path = self._root / dataset_id / "bars.jsonl"
        if not path.is_file():
            raise AtomicBenchmarkIntegrityError("G3 Dataset bars.jsonl is missing")
        expected_count = int(self._manifest["bar_count"])
        checksum = hashlib.sha256()
        count = 0
        previous: tuple[object, str] | None = None
        with path.open("rb") as handle:
            for raw in handle:
                checksum.update(raw)
                if raw == b"\n" or not raw.endswith(b"\n"):
                    raise AtomicBenchmarkIntegrityError(
                        "G3 Dataset JSONL requires one non-empty row plus LF"
                    )
                source = raw[:-1]
                try:
                    parsed = json.loads(source)
                    bar = HistoricalBar.from_dict(parsed)
                except (UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError) as error:
                    raise AtomicBenchmarkIntegrityError(
                        "G3 Dataset bar cannot parse"
                    ) from error
                observed = ObservedBar(bar=bar, source_json=source)
                key = (observed.timestamp, observed.symbol)
                if previous is not None and key <= previous:
                    raise AtomicBenchmarkIntegrityError(
                        "G3 Dataset bars must be unique timestamp/symbol order"
                    )
                previous = key
                count += 1
                if self._progress is not None and count % self._progress_every == 0:
                    self._progress(count, expected_count)
                yield observed
        actual_sha = checksum.hexdigest()
        if count != expected_count:
            raise AtomicBenchmarkIntegrityError("G3 Dataset bar count drift")
        if actual_sha != self._manifest["bars_sha256"]:
            raise AtomicBenchmarkIntegrityError("G3 Dataset payload SHA drift")
        self.source_bar_count = count
        self.source_bars_sha256 = actual_sha
        self.source_eof_verified = True
        if self._progress is not None:
            self._progress(count, expected_count)


class AtomicBenchmarkEligibilityAuditService:
    """Scan source eligibility only; never evaluate strategies or mutate DB state."""

    def audit(
        self,
        *,
        dataset: PreflightDatasetStream,
        audit_scope: Mapping[str, object],
        matrix_revision: int = 3,
    ) -> dict[str, object]:
        if type(matrix_revision) is not int or matrix_revision not in {2, 3}:
            raise AtomicBenchmarkIntegrityError(
                "eligibility audit supports only matrix revisions 2 and 3"
            )
        dynamic_reserve = matrix_revision == 3
        scope = _verify_eligibility_audit_scope(audit_scope)
        current_session: date | None = None
        accumulator = _SessionEligibilityAccumulator(dynamic_reserve)
        totals = {
            "observed": 0,
            "eligible": 0,
            "missing_entry": 0,
            "missing_signal": 0,
            "missing_exit": 0,
        }
        yearly: dict[int, dict[str, int]] = {}
        by_symbol: dict[str, dict[str, int]] = {}

        def finish_session(session: date) -> None:
            decisions = accumulator.decisions()
            year = yearly.setdefault(
                session.year,
                {
                    "observed": 0,
                    "eligible": 0,
                    "missing_entry": 0,
                    "missing_signal": 0,
                    "missing_exit": 0,
                },
            )
            for decision in decisions:
                symbol_counts = by_symbol.setdefault(
                    decision.symbol,
                    {
                        "observed": 0,
                        "eligible": 0,
                        "missing_entry": 0,
                        "missing_signal": 0,
                        "missing_exit": 0,
                    },
                )
                totals["observed"] += 1
                year["observed"] += 1
                symbol_counts["observed"] += 1
                if decision.eligible:
                    totals["eligible"] += 1
                    year["eligible"] += 1
                    symbol_counts["eligible"] += 1
                if decision.entry_reserve is None:
                    totals["missing_entry"] += 1
                    year["missing_entry"] += 1
                    symbol_counts["missing_entry"] += 1
                if (
                    dynamic_reserve
                    and decision.entry_reserve is not None
                    and decision.signal_observation_count_before_reserve == 0
                ):
                    totals["missing_signal"] += 1
                    year["missing_signal"] += 1
                    symbol_counts["missing_signal"] += 1
                if decision.terminal_exit is None:
                    totals["missing_exit"] += 1
                    year["missing_exit"] += 1
                    symbol_counts["missing_exit"] += 1

        for observed in dataset.iter_observed_bars():
            session = observed.session_date
            if current_session is None or session > current_session:
                if current_session is not None:
                    finish_session(current_session)
                current_session = session
                accumulator = _SessionEligibilityAccumulator(dynamic_reserve)
            elif session < current_session:
                raise AtomicBenchmarkIntegrityError(
                    "eligibility audit session order regressed"
                )
            accumulator.observe(observed)
        if current_session is not None:
            finish_session(current_session)
        if not dataset.source_eof_verified:
            raise AtomicBenchmarkIntegrityError(
                "eligibility audit Dataset EOF was not verified"
            )
        if totals["observed"] == 0:
            raise AtomicBenchmarkIntegrityError(
                "eligibility audit has no symbol-session observations"
            )
        ratio = _RATIO_CONTEXT.divide(
            Decimal(totals["eligible"]), Decimal(totals["observed"])
        ).quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN)

        def year_projection(
            year_number: int, values: Mapping[str, int]
        ) -> dict[str, object]:
            year_ratio = _RATIO_CONTEXT.divide(
                Decimal(values["eligible"]), Decimal(values["observed"])
            ).quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN)
            return {
                "year": year_number,
                "observed_symbol_session_count": values["observed"],
                "eligible_symbol_session_count": values["eligible"],
                "eligible_symbol_session_ratio": format(year_ratio, ".18f"),
                "missing_entry_reserve_count": values["missing_entry"],
                "missing_signal_observation_count": values["missing_signal"],
                "missing_terminal_exit_count": values["missing_exit"],
            }

        def symbol_projection(
            symbol: str, values: Mapping[str, int]
        ) -> dict[str, object]:
            symbol_ratio = _RATIO_CONTEXT.divide(
                Decimal(values["eligible"]), Decimal(values["observed"])
            ).quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN)
            return {
                "symbol": symbol,
                "observed_symbol_session_count": values["observed"],
                "eligible_symbol_session_count": values["eligible"],
                "eligible_symbol_session_ratio": format(symbol_ratio, ".18f"),
                "missing_entry_reserve_count": values["missing_entry"],
                "missing_signal_observation_count": values["missing_signal"],
                "missing_terminal_exit_count": values["missing_exit"],
            }

        body = {
            "schema_version": "r6-eligibility-source-audit-v2",
            **scope,
            "matrix_revision_candidate": matrix_revision,
            "dataset_id": dataset.manifest["dataset_id"],
            "dataset_digest": dataset.manifest["manifest_digest"],
            "dataset_bars_sha256": dataset.manifest["bars_sha256"],
            "dataset_bar_count": dataset.manifest["bar_count"],
            "source_bar_count": dataset.source_bar_count,
            "source_bars_sha256": dataset.source_bars_sha256,
            "source_eof_verified": True,
            "entry_reserve_selection_semantics": (
                "LAST_OBSERVED_SAME_SYMBOL_KBAR_AT_OR_BEFORE_12_45_V1"
                if dynamic_reserve
                else "EXACT_SAME_SYMBOL_12_45_KBAR_V1"
            ),
            "required_terminal_exit_time": "13:30",
            "observed_symbol_session_count": totals["observed"],
            "eligible_symbol_session_count": totals["eligible"],
            "excluded_symbol_session_count": (
                totals["observed"] - totals["eligible"]
            ),
            "eligible_symbol_session_ratio": format(ratio, ".18f"),
            "minimum_eligible_symbol_session_ratio": "0.95",
            "missing_entry_reserve_count": totals["missing_entry"],
            "missing_signal_observation_count": totals["missing_signal"],
            "missing_terminal_exit_count": totals["missing_exit"],
            "yearly": [
                year_projection(year, yearly[year]) for year in sorted(yearly)
            ],
            "symbols": [
                symbol_projection(symbol, by_symbol[symbol])
                for symbol in sorted(by_symbol)
            ],
        }
        return verify_eligibility_audit(
            {**body, "audit_digest": digest(body)}
        )


_ELIGIBILITY_AUDIT_FIELDS = frozenset(
    {
        "schema_version",
        "family_id",
        "active_matrix_id",
        "active_matrix_revision",
        "active_matrix_registration_digest",
        "active_protocol_core_digest",
        "active_benchmark_build_binding_digest",
        "research_baseline_digest",
        "dataset_binding_revision",
        "family_head_sequence",
        "attempt_count",
        "candidate_protocol_core_digest",
        "candidate_eligibility_audit_implementation_digest",
        "matrix_revision_candidate",
        "dataset_id",
        "dataset_digest",
        "dataset_bars_sha256",
        "dataset_bar_count",
        "source_bar_count",
        "source_bars_sha256",
        "source_eof_verified",
        "entry_reserve_selection_semantics",
        "required_terminal_exit_time",
        "observed_symbol_session_count",
        "eligible_symbol_session_count",
        "excluded_symbol_session_count",
        "eligible_symbol_session_ratio",
        "minimum_eligible_symbol_session_ratio",
        "missing_entry_reserve_count",
        "missing_signal_observation_count",
        "missing_terminal_exit_count",
        "yearly",
        "symbols",
        "audit_digest",
    }
)
_ELIGIBILITY_AUDIT_SCOPE_FIELDS = frozenset(
    {
        "family_id",
        "active_matrix_id",
        "active_matrix_revision",
        "active_matrix_registration_digest",
        "active_protocol_core_digest",
        "active_benchmark_build_binding_digest",
        "research_baseline_digest",
        "dataset_binding_revision",
        "family_head_sequence",
        "attempt_count",
        "candidate_protocol_core_digest",
        "candidate_eligibility_audit_implementation_digest",
    }
)
_ELIGIBILITY_AUDIT_YEAR_FIELDS = frozenset(
    {
        "year",
        "observed_symbol_session_count",
        "eligible_symbol_session_count",
        "eligible_symbol_session_ratio",
        "missing_entry_reserve_count",
        "missing_signal_observation_count",
        "missing_terminal_exit_count",
    }
)
_ELIGIBILITY_AUDIT_SYMBOL_FIELDS = frozenset(
    {
        "symbol",
        "observed_symbol_session_count",
        "eligible_symbol_session_count",
        "eligible_symbol_session_ratio",
        "missing_entry_reserve_count",
        "missing_signal_observation_count",
        "missing_terminal_exit_count",
    }
)


def _verify_eligibility_audit_scope(
    value: Mapping[str, object],
) -> dict[str, object]:
    scope = dict(value)
    if frozenset(scope) != _ELIGIBILITY_AUDIT_SCOPE_FIELDS:
        raise AtomicBenchmarkIntegrityError("eligibility audit scope fields drift")
    for field in ("family_id", "active_matrix_id"):
        if not isinstance(scope[field], str) or not scope[field]:
            raise AtomicBenchmarkIntegrityError(
                f"eligibility audit scope invalid: {field}"
            )
    for field in (
        "active_matrix_registration_digest",
        "active_protocol_core_digest",
        "active_benchmark_build_binding_digest",
        "research_baseline_digest",
        "candidate_protocol_core_digest",
        "candidate_eligibility_audit_implementation_digest",
    ):
        _sha256_text(scope[field], field)
    if (
        type(scope["active_matrix_revision"]) is not int
        or scope["active_matrix_revision"] != 2
        or type(scope["dataset_binding_revision"]) is not int
        or scope["dataset_binding_revision"] < 1
        or type(scope["family_head_sequence"]) is not int
        or scope["family_head_sequence"] != 0
        or type(scope["attempt_count"]) is not int
        or scope["attempt_count"] != 0
    ):
        raise AtomicBenchmarkIntegrityError("eligibility audit scope state drift")
    return scope


def verify_eligibility_audit(
    value: Mapping[str, object],
    *,
    expected_scope: Mapping[str, object] | None = None,
) -> dict[str, object]:
    audit = dict(value)
    if frozenset(audit) != _ELIGIBILITY_AUDIT_FIELDS:
        raise AtomicBenchmarkIntegrityError("eligibility audit fields drift")
    if (
        audit["schema_version"] != "r6-eligibility-source-audit-v2"
        or audit["matrix_revision_candidate"] != 3
        or audit["source_eof_verified"] is not True
        or audit["entry_reserve_selection_semantics"]
        != "LAST_OBSERVED_SAME_SYMBOL_KBAR_AT_OR_BEFORE_12_45_V1"
        or audit["required_terminal_exit_time"] != "13:30"
        or audit["minimum_eligible_symbol_session_ratio"] != "0.95"
    ):
        raise AtomicBenchmarkIntegrityError("eligibility audit contract drift")
    stored_scope = _verify_eligibility_audit_scope(
        {field: audit[field] for field in _ELIGIBILITY_AUDIT_SCOPE_FIELDS}
    )
    if expected_scope is not None and stored_scope != _verify_eligibility_audit_scope(
        expected_scope
    ):
        raise AtomicBenchmarkIntegrityError("eligibility audit scope conflict")
    if not isinstance(audit["dataset_id"], str) or not audit["dataset_id"]:
        raise AtomicBenchmarkIntegrityError("eligibility audit Dataset ID drift")
    for field in (
        "dataset_digest",
        "dataset_bars_sha256",
        "source_bars_sha256",
        "audit_digest",
    ):
        _sha256_text(audit[field], field)
    count_fields = (
        "dataset_bar_count",
        "source_bar_count",
        "observed_symbol_session_count",
        "eligible_symbol_session_count",
        "excluded_symbol_session_count",
        "missing_entry_reserve_count",
        "missing_signal_observation_count",
        "missing_terminal_exit_count",
    )
    for field in count_fields:
        if type(audit[field]) is not int or audit[field] < 0:
            raise AtomicBenchmarkIntegrityError(
                f"eligibility audit count invalid: {field}"
            )
    if (
        audit["dataset_bar_count"] != audit["source_bar_count"]
        or audit["dataset_bars_sha256"] != audit["source_bars_sha256"]
        or audit["observed_symbol_session_count"]
        != audit["eligible_symbol_session_count"]
        + audit["excluded_symbol_session_count"]
    ):
        raise AtomicBenchmarkIntegrityError("eligibility audit totals drift")
    if audit["observed_symbol_session_count"] == 0:
        raise AtomicBenchmarkIntegrityError("eligibility audit observations missing")

    def verified_ratio(eligible: int, observed: int, raw: object) -> Decimal:
        if not isinstance(raw, str):
            raise AtomicBenchmarkIntegrityError("eligibility audit ratio type drift")
        try:
            value = Decimal(raw)
        except Exception as error:
            raise AtomicBenchmarkIntegrityError(
                "eligibility audit ratio is invalid"
            ) from error
        expected = _RATIO_CONTEXT.divide(
            Decimal(eligible), Decimal(observed)
        ).quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN)
        if value != expected or raw != format(expected, ".18f"):
            raise AtomicBenchmarkIntegrityError("eligibility audit ratio drift")
        return value

    verified_ratio(
        audit["eligible_symbol_session_count"],
        audit["observed_symbol_session_count"],
        audit["eligible_symbol_session_ratio"],
    )
    yearly = audit["yearly"]
    if not isinstance(yearly, list) or not yearly:
        raise AtomicBenchmarkIntegrityError("eligibility audit yearly rows missing")
    previous_year = 0
    year_observed = year_eligible = 0
    year_missing_entry = year_missing_signal = year_missing_exit = 0
    for item in yearly:
        if not isinstance(item, Mapping) or frozenset(item) != _ELIGIBILITY_AUDIT_YEAR_FIELDS:
            raise AtomicBenchmarkIntegrityError("eligibility audit year fields drift")
        year = item["year"]
        observed = item["observed_symbol_session_count"]
        eligible = item["eligible_symbol_session_count"]
        if (
            type(year) is not int
            or year <= previous_year
            or type(observed) is not int
            or observed <= 0
            or type(eligible) is not int
            or eligible < 0
            or eligible > observed
        ):
            raise AtomicBenchmarkIntegrityError("eligibility audit year identity drift")
        for field in (
            "missing_entry_reserve_count",
            "missing_signal_observation_count",
            "missing_terminal_exit_count",
        ):
            if type(item[field]) is not int or item[field] < 0:
                raise AtomicBenchmarkIntegrityError(
                    "eligibility audit year count drift"
                )
        verified_ratio(eligible, observed, item["eligible_symbol_session_ratio"])
        previous_year = year
        year_observed += observed
        year_eligible += eligible
        year_missing_entry += item["missing_entry_reserve_count"]
        year_missing_signal += item["missing_signal_observation_count"]
        year_missing_exit += item["missing_terminal_exit_count"]
    if (
        year_observed != audit["observed_symbol_session_count"]
        or year_eligible != audit["eligible_symbol_session_count"]
        or year_missing_entry != audit["missing_entry_reserve_count"]
        or year_missing_signal != audit["missing_signal_observation_count"]
        or year_missing_exit != audit["missing_terminal_exit_count"]
    ):
        raise AtomicBenchmarkIntegrityError("eligibility audit yearly totals drift")
    symbols = audit["symbols"]
    if not isinstance(symbols, list) or not symbols:
        raise AtomicBenchmarkIntegrityError("eligibility audit symbol rows missing")
    previous_symbol = ""
    symbol_observed = symbol_eligible = 0
    symbol_missing_entry = symbol_missing_signal = symbol_missing_exit = 0
    for item in symbols:
        if (
            not isinstance(item, Mapping)
            or frozenset(item) != _ELIGIBILITY_AUDIT_SYMBOL_FIELDS
        ):
            raise AtomicBenchmarkIntegrityError(
                "eligibility audit symbol fields drift"
            )
        symbol = item["symbol"]
        observed = item["observed_symbol_session_count"]
        eligible = item["eligible_symbol_session_count"]
        if (
            not isinstance(symbol, str)
            or not symbol
            or symbol <= previous_symbol
            or type(observed) is not int
            or observed <= 0
            or type(eligible) is not int
            or eligible < 0
            or eligible > observed
        ):
            raise AtomicBenchmarkIntegrityError(
                "eligibility audit symbol identity drift"
            )
        for field in (
            "missing_entry_reserve_count",
            "missing_signal_observation_count",
            "missing_terminal_exit_count",
        ):
            if type(item[field]) is not int or item[field] < 0:
                raise AtomicBenchmarkIntegrityError(
                    "eligibility audit symbol count drift"
                )
        verified_ratio(eligible, observed, item["eligible_symbol_session_ratio"])
        previous_symbol = symbol
        symbol_observed += observed
        symbol_eligible += eligible
        symbol_missing_entry += item["missing_entry_reserve_count"]
        symbol_missing_signal += item["missing_signal_observation_count"]
        symbol_missing_exit += item["missing_terminal_exit_count"]
    if (
        symbol_observed != audit["observed_symbol_session_count"]
        or symbol_eligible != audit["eligible_symbol_session_count"]
        or symbol_missing_entry != audit["missing_entry_reserve_count"]
        or symbol_missing_signal != audit["missing_signal_observation_count"]
        or symbol_missing_exit != audit["missing_terminal_exit_count"]
    ):
        raise AtomicBenchmarkIntegrityError("eligibility audit symbol totals drift")
    body = dict(audit)
    stored = body.pop("audit_digest")
    if digest(body) != stored:
        raise AtomicBenchmarkIntegrityError("eligibility audit digest drift")
    canonical_object_bytes(audit)
    return audit


@dataclass
class _DayState:
    session_open: Decimal
    cumulative_volume: int = 0
    cumulative_amount: Decimal = Decimal("0")
    session_high: Decimal | None = None
    bars_seen: int = 0

    def update(self, bar: HistoricalBar) -> Decimal:
        self.cumulative_volume += bar.volume
        self.cumulative_amount += (
            bar.amount if bar.amount is not None else bar.close * bar.volume
        )
        self.bars_seen += 1
        self.session_high = (
            bar.high if self.session_high is None else max(self.session_high, bar.high)
        )
        if self.cumulative_volume <= 0:
            return bar.close
        return self.cumulative_amount / self.cumulative_volume


@dataclass
class _ActiveMatch:
    signal: dict[str, object]
    entry: ObservedBar
    latest: ObservedBar | None = None


class _ExternalMultiplicity:
    """Build the frozen parity projection with bounded in-memory chunks."""

    def __init__(self, directory: Path, label: str) -> None:
        self._directory = directory
        self._spool_path = directory / f".{label}.tokens"
        self._handle = self._spool_path.open("xb")

    @staticmethod
    def _token(row: Mapping[str, object]) -> str:
        return canonical_json(
            {
                "sequence": row["sequence"],
                "signal_id": row["signal_id"],
                "semantic_key": row["semantic_key"],
            }
        )

    def add(self, row: Mapping[str, object]) -> None:
        self._handle.write(self._token(row).encode("utf-8") + b"\n")

    def close(self) -> None:
        if not self._handle.closed:
            self._handle.flush()
            os.fsync(self._handle.fileno())
            self._handle.close()

    def finish(self) -> tuple[str, int, int]:
        self.close()
        chunk_paths: list[Path] = []
        try:
            with self._spool_path.open("r", encoding="utf-8", newline="") as source:
                while True:
                    values = []
                    for _ in range(_SORT_CHUNK_SIZE):
                        line = source.readline()
                        if not line:
                            break
                        if not line.endswith("\n"):
                            raise AtomicBenchmarkIntegrityError(
                                "G3 parity token spool is incomplete"
                            )
                        values.append(line[:-1])
                    if not values:
                        break
                    values.sort()
                    chunk = self._directory / f".tokens-{len(chunk_paths):05d}.sorted"
                    with chunk.open("x", encoding="utf-8", newline="") as output:
                        for value in values:
                            output.write(value + "\n")
                        output.flush()
                        os.fsync(output.fileno())
                    chunk_paths.append(chunk)

            handles = [path.open("r", encoding="utf-8", newline="") for path in chunk_paths]
            try:
                streams = ((line[:-1] for line in handle) for handle in handles)
                merged = heapq.merge(*streams)
                checksum = hashlib.sha256()
                checksum.update(
                    b'{"schema_version":"r6-layer-parity-projection-v1","tokens":{'
                )
                previous: str | None = None
                multiplicity = 0
                total = 0
                duplicate_count = 0
                first = True

                def emit(token: str, count: int) -> None:
                    nonlocal first
                    if not first:
                        checksum.update(b",")
                    first = False
                    checksum.update(
                        json.dumps(
                            token,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        ).encode("utf-8")
                    )
                    checksum.update(b":")
                    checksum.update(str(count).encode("ascii"))

                for token in merged:
                    total += 1
                    if token == previous:
                        multiplicity += 1
                        duplicate_count += 1
                        continue
                    if previous is not None:
                        emit(previous, multiplicity)
                    previous = token
                    multiplicity = 1
                if previous is not None:
                    emit(previous, multiplicity)
                checksum.update(b"}}")
                return checksum.hexdigest(), duplicate_count, total
            finally:
                for handle in handles:
                    handle.close()
        finally:
            self._spool_path.unlink(missing_ok=True)
            for path in chunk_paths:
                path.unlink(missing_ok=True)


def _write_canonical(path: Path, value: Mapping[str, object]) -> None:
    payload = canonical_object_bytes(value)
    with path.open("xb") as handle:
        handle.write(payload)
        handle.flush()
        os.fsync(handle.fileno())


def _sha256_text(value: object, label: str) -> str:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise AtomicBenchmarkIntegrityError(f"{label} must be lowercase SHA-256")
    return value


def verify_eligibility_row(value: Mapping[str, object]) -> dict[str, object]:
    row = dict(value)
    schema = row.get("schema_version")
    is_dynamic_reserve = schema == ELIGIBILITY_ROW_SCHEMA_V2
    expected_fields = (
        _ELIGIBILITY_ROW_FIELDS_V2
        if is_dynamic_reserve
        else _ELIGIBILITY_ROW_FIELDS
    )
    if frozenset(row) != expected_fields:
        raise AtomicBenchmarkIntegrityError("eligibility row fields drift")
    if schema not in {ELIGIBILITY_ROW_SCHEMA, ELIGIBILITY_ROW_SCHEMA_V2}:
        raise AtomicBenchmarkIntegrityError("eligibility row schema drift")
    if type(row["sequence"]) is not int or row["sequence"] < 1:
        raise AtomicBenchmarkIntegrityError("eligibility sequence is invalid")
    if not isinstance(row["symbol"], str) or not row["symbol"]:
        raise AtomicBenchmarkIntegrityError("eligibility symbol is invalid")
    try:
        if date.fromisoformat(str(row["session_date"])).isoformat() != row["session_date"]:
            raise ValueError
    except ValueError as error:
        raise AtomicBenchmarkIntegrityError("eligibility session date is invalid") from error
    reasons = row["exclusion_reason_codes"]
    if not isinstance(reasons, list) or any(not isinstance(item, str) for item in reasons):
        raise AtomicBenchmarkIntegrityError("eligibility reasons are invalid")
    allowed_reasons = (
        [
            "NO_ENTRY_RESERVE_AT_OR_BEFORE_12_45",
            "NO_SIGNAL_OBSERVATION_BEFORE_ENTRY_RESERVE",
            "MISSING_TERMINAL_EXIT_13_30",
        ]
        if is_dynamic_reserve
        else [
            "MISSING_ENTRY_RESERVE_12_45",
            "MISSING_TERMINAL_EXIT_13_30",
        ]
    )
    if reasons != [item for item in allowed_reasons if item in reasons]:
        raise AtomicBenchmarkIntegrityError("eligibility reason order is invalid")
    pairs = (
        ("entry_reserve_at", "entry_reserve_bar_digest", COMMON_SIGNAL_CUTOFF),
        ("terminal_exit_at", "terminal_exit_bar_digest", REQUIRED_TERMINAL_EXIT),
    )
    for timestamp_field, digest_field, boundary_time in pairs:
        timestamp = row[timestamp_field]
        bar_digest = row[digest_field]
        if (timestamp is None) != (bar_digest is None):
            raise AtomicBenchmarkIntegrityError("eligibility anchor pair is incomplete")
        if timestamp is not None:
            try:
                parsed = datetime.fromisoformat(str(timestamp))
            except ValueError as error:
                raise AtomicBenchmarkIntegrityError("eligibility anchor timestamp invalid") from error
            time_matches = (
                parsed.time().replace(tzinfo=None) <= boundary_time
                if is_dynamic_reserve and timestamp_field == "entry_reserve_at"
                else parsed.time().replace(tzinfo=None) == boundary_time
            )
            if (
                parsed.isoformat(timespec="seconds") != timestamp
                or parsed.utcoffset() is None
                or parsed.utcoffset().total_seconds() != 8 * 3600
                or parsed.date().isoformat() != row["session_date"]
                or not time_matches
            ):
                raise AtomicBenchmarkIntegrityError("eligibility anchor timestamp drift")
            _sha256_text(bar_digest, digest_field)
    expected_reasons = []
    if row["entry_reserve_at"] is None:
        expected_reasons.append(
            "NO_ENTRY_RESERVE_AT_OR_BEFORE_12_45"
            if is_dynamic_reserve
            else "MISSING_ENTRY_RESERVE_12_45"
        )
    if is_dynamic_reserve:
        signal_observations = row["signal_observation_count_before_reserve"]
        if type(signal_observations) is not int or signal_observations < 0:
            raise AtomicBenchmarkIntegrityError(
                "eligibility signal observation count is invalid"
            )
        if row["entry_reserve_at"] is None and signal_observations != 0:
            raise AtomicBenchmarkIntegrityError(
                "eligibility signal observations require an entry reserve"
            )
        if row["entry_reserve_at"] is not None and signal_observations == 0:
            expected_reasons.append("NO_SIGNAL_OBSERVATION_BEFORE_ENTRY_RESERVE")
    if row["terminal_exit_at"] is None:
        expected_reasons.append("MISSING_TERMINAL_EXIT_13_30")
    expected_status = "ELIGIBLE" if not expected_reasons else "EXCLUDED"
    if row["eligibility_status"] != expected_status or reasons != expected_reasons:
        raise AtomicBenchmarkIntegrityError("eligibility status/reasons drift")
    _sha256_text(row["eligibility_row_digest"], "eligibility_row_digest")
    body = {key: item for key, item in row.items() if key != "eligibility_row_digest"}
    if digest(body) != row["eligibility_row_digest"]:
        raise AtomicBenchmarkIntegrityError("eligibility row digest drift")
    canonical_object_bytes(row)
    return row


def verify_eligibility_manifest(value: Mapping[str, object]) -> dict[str, object]:
    manifest = dict(value)
    schema = manifest.get("schema_version")
    is_dynamic_reserve = schema == ELIGIBILITY_MANIFEST_SCHEMA_V2
    expected_fields = (
        _ELIGIBILITY_MANIFEST_FIELDS_V2
        if is_dynamic_reserve
        else _ELIGIBILITY_MANIFEST_FIELDS
    )
    if frozenset(manifest) != expected_fields:
        raise AtomicBenchmarkIntegrityError("eligibility manifest fields drift")
    if is_dynamic_reserve:
        contract_valid = (
            manifest["eligibility_row_schema_version"]
            == ELIGIBILITY_ROW_SCHEMA_V2
            and manifest["entry_reserve_selection_semantics"]
            == "LAST_OBSERVED_SAME_SYMBOL_KBAR_AT_OR_BEFORE_12_45_V1"
            and manifest["signal_admission_comparator"]
            == "STRICT_LT_ENTRY_RESERVE_AT"
            and manifest["entry_fill_deadline_time"] == "12:45"
            and manifest["required_terminal_exit_time"] == "13:30"
            and manifest["minimum_eligible_symbol_session_ratio"] == "0.95"
        )
    else:
        contract_valid = (
            schema == ELIGIBILITY_MANIFEST_SCHEMA
            and manifest["eligibility_row_schema_version"]
            == ELIGIBILITY_ROW_SCHEMA
            and manifest["common_signal_cutoff_time"] == "12:45"
            and manifest["entry_fill_deadline_time"] == "12:45"
            and manifest["required_terminal_exit_time"] == "13:30"
            and manifest["minimum_eligible_symbol_session_ratio"] == "0.95"
        )
    if not contract_valid:
        raise AtomicBenchmarkIntegrityError("eligibility manifest contract drift")
    for field in (
        "dataset_digest",
        "dataset_bars_sha256",
        "eligibility_rows_sha256",
        "eligibility_manifest_digest",
    ):
        _sha256_text(manifest[field], field)
    count_fields = (
        "observed_symbol_session_count",
        "eligible_symbol_session_count",
        "excluded_symbol_session_count",
        "missing_entry_reserve_count",
        "missing_terminal_exit_count",
    )
    if is_dynamic_reserve:
        count_fields = (*count_fields, "missing_signal_observation_count")
    for field in count_fields:
        if type(manifest[field]) is not int or manifest[field] < 0:
            raise AtomicBenchmarkIntegrityError(f"eligibility count invalid: {field}")
    if manifest["observed_symbol_session_count"] != (
        manifest["eligible_symbol_session_count"]
        + manifest["excluded_symbol_session_count"]
    ):
        raise AtomicBenchmarkIntegrityError("eligibility counts cannot reconcile")
    ratio = manifest["eligible_symbol_session_ratio"]
    if not isinstance(ratio, str):
        raise AtomicBenchmarkIntegrityError("eligibility ratio must be Decimal text")
    try:
        parsed_ratio = Decimal(ratio)
    except Exception as error:
        raise AtomicBenchmarkIntegrityError("eligibility ratio is invalid") from error
    if (
        not parsed_ratio.is_finite()
        or parsed_ratio.as_tuple().exponent != -18
        or parsed_ratio < 0
        or parsed_ratio > 1
    ):
        raise AtomicBenchmarkIntegrityError("eligibility ratio is not canonical")
    body = dict(manifest)
    stored = body.pop("eligibility_manifest_digest")
    if digest(body) != stored:
        raise AtomicBenchmarkIntegrityError("eligibility manifest digest drift")
    canonical_object_bytes(manifest)
    return manifest


def _ledger_manifest_from_evidence(
    *,
    identity: Mapping[str, object],
    signal_count: int,
    rows_sha256: str,
    multiplicity_digest: str,
    eligibility_manifest_digest: str,
) -> dict[str, object]:
    body = {
        "schema_version": LEDGER_MANIFEST_SCHEMA,
        **dict(identity),
        "ledger_row_schema_version": LEDGER_ROW_SCHEMA,
        "ledger_signal_count": signal_count,
        "ledger_rows_sha256": rows_sha256,
        "ledger_signal_multiplicity_digest": multiplicity_digest,
        "eligibility_manifest_digest": eligibility_manifest_digest,
    }
    return verify_ledger_manifest({**body, "ledger_manifest_digest": digest(body)})


def _match_manifest_from_evidence(
    *,
    ledger: Mapping[str, object],
    matched_count: int,
    missing_entry_count: int,
    missing_exit_count: int,
    duplicate_match_count: int,
    rows_sha256: str,
    multiplicity_digest: str,
) -> dict[str, object]:
    body = {
        "schema_version": MATCH_MANIFEST_SCHEMA,
        **{
            field: ledger[field]
            for field in (
                "matrix_id",
                "registration_digest",
                "family_id",
                "research_baseline_digest",
                "slot_sequence",
                "hypothesis_id",
                "strategy_id",
                "strategy_version_id",
                "strategy_configuration_digest",
                "strategy_implementation_digest",
                "lifecycle_sequence",
                "lifecycle_event_id",
                "lifecycle_projection_digest",
                "dataset_id",
                "dataset_digest",
                "dataset_bars_sha256",
                "dataset_binding_revision",
                "protocol_core_digest",
                "algorithm_contract_digest",
                "algorithm_implementation_digest",
            )
        },
        "ledger_manifest_digest": ledger["ledger_manifest_digest"],
        "ledger_rows_sha256": ledger["ledger_rows_sha256"],
        "match_row_schema_version": MATCH_ROW_SCHEMA,
        "signal_count": ledger["ledger_signal_count"],
        "matched_entry_count": matched_count,
        "matched_exit_count": matched_count,
        "missing_entry_count": missing_entry_count,
        "missing_exit_count": missing_exit_count,
        "duplicate_match_count": duplicate_match_count,
        "match_rows_sha256": rows_sha256,
        "match_signal_multiplicity_digest": multiplicity_digest,
        "eligibility_manifest_digest": ledger["eligibility_manifest_digest"],
    }
    return verify_match_manifest({**body, "match_manifest_digest": digest(body)})


class _SlotWriter:
    def __init__(
        self,
        *,
        directory: Path,
        identity: Mapping[str, object],
    ) -> None:
        self.directory = directory
        self.identity = dict(identity)
        self.admission = FirstTriggerAdmission()
        self.waiting: dict[str, dict[str, object]] = {}
        self.active: dict[str, _ActiveMatch] = {}
        self.ledger_count = 0
        self.match_count = 0
        self.missing_entry_count = 0
        self.missing_exit_count = 0
        self._ledger_sha = hashlib.sha256()
        self._match_sha = hashlib.sha256()
        directory.mkdir(parents=True, exist_ok=False)
        self._ledger = (directory / "ledger.jsonl").open("xb")
        self._matches = (directory / "matches.jsonl").open("xb")
        self._ledger_tokens = _ExternalMultiplicity(directory, "ledger")
        self._match_tokens = _ExternalMultiplicity(directory, "match")

    def before_evaluation(self, bar: ObservedBar) -> None:
        active = self.active.get(bar.symbol)
        if active is not None:
            active.latest = bar
        waiting = self.waiting.pop(bar.symbol, None)
        if waiting is not None:
            self.active[bar.symbol] = _ActiveMatch(waiting, bar)

    def add_signal(self, row: Mapping[str, object]) -> None:
        verified = verify_ledger_row(row)
        if verified["sequence"] != self.ledger_count + 1:
            raise AtomicBenchmarkIntegrityError("G3 ledger sequence drift")
        if verified["symbol"] in self.waiting or verified["symbol"] in self.active:
            raise AtomicBenchmarkIntegrityError("G3 duplicate slot/symbol signal")
        payload = canonical_object_bytes(verified)
        self._ledger.write(payload)
        self._ledger_sha.update(payload)
        self._ledger_tokens.add(verified)
        self.ledger_count += 1
        self.waiting[str(verified["symbol"])] = verified

    def finish_session(self) -> None:
        if self.waiting:
            self.missing_entry_count += len(self.waiting)
            missing_sequences = sorted(
                int(item["sequence"]) for item in self.waiting.values()
            )
            self.waiting.clear()
            raise AtomicBenchmarkIntegrityError(
                "G3 incomplete match coverage: "
                f"slot={self.identity['slot_sequence']} "
                f"missing_entry_sequences={missing_sequences}"
            )
        for item in sorted(
            self.active.values(), key=lambda value: int(value.signal["sequence"])
        ):
            if item.latest is None:
                self.missing_exit_count += 1
                raise AtomicBenchmarkIntegrityError(
                    "G3 incomplete match coverage: "
                    f"slot={self.identity['slot_sequence']} "
                    f"missing_exit_sequence={item.signal['sequence']}"
                )
            if (
                item.entry.timestamp.time().replace(tzinfo=None) > COMMON_SIGNAL_CUTOFF
                or item.latest.timestamp.time().replace(tzinfo=None)
                != REQUIRED_TERMINAL_EXIT
            ):
                raise AtomicBenchmarkIntegrityError(
                    "G3 entry/terminal-exit boundary drift"
                )
            row = _make_match(item.signal, item.entry, item.latest)
            if row["sequence"] != self.match_count + 1:
                raise AtomicBenchmarkIntegrityError("G3 match sequence drift")
            payload = canonical_object_bytes(row)
            self._matches.write(payload)
            self._match_sha.update(payload)
            self._match_tokens.add(row)
            self.match_count += 1
        self.active.clear()

    def finalize(
        self, *, eligibility_manifest_digest: str
    ) -> tuple[dict[str, object], dict[str, object]]:
        self.finish_session()
        for handle in (self._ledger, self._matches):
            handle.flush()
            os.fsync(handle.fileno())
            handle.close()
        ledger_multiplicity, ledger_duplicates, ledger_tokens = (
            self._ledger_tokens.finish()
        )
        match_multiplicity, match_duplicates, match_tokens = self._match_tokens.finish()
        if ledger_duplicates != 0 or match_duplicates != 0:
            raise AtomicBenchmarkIntegrityError("G3 duplicate parity token")
        if ledger_tokens != self.ledger_count or match_tokens != self.match_count:
            raise AtomicBenchmarkIntegrityError("G3 parity token count drift")
        ledger_manifest = _ledger_manifest_from_evidence(
            identity=self.identity,
            signal_count=self.ledger_count,
            rows_sha256=self._ledger_sha.hexdigest(),
            multiplicity_digest=ledger_multiplicity,
            eligibility_manifest_digest=eligibility_manifest_digest,
        )
        match_manifest = _match_manifest_from_evidence(
            ledger=ledger_manifest,
            matched_count=self.match_count,
            missing_entry_count=self.missing_entry_count,
            missing_exit_count=self.missing_exit_count,
            duplicate_match_count=match_duplicates,
            rows_sha256=self._match_sha.hexdigest(),
            multiplicity_digest=match_multiplicity,
        )
        if (
            self.missing_entry_count != 0
            or self.missing_exit_count != 0
            or ledger_multiplicity != match_multiplicity
        ):
            raise AtomicBenchmarkIntegrityError(
                "G3 ledger/match coverage or parity is incomplete"
            )
        _write_canonical(self.directory / "ledger_manifest.json", ledger_manifest)
        _write_canonical(self.directory / "match_manifest.json", match_manifest)
        return ledger_manifest, match_manifest

    def close(self) -> None:
        for handle in (self._ledger, self._matches):
            if not handle.closed:
                handle.close()
        self._ledger_tokens.close()
        self._match_tokens.close()


class AtomicBenchmarkPreflightService:
    """Evaluate seven isolated runtimes in one canonical Dataset traversal."""

    def __init__(self, artifact_root: Path) -> None:
        self._artifact_root = Path(artifact_root)

    def build(
        self,
        *,
        slots: Sequence[PreflightSlotRuntime],
        dataset: PreflightDatasetStream,
        family_id: str,
        matrix_id: str,
        registration_digest: str,
        research_baseline_digest: str,
        protocol_core_digest: str,
        dataset_binding_revision: int,
        algorithm_implementation_digest: str,
        preflight_implementation_digest: str,
        matrix_revision: int = 2,
    ) -> AtomicBenchmarkPreflightBuild:
        if tuple(slot.slot_sequence for slot in slots) != tuple(range(1, 8)):
            raise AtomicBenchmarkIntegrityError("G3 requires exact slots 1..7")
        if type(matrix_revision) is not int or matrix_revision not in {2, 3}:
            raise AtomicBenchmarkIntegrityError(
                "G3 supports only matrix revisions 2 and 3"
            )
        dynamic_reserve = matrix_revision == 3
        eligibility_row_schema = (
            ELIGIBILITY_ROW_SCHEMA_V2
            if dynamic_reserve
            else ELIGIBILITY_ROW_SCHEMA
        )
        eligibility_manifest_schema = (
            ELIGIBILITY_MANIFEST_SCHEMA_V2
            if dynamic_reserve
            else ELIGIBILITY_MANIFEST_SCHEMA
        )
        preflight_schema = (
            PREFLIGHT_MANIFEST_SCHEMA_V3
            if dynamic_reserve
            else PREFLIGHT_MANIFEST_SCHEMA
        )
        slot_root_schema = (
            PREFLIGHT_SLOT_ROOT_SCHEMA_V3
            if dynamic_reserve
            else PREFLIGHT_SLOT_ROOT_SCHEMA
        )
        temporary = self._artifact_root / f".r6-g3-{uuid4().hex}.tmp"
        writers: list[_SlotWriter] = []
        eligibility_handle = None
        spool = None
        try:
            temporary.mkdir(parents=True, exist_ok=False)
            eligibility_directory = temporary / "eligibility"
            eligibility_directory.mkdir()
            eligibility_handle = (eligibility_directory / "rows.jsonl").open("xb")
            eligibility_sha = hashlib.sha256()
            eligibility_counts = {
                "observed": 0,
                "eligible": 0,
                "missing_entry": 0,
                "missing_signal_observation": 0,
                "missing_exit": 0,
            }
            eligibility_sequence = 0
            for slot in slots:
                slot.strategy.reset_runtime()
                writers.append(
                    _SlotWriter(
                        directory=temporary / f"slot-{slot.slot_sequence:02d}",
                        identity=slot.identity,
                    )
                )
            previous_close: dict[str, Decimal] = {}
            current_session: date | None = None
            session_closes: dict[str, Decimal] = {}
            eligibility_accumulator = _SessionEligibilityAccumulator(dynamic_reserve)
            spool = tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024, mode="w+b")

            def process_session(session: date) -> None:
                nonlocal eligibility_sequence
                eligible_symbols: set[str] = set()
                entry_reserve_by_symbol: dict[str, datetime] = {}
                decisions = eligibility_accumulator.decisions()
                for decision in decisions:
                    symbol = decision.symbol
                    eligibility_sequence += 1
                    entry = decision.entry_reserve
                    terminal = decision.terminal_exit
                    reasons = list(decision.exclusion_reason_codes)
                    if entry is None:
                        eligibility_counts["missing_entry"] += 1
                    signal_observation_count = (
                        decision.signal_observation_count_before_reserve
                    )
                    if (
                        dynamic_reserve
                        and entry is not None
                        and signal_observation_count == 0
                    ):
                        eligibility_counts["missing_signal_observation"] += 1
                    if terminal is None:
                        eligibility_counts["missing_exit"] += 1
                    if decision.eligible:
                        eligible_symbols.add(symbol)
                        entry_reserve_by_symbol[symbol] = entry.timestamp
                        eligibility_counts["eligible"] += 1
                    eligibility_counts["observed"] += 1
                    body = {
                        "schema_version": eligibility_row_schema,
                        "sequence": eligibility_sequence,
                        "symbol": symbol,
                        "session_date": session.isoformat(),
                        "entry_reserve_at": (
                            entry.timestamp.isoformat(timespec="seconds")
                            if entry is not None
                            else None
                        ),
                        "entry_reserve_bar_digest": (
                            entry.source_digest if entry is not None else None
                        ),
                        "terminal_exit_at": (
                            terminal.timestamp.isoformat(timespec="seconds")
                            if terminal is not None
                            else None
                        ),
                        "terminal_exit_bar_digest": (
                            terminal.source_digest if terminal is not None else None
                        ),
                        "eligibility_status": "ELIGIBLE" if not reasons else "EXCLUDED",
                        "exclusion_reason_codes": reasons,
                    }
                    if dynamic_reserve:
                        body["signal_observation_count_before_reserve"] = (
                            signal_observation_count
                        )
                    row = verify_eligibility_row(
                        {**body, "eligibility_row_digest": digest(body)}
                    )
                    payload = canonical_object_bytes(row)
                    eligibility_handle.write(payload)
                    eligibility_sha.update(payload)

                if eligible_symbols:
                    for slot in slots:
                        slot.strategy.begin_session(session)
                    day_states: dict[str, _DayState] = {}
                    spool.seek(0)
                    for raw in spool:
                        if raw == b"\n" or not raw.endswith(b"\n"):
                            raise AtomicBenchmarkIntegrityError("G3 session spool drift")
                        source = raw[:-1]
                        try:
                            parsed = json.loads(source)
                            bar = HistoricalBar.from_dict(parsed)
                        except (ValueError, TypeError, json.JSONDecodeError) as error:
                            raise AtomicBenchmarkIntegrityError(
                                "G3 session spool cannot parse"
                            ) from error
                        observed = ObservedBar(bar=bar, source_json=source)
                        if observed.symbol not in eligible_symbols:
                            continue
                        bar_time = observed.timestamp.time().replace(tzinfo=None)
                        if bar_time > REQUIRED_TERMINAL_EXIT:
                            continue
                        for writer in writers:
                            writer.before_evaluation(observed)
                        state = day_states.get(observed.symbol)
                        if state is None:
                            state = _DayState(session_open=observed.open)
                            day_states[observed.symbol] = state
                        session_high_before = state.session_high
                        vwap = state.update(observed.bar)
                        signal_cutoff = (
                            entry_reserve_by_symbol[observed.symbol]
                            if dynamic_reserve
                            else None
                        )
                        if (
                            observed.timestamp >= signal_cutoff
                            if signal_cutoff is not None
                            else bar_time >= COMMON_SIGNAL_CUTOFF
                        ):
                            continue
                        context = StrategyContext(
                            symbol=observed.symbol,
                            bar=observed.bar,
                            previous_close=previous_close.get(observed.symbol),
                            session_open=state.session_open,
                            session_high_before=session_high_before,
                            vwap=vwap,
                            cumulative_volume=state.cumulative_volume,
                            bars_seen=state.bars_seen,
                            is_last_bar=False,
                            resolved_session_date=session,
                        )
                        for slot, writer in zip(slots, writers, strict=True):
                            evaluation, feature_evidence = (
                                slot.strategy.evaluate_with_feature_evidence(context)
                            )
                            observed_values = dict(evaluation.observed)
                            observed_values.pop("feature_input_evidence", None)
                            row = writer.admission.consider(
                                matrix_id=matrix_id,
                                registration_digest=registration_digest,
                                slot_sequence=slot.slot_sequence,
                                hypothesis_id=str(slot.identity["hypothesis_id"]),
                                strategy_id=str(slot.identity["strategy_id"]),
                                strategy_version_id=str(
                                    slot.identity["strategy_version_id"]
                                ),
                                strategy_configuration_digest=str(
                                    slot.identity["strategy_configuration_digest"]
                                ),
                                strategy_implementation_digest=str(
                                    slot.identity["strategy_implementation_digest"]
                                ),
                                feature_request_identity_digest=str(
                                    slot.feature_request_identity_digest
                                ),
                                source_bar=observed,
                                evaluation_status=evaluation.status.value,
                                evaluation_document={
                                    "observed": observed_values,
                                    "threshold": dict(evaluation.threshold),
                                },
                                feature_input_evidence=feature_evidence,
                            )
                            if row is not None:
                                writer.add_signal(row)
                    for writer in writers:
                        writer.finish_session()
                previous_close.update(session_closes)

            for observed in dataset.iter_observed_bars():
                session = observed.session_date
                if current_session is None or session > current_session:
                    if current_session is not None:
                        process_session(current_session)
                        spool.close()
                        spool = tempfile.SpooledTemporaryFile(
                            max_size=8 * 1024 * 1024, mode="w+b"
                        )
                    current_session = session
                    session_closes = {}
                    eligibility_accumulator = _SessionEligibilityAccumulator(
                        dynamic_reserve
                    )
                elif session < current_session:
                    raise AtomicBenchmarkIntegrityError("G3 session order regressed")
                spool.write(observed.source_json + b"\n")
                eligibility_accumulator.observe(observed)
                session_closes[observed.symbol] = observed.close
            if current_session is not None:
                process_session(current_session)
            spool.close()
            if not dataset.source_eof_verified:
                raise AtomicBenchmarkIntegrityError("G3 Dataset EOF was not verified")
            eligibility_handle.flush()
            os.fsync(eligibility_handle.fileno())
            eligibility_handle.close()
            observed_count = eligibility_counts["observed"]
            if observed_count == 0:
                raise AtomicBenchmarkIntegrityError("G3 eligibility has no observations")
            ratio = _RATIO_CONTEXT.divide(
                Decimal(eligibility_counts["eligible"]), Decimal(observed_count)
            ).quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_EVEN)
            if ratio < MINIMUM_ELIGIBLE_RATIO:
                raise AtomicBenchmarkIntegrityError(
                    "G3 eligible symbol/session ratio below 0.95"
                )
            eligibility_body = {
                "schema_version": eligibility_manifest_schema,
                "dataset_id": dataset.manifest["dataset_id"],
                "dataset_digest": dataset.manifest["manifest_digest"],
                "dataset_bars_sha256": dataset.manifest["bars_sha256"],
                "entry_fill_deadline_time": "12:45",
                "required_terminal_exit_time": "13:30",
                "eligibility_row_schema_version": eligibility_row_schema,
                "observed_symbol_session_count": observed_count,
                "eligible_symbol_session_count": eligibility_counts["eligible"],
                "excluded_symbol_session_count": (
                    observed_count - eligibility_counts["eligible"]
                ),
                "missing_entry_reserve_count": eligibility_counts["missing_entry"],
                "missing_terminal_exit_count": eligibility_counts["missing_exit"],
                "eligible_symbol_session_ratio": format(ratio, ".18f"),
                "minimum_eligible_symbol_session_ratio": "0.95",
                "eligibility_rows_sha256": eligibility_sha.hexdigest(),
            }
            if dynamic_reserve:
                eligibility_body.update(
                    {
                        "entry_reserve_selection_semantics": (
                            "LAST_OBSERVED_SAME_SYMBOL_KBAR_AT_OR_BEFORE_12_45_V1"
                        ),
                        "signal_admission_comparator": (
                            "STRICT_LT_ENTRY_RESERVE_AT"
                        ),
                        "missing_signal_observation_count": eligibility_counts[
                            "missing_signal_observation"
                        ],
                    }
                )
            else:
                eligibility_body["common_signal_cutoff_time"] = "12:45"
            eligibility_manifest = verify_eligibility_manifest(
                {
                    **eligibility_body,
                    "eligibility_manifest_digest": digest(eligibility_body),
                }
            )
            _write_canonical(
                eligibility_directory / "manifest.json", eligibility_manifest
            )
            slot_roots = []
            slot_manifests = []
            for slot, writer in zip(slots, writers, strict=True):
                ledger_manifest, match_manifest = writer.finalize(
                    eligibility_manifest_digest=eligibility_manifest[
                        "eligibility_manifest_digest"
                    ]
                )
                slot_roots.append(
                    {
                        "schema_version": slot_root_schema,
                        "slot_sequence": slot.slot_sequence,
                        "hypothesis_id": slot.identity["hypothesis_id"],
                        "eligibility_manifest_digest": eligibility_manifest[
                            "eligibility_manifest_digest"
                        ],
                        "ledger_manifest_digest": ledger_manifest[
                            "ledger_manifest_digest"
                        ],
                        "match_manifest_digest": match_manifest[
                            "match_manifest_digest"
                        ],
                        "signal_count": ledger_manifest["ledger_signal_count"],
                        "matched_count": match_manifest["matched_entry_count"],
                    }
                )
                slot_manifests.append(
                    {"ledger": ledger_manifest, "match": match_manifest}
                )
            body = {
                "schema_version": preflight_schema,
                "family_id": family_id,
                "matrix_id": matrix_id,
                "matrix_revision": matrix_revision,
                "registration_digest": registration_digest,
                "research_baseline_digest": research_baseline_digest,
                "dataset_id": dataset.manifest["dataset_id"],
                "dataset_digest": dataset.manifest["manifest_digest"],
                "dataset_bars_sha256": dataset.manifest["bars_sha256"],
                "dataset_bar_count": dataset.manifest["bar_count"],
                "dataset_binding_revision": dataset_binding_revision,
                "source_bar_count": dataset.source_bar_count,
                "source_bars_sha256": dataset.source_bars_sha256,
                "source_eof_verified": True,
                "protocol_core_digest": protocol_core_digest,
                "algorithm_contract_digest": ALGORITHM_CONTRACT_DIGEST,
                "algorithm_implementation_digest": algorithm_implementation_digest,
                "preflight_implementation_digest": preflight_implementation_digest,
                "eligibility_manifest_digest": eligibility_manifest[
                    "eligibility_manifest_digest"
                ],
                "slots": slot_roots,
            }
            manifest = {**body, "preflight_digest": digest(body)}
            _write_canonical(temporary / "preflight_manifest.json", manifest)
            final = self._artifact_root / str(manifest["preflight_digest"])
            self._publish(temporary, final, manifest)
            return AtomicBenchmarkPreflightBuild(
                manifest=manifest,
                slot_roots=tuple(slot_roots),
                slot_manifests=tuple(slot_manifests),
                path=final,
            )
        except BaseException:
            if eligibility_handle is not None and not eligibility_handle.closed:
                eligibility_handle.close()
            if spool is not None:
                spool.close()
            for writer in writers:
                writer.close()
            shutil.rmtree(temporary, ignore_errors=True)
            raise

    @staticmethod
    def _publish(
        temporary: Path, final: Path, expected: Mapping[str, object]
    ) -> None:
        final.parent.mkdir(parents=True, exist_ok=True)
        verify_preflight_artifact(temporary, expected_manifest=expected)
        if final.exists():
            verify_preflight_artifact(final, expected_manifest=expected)
            shutil.rmtree(temporary)
            return
        os.replace(temporary, final)
        directory_fd = os.open(final.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)


def _load_exact_manifest(path: Path, verifier: Callable[[Mapping[str, Any]], Any]) -> dict[str, Any]:
    payload = path.read_bytes()
    try:
        value = json.loads(payload)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise AtomicBenchmarkIntegrityError(f"invalid manifest: {path.name}") from error
    if not isinstance(value, Mapping):
        raise AtomicBenchmarkIntegrityError(f"manifest is not an object: {path.name}")
    verified = dict(verifier(value))
    if payload != canonical_object_bytes(verified):
        raise AtomicBenchmarkIntegrityError(f"manifest bytes are not canonical: {path.name}")
    return verified


def _stream_artifact_rows(
    path: Path,
    *,
    verifier: Callable[[Mapping[str, Any]], dict[str, Any]],
    identity: Mapping[str, object],
) -> tuple[int, str, str, int]:
    checksum = hashlib.sha256()
    count = 0
    with tempfile.TemporaryDirectory(prefix="r6-g3-verify-") as temp:
        multiplicity = _ExternalMultiplicity(Path(temp), "rows")
        try:
            with path.open("rb") as handle:
                for raw in handle:
                    checksum.update(raw)
                    if raw == b"\n" or not raw.endswith(b"\n"):
                        raise AtomicBenchmarkIntegrityError(
                            f"{path.name} requires canonical JSON plus LF"
                        )
                    try:
                        parsed = json.loads(raw[:-1])
                    except (UnicodeDecodeError, json.JSONDecodeError) as error:
                        raise AtomicBenchmarkIntegrityError(
                            f"{path.name} row cannot parse"
                        ) from error
                    if not isinstance(parsed, Mapping):
                        raise AtomicBenchmarkIntegrityError(
                            f"{path.name} row is not an object"
                        )
                    row = verifier(parsed)
                    if raw != canonical_object_bytes(row):
                        raise AtomicBenchmarkIntegrityError(
                            f"{path.name} row bytes are not canonical"
                        )
                    count += 1
                    if row["sequence"] != count:
                        raise AtomicBenchmarkIntegrityError(
                            f"{path.name} sequence drift"
                        )
                    for field in (
                        "matrix_id",
                        "registration_digest",
                        "slot_sequence",
                        "hypothesis_id",
                        "strategy_id",
                        "strategy_version_id",
                        "strategy_configuration_digest",
                        "strategy_implementation_digest",
                    ):
                        if field in row and row[field] != identity[field]:
                            raise AtomicBenchmarkIntegrityError(
                                f"{path.name} lineage drift: {field}"
                            )
                    multiplicity.add(row)
            projection_digest, duplicates, token_count = multiplicity.finish()
            if token_count != count:
                raise AtomicBenchmarkIntegrityError(f"{path.name} token count drift")
            return count, checksum.hexdigest(), projection_digest, duplicates
        finally:
            multiplicity.close()


def verify_preflight_manifest(value: Mapping[str, object]) -> dict[str, object]:
    manifest = dict(value)
    if frozenset(manifest) != _PREFLIGHT_FIELDS:
        raise AtomicBenchmarkIntegrityError("G3 preflight manifest fields drift")
    schema_revision = {
        PREFLIGHT_MANIFEST_SCHEMA: 2,
        PREFLIGHT_MANIFEST_SCHEMA_V3: 3,
    }.get(manifest.get("schema_version"))
    if schema_revision is None:
        raise AtomicBenchmarkIntegrityError("G3 preflight manifest schema drift")
    if manifest["matrix_revision"] != schema_revision:
        raise AtomicBenchmarkIntegrityError("G3 matrix revision drift")
    if type(manifest["source_eof_verified"]) is not bool or not manifest[
        "source_eof_verified"
    ]:
        raise AtomicBenchmarkIntegrityError("G3 source EOF evidence is invalid")
    for field in (
        "registration_digest",
        "research_baseline_digest",
        "dataset_digest",
        "dataset_bars_sha256",
        "source_bars_sha256",
        "protocol_core_digest",
        "algorithm_contract_digest",
        "algorithm_implementation_digest",
        "preflight_implementation_digest",
        "eligibility_manifest_digest",
        "preflight_digest",
    ):
        value = manifest[field]
        if (
            not isinstance(value, str)
            or len(value) != 64
            or any(character not in "0123456789abcdef" for character in value)
        ):
            raise AtomicBenchmarkIntegrityError(f"G3 invalid SHA-256: {field}")
    if manifest["algorithm_contract_digest"] != ALGORITHM_CONTRACT_DIGEST:
        raise AtomicBenchmarkIntegrityError("G3 algorithm contract drift")
    for field in ("dataset_bar_count", "source_bar_count"):
        if type(manifest[field]) is not int or int(manifest[field]) < 0:
            raise AtomicBenchmarkIntegrityError(f"G3 invalid count: {field}")
    if manifest["dataset_bar_count"] != manifest["source_bar_count"]:
        raise AtomicBenchmarkIntegrityError("G3 Dataset count evidence drift")
    if manifest["dataset_bars_sha256"] != manifest["source_bars_sha256"]:
        raise AtomicBenchmarkIntegrityError("G3 Dataset SHA evidence drift")
    if manifest["dataset_binding_revision"] != 1:
        raise AtomicBenchmarkIntegrityError("G3 binding revision drift")
    slots = manifest["slots"]
    if not isinstance(slots, list) or len(slots) != 7:
        raise AtomicBenchmarkIntegrityError("G3 requires seven slot roots")
    for expected, root in enumerate(slots, start=1):
        if not isinstance(root, Mapping) or frozenset(root) != _SLOT_ROOT_FIELDS:
            raise AtomicBenchmarkIntegrityError("G3 slot root fields drift")
        if (
            root["schema_version"]
            != (
                PREFLIGHT_SLOT_ROOT_SCHEMA_V3
                if schema_revision == 3
                else PREFLIGHT_SLOT_ROOT_SCHEMA
            )
            or root["slot_sequence"] != expected
            or type(root["signal_count"]) is not int
            or type(root["matched_count"]) is not int
            or root["signal_count"] < 0
            or root["matched_count"] < 0
        ):
            raise AtomicBenchmarkIntegrityError("G3 slot root identity drift")
        if root["eligibility_manifest_digest"] != manifest[
            "eligibility_manifest_digest"
        ]:
            raise AtomicBenchmarkIntegrityError("G3 slot eligibility root drift")
    body = dict(manifest)
    stored_digest = body.pop("preflight_digest")
    if digest(body) != stored_digest:
        raise AtomicBenchmarkIntegrityError("G3 preflight digest drift")
    canonical_object_bytes(manifest)
    return manifest


def verify_preflight_artifact(
    path: Path, *, expected_manifest: Mapping[str, object] | None = None
) -> AtomicBenchmarkPreflightBuild:
    root = Path(path)
    if root.is_symlink() or not root.is_dir():
        raise AtomicBenchmarkIntegrityError("G3 preflight artifact is missing")
    expected_files = {"preflight_manifest.json"}
    expected_files.update({"eligibility/rows.jsonl", "eligibility/manifest.json"})
    for slot in range(1, 8):
        prefix = f"slot-{slot:02d}"
        expected_files.update(
            {
                f"{prefix}/ledger.jsonl",
                f"{prefix}/matches.jsonl",
                f"{prefix}/ledger_manifest.json",
                f"{prefix}/match_manifest.json",
            }
        )
    expected_directories = {"eligibility"}
    expected_directories.update({f"slot-{slot:02d}" for slot in range(1, 8)})
    actual_files: set[str] = set()
    actual_directories: set[str] = set()
    for item in root.rglob("*"):
        relative = item.relative_to(root).as_posix()
        if item.is_symlink():
            raise AtomicBenchmarkIntegrityError(
                "G3 preflight artifact cannot contain symlinks"
            )
        mode = item.stat(follow_symlinks=False).st_mode
        if stat.S_ISDIR(mode):
            actual_directories.add(relative)
        elif stat.S_ISREG(mode):
            actual_files.add(relative)
        else:
            raise AtomicBenchmarkIntegrityError(
                "G3 preflight artifact contains a non-regular member"
            )
    if actual_files != expected_files or actual_directories != expected_directories:
        raise AtomicBenchmarkIntegrityError("G3 preflight artifact member tree drift")
    manifest = _load_exact_manifest(
        root / "preflight_manifest.json", verify_preflight_manifest
    )
    if expected_manifest is not None and manifest != dict(expected_manifest):
        raise AtomicBenchmarkIntegrityError("G3 preflight expected root conflict")
    eligibility = _load_exact_manifest(
        root / "eligibility" / "manifest.json", verify_eligibility_manifest
    )
    if (
        eligibility["eligibility_manifest_digest"]
        != manifest["eligibility_manifest_digest"]
        or eligibility["dataset_id"] != manifest["dataset_id"]
        or eligibility["dataset_digest"] != manifest["dataset_digest"]
        or eligibility["dataset_bars_sha256"] != manifest["dataset_bars_sha256"]
    ):
        raise AtomicBenchmarkIntegrityError("G3 eligibility root lineage drift")
    eligibility_sha = hashlib.sha256()
    observed = eligible = missing_entry = missing_signal = missing_exit = 0
    previous_key: tuple[str, str] | None = None
    with (root / "eligibility" / "rows.jsonl").open("rb") as handle:
        for raw in handle:
            eligibility_sha.update(raw)
            if raw == b"\n" or not raw.endswith(b"\n"):
                raise AtomicBenchmarkIntegrityError(
                    "G3 eligibility rows require canonical JSON plus LF"
                )
            try:
                parsed = json.loads(raw[:-1])
            except (UnicodeDecodeError, json.JSONDecodeError) as error:
                raise AtomicBenchmarkIntegrityError(
                    "G3 eligibility row cannot parse"
                ) from error
            if not isinstance(parsed, Mapping):
                raise AtomicBenchmarkIntegrityError("G3 eligibility row is not object")
            row = verify_eligibility_row(parsed)
            if raw != canonical_object_bytes(row):
                raise AtomicBenchmarkIntegrityError(
                    "G3 eligibility row bytes are not canonical"
                )
            observed += 1
            if row["sequence"] != observed:
                raise AtomicBenchmarkIntegrityError("G3 eligibility sequence drift")
            key = (str(row["session_date"]), str(row["symbol"]))
            if previous_key is not None and key <= previous_key:
                raise AtomicBenchmarkIntegrityError("G3 eligibility row order drift")
            previous_key = key
            if row["eligibility_status"] == "ELIGIBLE":
                eligible += 1
            if row["entry_reserve_at"] is None:
                missing_entry += 1
            if (
                row["schema_version"] == ELIGIBILITY_ROW_SCHEMA_V2
                and row["entry_reserve_at"] is not None
                and row["signal_observation_count_before_reserve"] == 0
            ):
                missing_signal += 1
            if row["terminal_exit_at"] is None:
                missing_exit += 1
    expected_ratio = _RATIO_CONTEXT.divide(Decimal(eligible), Decimal(observed)).quantize(
        _RATIO_QUANTUM, rounding=ROUND_HALF_EVEN
    ) if observed else Decimal("0.000000000000000000")
    if (
        observed != eligibility["observed_symbol_session_count"]
        or eligible != eligibility["eligible_symbol_session_count"]
        or observed - eligible != eligibility["excluded_symbol_session_count"]
        or missing_entry != eligibility["missing_entry_reserve_count"]
        or (
            eligibility["schema_version"] == ELIGIBILITY_MANIFEST_SCHEMA_V2
            and missing_signal
            != eligibility["missing_signal_observation_count"]
        )
        or missing_exit != eligibility["missing_terminal_exit_count"]
        or format(expected_ratio, ".18f")
        != eligibility["eligible_symbol_session_ratio"]
        or eligibility_sha.hexdigest() != eligibility["eligibility_rows_sha256"]
        or expected_ratio < MINIMUM_ELIGIBLE_RATIO
    ):
        raise AtomicBenchmarkIntegrityError("G3 eligibility artifact audit failed")
    slot_roots: list[dict[str, object]] = []
    slot_manifests: list[dict[str, dict[str, object]]] = []
    for expected, root_entry in enumerate(manifest["slots"], start=1):
        directory = root / f"slot-{expected:02d}"
        ledger = _load_exact_manifest(
            directory / "ledger_manifest.json", verify_ledger_manifest
        )
        matches = _load_exact_manifest(
            directory / "match_manifest.json", verify_match_manifest
        )
        identity = {
            field: ledger[field]
            for field in (
                "matrix_id",
                "registration_digest",
                "slot_sequence",
                "hypothesis_id",
                "strategy_id",
                "strategy_version_id",
                "strategy_configuration_digest",
                "strategy_implementation_digest",
            )
        }
        ledger_count, ledger_sha, ledger_parity, ledger_duplicates = (
            _stream_artifact_rows(
                directory / "ledger.jsonl",
                verifier=verify_ledger_row,
                identity=identity,
            )
        )
        match_count, match_sha, match_parity, match_duplicates = (
            _stream_artifact_rows(
                directory / "matches.jsonl",
                verifier=verify_match_row,
                identity=identity,
            )
        )
        common_checks = {
            "family_id": manifest["family_id"],
            "matrix_id": manifest["matrix_id"],
            "registration_digest": manifest["registration_digest"],
            "research_baseline_digest": manifest["research_baseline_digest"],
            "dataset_id": manifest["dataset_id"],
            "dataset_digest": manifest["dataset_digest"],
            "dataset_bars_sha256": manifest["dataset_bars_sha256"],
            "dataset_binding_revision": manifest["dataset_binding_revision"],
            "protocol_core_digest": manifest["protocol_core_digest"],
            "algorithm_contract_digest": manifest["algorithm_contract_digest"],
            "algorithm_implementation_digest": manifest[
                "algorithm_implementation_digest"
            ],
        }
        if any(ledger[field] != value for field, value in common_checks.items()):
            raise AtomicBenchmarkIntegrityError("G3 ledger root lineage drift")
        if any(matches[field] != value for field, value in common_checks.items()):
            raise AtomicBenchmarkIntegrityError("G3 match root lineage drift")
        if (
            ledger_count != ledger["ledger_signal_count"]
            or ledger_sha != ledger["ledger_rows_sha256"]
            or ledger_parity != ledger["ledger_signal_multiplicity_digest"]
            or ledger_duplicates != 0
            or match_count != matches["matched_entry_count"]
            or match_sha != matches["match_rows_sha256"]
            or match_parity != matches["match_signal_multiplicity_digest"]
            or match_duplicates != matches["duplicate_match_count"]
            or matches["missing_entry_count"] != 0
            or matches["missing_exit_count"] != 0
            or ledger_parity != match_parity
            or ledger.get("eligibility_manifest_digest")
            != manifest["eligibility_manifest_digest"]
            or matches.get("eligibility_manifest_digest")
            != manifest["eligibility_manifest_digest"]
            or root_entry["hypothesis_id"] != ledger["hypothesis_id"]
            or root_entry["ledger_manifest_digest"]
            != ledger["ledger_manifest_digest"]
            or root_entry["match_manifest_digest"]
            != matches["match_manifest_digest"]
            or root_entry["signal_count"] != ledger_count
            or root_entry["matched_count"] != match_count
        ):
            raise AtomicBenchmarkIntegrityError("G3 slot artifact audit failed")
        slot_roots.append(dict(root_entry))
        slot_manifests.append({"ledger": ledger, "match": matches})
    return AtomicBenchmarkPreflightBuild(
        manifest=manifest,
        slot_roots=tuple(slot_roots),
        slot_manifests=tuple(slot_manifests),
        path=root,
    )


def preflight_implementation_digest(repository_root: Path) -> str:
    """Bind the G3 orchestration without changing the sealed G1 algorithm root."""

    paths = (
        "backtest/atomic_benchmark/preflight.py",
        "backtest/atomic_strategy_adapter.py",
        "scripts/preflight_atomic_entry_benchmark.py",
    )
    files = []
    for relative in paths:
        payload = (Path(repository_root) / relative).read_bytes()
        files.append(
            {"path": relative, "byte_count": len(payload), "sha256": hashlib.sha256(payload).hexdigest()}
        )
    return digest({"schema_version": "r6-preflight-source-manifest-v2", "files": files})


def eligibility_audit_implementation_digest(repository_root: Path) -> str:
    """Bind the source-only A2 audit code used before Migration 018."""

    paths = (
        "backtest/atomic_benchmark/preflight.py",
        "scripts/audit_atomic_entry_benchmark_eligibility.py",
    )
    files = []
    for relative in paths:
        payload = (Path(repository_root) / relative).read_bytes()
        files.append(
            {
                "path": relative,
                "byte_count": len(payload),
                "sha256": hashlib.sha256(payload).hexdigest(),
            }
        )
    return digest(
        {"schema_version": "r6-eligibility-audit-source-manifest-v1", "files": files}
    )


def as_atomic_runtime(strategy: AtomicBacktestStrategyAdapter) -> PreflightStrategyRuntime:
    """Make the intended adapter boundary explicit for composition roots."""

    return strategy
