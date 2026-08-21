"""Passive, deterministic evidence extraction for late market-data delivery.

This module deliberately observes the canonical Journal and its dispositions.
It does not reinterpret late delivery, select a Health severity, or change any
projection/admission behavior.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import date, datetime, time
from enum import StrEnum
from pathlib import Path
from typing import Mapping
from zoneinfo import ZoneInfo

from market_data.journal import JournalRecordType, verify_market_event_journal


TAIPEI = ZoneInfo("Asia/Taipei")
LATE_DELIVERY_COHORT_MANIFEST_SCHEMA = "late-delivery-cohort-manifest-v1"
LATE_DELIVERY_SESSION_SCHEMA = "late-delivery-session-evidence-v1"
LATE_DELIVERY_DAILY_SCHEMA = "late-delivery-daily-evidence-v2"


class SessionPhase(StrEnum):
    OPEN = "OPEN"
    MID = "MID"
    CLOSE = "CLOSE"


_PHASE_WINDOWS: tuple[tuple[SessionPhase, time, time], ...] = (
    (SessionPhase.OPEN, time(9, 0), time(9, 30)),
    (SessionPhase.MID, time(10, 30), time(11, 0)),
    (SessionPhase.CLOSE, time(13, 0), time(13, 30)),
)


@dataclass(frozen=True)
class LateDeliveryCohortEntry:
    symbol: str
    liquidity_tier: str
    selection_evidence: str


@dataclass(frozen=True)
class LateDeliveryCohort:
    entries: tuple[LateDeliveryCohortEntry, ...]
    source_provider: str
    source_date: date
    source_identity: str
    manifest_digest: str

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(entry.symbol for entry in self.entries)

    def tier_for(self, symbol: str) -> str:
        normalized = _symbol(symbol)
        for entry in self.entries:
            if entry.symbol == normalized:
                return entry.liquidity_tier
        raise KeyError(f"symbol is not in late-delivery cohort: {normalized}")

    @classmethod
    def from_path(cls, path: Path) -> "LateDeliveryCohort":
        try:
            raw = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as error:
            raise ValueError(f"late-delivery cohort is unreadable: {path}") from error
        if not isinstance(raw, dict):
            raise ValueError("late-delivery cohort root must be an object")
        return cls.from_mapping(raw)

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "LateDeliveryCohort":
        required = {
            "schema",
            "status",
            "capture_timezone",
            "selection_source",
            "symbols",
            "session_windows",
        }
        if set(raw) != required:
            raise ValueError("late-delivery cohort fields do not match contract")
        if raw["schema"] != LATE_DELIVERY_COHORT_MANIFEST_SCHEMA:
            raise ValueError("unsupported late-delivery cohort schema")
        if raw["status"] != "FROZEN_FOR_COLLECTION":
            raise ValueError("late-delivery cohort must be FROZEN_FOR_COLLECTION")
        if raw["capture_timezone"] != "Asia/Taipei":
            raise ValueError("late-delivery cohort timezone must be Asia/Taipei")
        source = _mapping(raw["selection_source"], "selection_source")
        if set(source) != {"provider", "source_date", "source_identity"}:
            raise ValueError("selection_source fields do not match contract")
        provider = _non_empty(source["provider"], "selection_source.provider")
        source_date = _date(source["source_date"], "selection_source.source_date")
        source_identity = _non_empty(
            source["source_identity"], "selection_source.source_identity"
        )
        symbols = _object_list(raw["symbols"], "symbols")
        if not 6 <= len(symbols) <= 9:
            raise ValueError("late-delivery cohort must contain six to nine symbols")
        entries: list[LateDeliveryCohortEntry] = []
        tiers: set[str] = set()
        for item in symbols:
            if set(item) != {"symbol", "liquidity_tier", "selection_evidence"}:
                raise ValueError("cohort symbol fields do not match contract")
            symbol = _symbol(item["symbol"])
            tier = _non_empty(item["liquidity_tier"], "liquidity_tier").lower()
            if tier not in {"high", "mid", "low"}:
                raise ValueError("liquidity_tier must be high, mid, or low")
            entries.append(
                LateDeliveryCohortEntry(
                    symbol=symbol,
                    liquidity_tier=tier,
                    selection_evidence=_non_empty(
                        item["selection_evidence"], "selection_evidence"
                    ),
                )
            )
            tiers.add(tier)
        entries.sort(key=lambda item: item.symbol)
        if len({item.symbol for item in entries}) != len(entries):
            raise ValueError("late-delivery cohort contains duplicate symbols")
        if tiers != {"high", "mid", "low"}:
            raise ValueError("late-delivery cohort requires high, mid, and low tiers")
        _validate_session_windows(raw["session_windows"])
        canonical = _canonical_json(raw)
        return cls(
            entries=tuple(entries),
            source_provider=provider,
            source_date=source_date,
            source_identity=source_identity,
            manifest_digest=hashlib.sha256(canonical).hexdigest(),
        )


@dataclass(frozen=True)
class LateDeliveryEvent:
    session_id: str
    session_date: date
    symbol: str
    stream_kind: str
    record_index: int
    ingress_record_index: int
    event_id: str
    source_ts: datetime
    received_ts: datetime
    previous_watermark_source_ts: datetime
    previous_watermark_ingress_sequence: int
    source_regression_ms: float
    receive_progression_ms: float | None
    consecutive_late_count: int
    time_since_previous_late_ms: float | None
    session_phase: SessionPhase | None
    projection_effect: str
    health_effect: str
    admission_effect: str

    def to_dict(self) -> dict[str, object]:
        return {
            "session_id": self.session_id,
            "session_date": self.session_date.isoformat(),
            "symbol": self.symbol,
            "stream_kind": self.stream_kind,
            "record_index": self.record_index,
            "ingress_record_index": self.ingress_record_index,
            "event_id": self.event_id,
            "source_ts": self.source_ts.isoformat(),
            "received_ts": self.received_ts.isoformat(),
            "previous_watermark_source_ts": self.previous_watermark_source_ts.isoformat(),
            "previous_watermark_ingress_sequence": self.previous_watermark_ingress_sequence,
            "source_regression_ms": self.source_regression_ms,
            "receive_progression_ms": self.receive_progression_ms,
            "consecutive_late_count": self.consecutive_late_count,
            "time_since_previous_late_ms": self.time_since_previous_late_ms,
            "session_phase": (
                self.session_phase.value if self.session_phase is not None else None
            ),
            "projection_effect": self.projection_effect,
            "health_effect": self.health_effect,
            "admission_effect": self.admission_effect,
        }


@dataclass(frozen=True)
class LateDeliveryTotals:
    total_events: int
    accepted_count: int
    rejected_count: int
    late_delivery_count: int
    late_delivery_ratio: float | None
    regression_abs_p50_ms: float | None
    regression_abs_p90_ms: float | None
    regression_abs_p95_ms: float | None
    regression_abs_p99_ms: float | None
    regression_abs_max_ms: float | None
    consecutive_late_max: int

    @classmethod
    def from_events(
        cls,
        *,
        total_events: int,
        accepted_count: int,
        rejected_count: int,
        late_events: tuple[LateDeliveryEvent, ...],
    ) -> "LateDeliveryTotals":
        regressions = sorted(abs(item.source_regression_ms) for item in late_events)
        return cls(
            total_events=total_events,
            accepted_count=accepted_count,
            rejected_count=rejected_count,
            late_delivery_count=len(late_events),
            late_delivery_ratio=(
                len(late_events) / total_events if total_events else None
            ),
            regression_abs_p50_ms=_percentile(regressions, 0.50),
            regression_abs_p90_ms=_percentile(regressions, 0.90),
            regression_abs_p95_ms=_percentile(regressions, 0.95),
            regression_abs_p99_ms=_percentile(regressions, 0.99),
            regression_abs_max_ms=max(regressions) if regressions else None,
            consecutive_late_max=max(
                (item.consecutive_late_count for item in late_events), default=0
            ),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "total_events": self.total_events,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "late_delivery_count": self.late_delivery_count,
            "late_delivery_ratio": self.late_delivery_ratio,
            "regression_abs_p50_ms": self.regression_abs_p50_ms,
            "regression_abs_p90_ms": self.regression_abs_p90_ms,
            "regression_abs_p95_ms": self.regression_abs_p95_ms,
            "regression_abs_p99_ms": self.regression_abs_p99_ms,
            "regression_abs_max_ms": self.regression_abs_max_ms,
            "consecutive_late_max": self.consecutive_late_max,
        }


@dataclass(frozen=True)
class LateDeliverySessionReport:
    session_id: str
    session_date: date
    journal_sha256: str
    status: str
    stream_totals: Mapping[str, LateDeliveryTotals]
    by_symbol: Mapping[str, "LateDeliverySymbolSummary"]
    by_phase: Mapping[str, "LateDeliverySymbolSummary"]
    late_deliveries: tuple[LateDeliveryEvent, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": LATE_DELIVERY_SESSION_SCHEMA,
            "session_id": self.session_id,
            "session_date": self.session_date.isoformat(),
            "journal_sha256": self.journal_sha256,
            "status": self.status,
            "stream_totals": {
                key: value.to_dict() for key, value in sorted(self.stream_totals.items())
            },
            "by_symbol": {
                key: value.to_dict() for key, value in sorted(self.by_symbol.items())
            },
            "by_phase": {
                key: value.to_dict() for key, value in sorted(self.by_phase.items())
            },
            "late_deliveries": [item.to_dict() for item in self.late_deliveries],
            "policy_interpretation": "PROHIBITED_EVIDENCE_ONLY",
        }


@dataclass(frozen=True)
class LateDeliverySymbolSummary:
    by_stream: Mapping[str, LateDeliveryTotals]

    def to_dict(self) -> dict[str, object]:
        return {
            "by_stream": {
                key: value.to_dict() for key, value in sorted(self.by_stream.items())
            }
        }


@dataclass(frozen=True)
class LateDeliveryDailyReport:
    session_date: date
    session_count: int
    incomplete_session_ids: tuple[str, ...]
    replay_failed_session_ids: tuple[str, ...]
    by_stream: Mapping[str, LateDeliveryTotals]
    by_symbol: Mapping[str, LateDeliverySymbolSummary]
    by_phase: Mapping[str, LateDeliverySymbolSummary]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema": LATE_DELIVERY_DAILY_SCHEMA,
            "session_date": self.session_date.isoformat(),
            "session_count": self.session_count,
            "incomplete_session_ids": list(self.incomplete_session_ids),
            "replay_failed_session_ids": list(self.replay_failed_session_ids),
            "by_stream": {
                key: value.to_dict() for key, value in sorted(self.by_stream.items())
            },
            "by_symbol": {
                key: value.to_dict() for key, value in sorted(self.by_symbol.items())
            },
            "by_phase": {
                key: value.to_dict() for key, value in sorted(self.by_phase.items())
            },
            "policy_interpretation": "PROHIBITED_EVIDENCE_ONLY",
        }


def classify_session_phase(value: datetime) -> SessionPhase | None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("session phase timestamp must be timezone-aware")
    local_time = value.astimezone(TAIPEI).timetz().replace(tzinfo=None)
    for phase, starts_at, ends_at in _PHASE_WINDOWS:
        if starts_at <= local_time < ends_at:
            return phase
    return None


def analyze_late_delivery_session(session_dir: Path) -> LateDeliverySessionReport:
    journal = verify_market_event_journal(session_dir)
    if not journal.valid or journal.manifest is None or journal.calculated_sha256 is None:
        errors = "; ".join(journal.errors) or "journal verification failed"
        raise ValueError(f"late-delivery analysis requires a finalized valid Journal: {errors}")
    manifest = journal.manifest
    if manifest.get("status") != "FINALIZED":
        raise ValueError("late-delivery analysis requires a FINALIZED Journal")
    ingress: dict[int, Mapping[str, object]] = {}
    ingress_by_sequence: dict[int, Mapping[str, object]] = {}
    totals: dict[str, list[int]] = _empty_counts()
    totals_by_symbol: dict[str, dict[str, list[int]]] = {}
    totals_by_phase: dict[str, dict[str, list[int]]] = {}
    late_events: list[LateDeliveryEvent] = []
    consecutive: dict[tuple[str, str], int] = {}
    previous_late_received: dict[tuple[str, str], datetime] = {}

    for record in journal.records:
        record_type = str(record["record_type"])
        if record_type == JournalRecordType.INGRESS.value:
            event = _mapping(record["event"], "event")
            index = _integer(record["record_index"], "record_index")
            ingress[index] = event
            ingress_by_sequence[_integer(event["ingress_sequence"], "ingress_sequence")] = event
            continue
        if record_type != JournalRecordType.DISPOSITION.value:
            continue
        result = _mapping(record["result"], "result")
        ingress_index = _integer(record["ingress_record_index"], "ingress_record_index")
        event = ingress.get(ingress_index)
        if event is None:
            raise ValueError("disposition references a missing ingress event")
        stream_kind = _non_empty(result["stream_kind"], "result.stream_kind")
        if stream_kind not in totals:
            raise ValueError("unsupported market stream in Journal")
        symbol = _symbol(result["symbol"])
        key = (symbol, stream_kind)
        received_at = _aware(event["received_at"], "event.received_at")
        phase = classify_session_phase(received_at)
        bucket = totals[stream_kind]
        bucket[0] += 1
        symbol_bucket = totals_by_symbol.setdefault(symbol, _empty_counts())[stream_kind]
        symbol_bucket[0] += 1
        phase_bucket: list[int] | None = None
        if phase is not None:
            phase_bucket = totals_by_phase.setdefault(phase.value, _empty_counts())[stream_kind]
            phase_bucket[0] += 1
        if bool(result["projection_applied"]):
            bucket[1] += 1
            symbol_bucket[1] += 1
            if phase_bucket is not None:
                phase_bucket[1] += 1
            consecutive[key] = 0
            continue
        bucket[2] += 1
        symbol_bucket[2] += 1
        if phase_bucket is not None:
            phase_bucket[2] += 1
        if result["status"] != "OUT_OF_ORDER_REJECTED":
            consecutive[key] = 0
            continue
        previous = _mapping(result["previous_watermark"], "previous_watermark")
        event_at = _aware(event["event_at"], "event.event_at")
        previous_event_at = _aware(previous["event_time"], "previous_watermark.event_time")
        previous_sequence = _integer(
            previous["ingress_sequence"], "previous_watermark.ingress_sequence"
        )
        previous_event = ingress_by_sequence.get(previous_sequence)
        if previous_event is None:
            raise ValueError("late delivery watermark does not reference an ingress")
        previous_received_at = _aware(
            previous_event["received_at"], "previous ingress received_at"
        )
        consecutive[key] = consecutive.get(key, 0) + 1
        last_late = previous_late_received.get(key)
        late = LateDeliveryEvent(
            session_id=_non_empty(manifest["session_id"], "session_id"),
            session_date=_date(manifest["session_date"], "session_date"),
            symbol=symbol,
            stream_kind=stream_kind,
            record_index=_integer(record["record_index"], "record_index"),
            ingress_record_index=ingress_index,
            event_id=_non_empty(result["event_id"], "result.event_id"),
            source_ts=event_at,
            received_ts=received_at,
            previous_watermark_source_ts=previous_event_at,
            previous_watermark_ingress_sequence=previous_sequence,
            source_regression_ms=(event_at - previous_event_at).total_seconds() * 1000,
            receive_progression_ms=(received_at - previous_received_at).total_seconds() * 1000,
            consecutive_late_count=consecutive[key],
            time_since_previous_late_ms=(
                (received_at - last_late).total_seconds() * 1000
                if last_late is not None
                else None
            ),
            session_phase=classify_session_phase(received_at),
            projection_effect="REJECTED_BEFORE_PROJECTION",
            health_effect=_transition(
                _non_empty(result["health_before"], "result.health_before"),
                _non_empty(result["health_after"], "result.health_after"),
            ),
            admission_effect=_transition(
                _admission(_non_empty(result["health_before"], "result.health_before")),
                _admission(_non_empty(result["health_after"], "result.health_after")),
            ),
        )
        previous_late_received[key] = received_at
        late_events.append(late)

    late_events.sort(key=lambda item: item.record_index)
    stream_totals = _summary_from_counts(totals, tuple(late_events))
    by_symbol = {
        symbol: LateDeliverySymbolSummary(
            by_stream=_summary_from_counts(
                values,
                tuple(item for item in late_events if item.symbol == symbol),
            )
        )
        for symbol, values in sorted(totals_by_symbol.items())
    }
    by_phase = {
        phase: LateDeliverySymbolSummary(
            by_stream=_summary_from_counts(
                values,
                tuple(
                    item
                    for item in late_events
                    if item.session_phase is not None and item.session_phase.value == phase
                ),
            )
        )
        for phase, values in sorted(totals_by_phase.items())
    }
    return LateDeliverySessionReport(
        session_id=_non_empty(manifest["session_id"], "session_id"),
        session_date=_date(manifest["session_date"], "session_date"),
        journal_sha256=journal.calculated_sha256,
        status="FINALIZED",
        stream_totals=stream_totals,
        by_symbol=by_symbol,
        by_phase=by_phase,
        late_deliveries=tuple(late_events),
    )


def write_late_delivery_session_report(
    session_dir: Path,
    report: LateDeliverySessionReport,
) -> Path:
    path = session_dir / "late_delivery_evidence.json"
    encoded = _canonical_json(report.to_dict()) + b"\n"
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("late-delivery session report already exists with different content")
        return path
    with path.open("xb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    return path


def build_daily_late_delivery_report(
    records_root: Path,
    session_date: date,
) -> LateDeliveryDailyReport:
    session_root = records_root / session_date.isoformat()
    reports: list[LateDeliverySessionReport] = []
    incomplete_session_ids: list[str] = []
    replay_failed_session_ids: list[str] = []
    if session_root.exists():
        for path in sorted(session_root.glob("*/late_delivery_evidence.json")):
            raw = _mapping(json.loads(path.read_text()), "late-delivery session report")
            if raw.get("schema") != LATE_DELIVERY_SESSION_SCHEMA:
                raise ValueError(f"unsupported late-delivery session schema: {path}")
            if _date(raw["session_date"], "session_date") != session_date:
                raise ValueError(f"late-delivery report date mismatch: {path}")
            reports.append(_session_report_from_mapping(raw))
        for path in sorted(session_root.glob("*/passive_capture_report.json")):
            raw = _mapping(json.loads(path.read_text()), "passive capture report")
            if raw.get("schema") != "late-delivery-passive-capture-report-v1":
                raise ValueError(f"unsupported passive capture report schema: {path}")
            session_id = _non_empty(raw["session_id"], "session_id")
            status = _non_empty(raw["status"], "status")
            if status == "INCOMPLETE":
                incomplete_session_ids.append(session_id)
            elif status == "REPLAY_FAILED":
                replay_failed_session_ids.append(session_id)

    all_events = tuple(
        event
        for report in reports
        for event in report.late_deliveries
    )
    by_stream = _totals_by_stream(reports, all_events)
    by_symbol = _aggregate_scoped_summaries(
        reports=reports,
        events=all_events,
        scope_name="symbol",
    )
    by_phase = _aggregate_scoped_summaries(
        reports=reports,
        events=all_events,
        scope_name="phase",
    )
    return LateDeliveryDailyReport(
        session_date=session_date,
        session_count=len(reports),
        incomplete_session_ids=tuple(sorted(set(incomplete_session_ids))),
        replay_failed_session_ids=tuple(sorted(set(replay_failed_session_ids))),
        by_stream=by_stream,
        by_symbol=by_symbol,
        by_phase=by_phase,
    )


def write_daily_late_delivery_report(path: Path, report: LateDeliveryDailyReport) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = _canonical_json(report.to_dict()) + b"\n"
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("wb") as output:
        output.write(encoded)
        output.flush()
        os.fsync(output.fileno())
    os.replace(temporary, path)
    return path


def _totals_by_stream(
    reports: tuple[LateDeliverySessionReport, ...] | list[LateDeliverySessionReport],
    events: tuple[LateDeliveryEvent, ...],
) -> dict[str, LateDeliveryTotals]:
    values: dict[str, list[int]] = {"TICK": [0, 0, 0], "BIDASK": [0, 0, 0]}
    for report in reports:
        for stream, total in report.stream_totals.items():
            bucket = values[stream]
            bucket[0] += total.total_events
            bucket[1] += total.accepted_count
            bucket[2] += total.rejected_count
    return {
        stream: LateDeliveryTotals.from_events(
            total_events=value[0],
            accepted_count=value[1],
            rejected_count=value[2],
            late_events=tuple(event for event in events if event.stream_kind == stream),
        )
        for stream, value in sorted(values.items())
    }


def _empty_counts() -> dict[str, list[int]]:
    return {"TICK": [0, 0, 0], "BIDASK": [0, 0, 0]}


def _summary_from_counts(
    counts: Mapping[str, list[int]],
    events: tuple[LateDeliveryEvent, ...],
) -> dict[str, LateDeliveryTotals]:
    return {
        stream: LateDeliveryTotals.from_events(
            total_events=values[0],
            accepted_count=values[1],
            rejected_count=values[2],
            late_events=tuple(event for event in events if event.stream_kind == stream),
        )
        for stream, values in sorted(counts.items())
    }


def _aggregate_scoped_summaries(
    *,
    reports: list[LateDeliverySessionReport],
    events: tuple[LateDeliveryEvent, ...],
    scope_name: str,
) -> dict[str, LateDeliverySymbolSummary]:
    scoped: dict[str, dict[str, list[int]]] = {}
    for report in reports:
        summaries = report.by_symbol if scope_name == "symbol" else report.by_phase
        for key, summary in summaries.items():
            target = scoped.setdefault(key, _empty_counts())
            for stream, total in summary.by_stream.items():
                bucket = target[stream]
                bucket[0] += total.total_events
                bucket[1] += total.accepted_count
                bucket[2] += total.rejected_count
    return {
        key: LateDeliverySymbolSummary(
            by_stream=_summary_from_counts(
                values,
                tuple(
                    item
                    for item in events
                    if (
                        item.symbol == key
                        if scope_name == "symbol"
                        else item.session_phase is not None
                        and item.session_phase.value == key
                    )
                ),
            )
        )
        for key, values in sorted(scoped.items())
    }


def _session_report_from_mapping(raw: Mapping[str, object]) -> LateDeliverySessionReport:
    events = tuple(_late_event_from_mapping(item) for item in _object_list(raw["late_deliveries"], "late_deliveries"))
    stream_raw = _mapping(raw["stream_totals"], "stream_totals")
    totals = {
        stream: _totals_from_mapping(_mapping(value, f"stream_totals.{stream}"))
        for stream, value in stream_raw.items()
    }
    if set(totals) != {"TICK", "BIDASK"}:
        raise ValueError("late-delivery report must contain Tick and BidAsk totals")
    by_symbol = _scoped_summaries_from_mapping(raw["by_symbol"], "by_symbol")
    by_phase = _scoped_summaries_from_mapping(raw["by_phase"], "by_phase")
    if raw.get("policy_interpretation") != "PROHIBITED_EVIDENCE_ONLY":
        raise ValueError("late-delivery report must not contain a policy interpretation")
    return LateDeliverySessionReport(
        session_id=_non_empty(raw["session_id"], "session_id"),
        session_date=_date(raw["session_date"], "session_date"),
        journal_sha256=_non_empty(raw["journal_sha256"], "journal_sha256"),
        status=_non_empty(raw["status"], "status"),
        stream_totals=totals,
        by_symbol=by_symbol,
        by_phase=by_phase,
        late_deliveries=events,
    )


def _scoped_summaries_from_mapping(
    raw: object,
    field_name: str,
) -> dict[str, LateDeliverySymbolSummary]:
    mapping = _mapping(raw, field_name)
    result: dict[str, LateDeliverySymbolSummary] = {}
    for key, value in mapping.items():
        summary = _mapping(value, f"{field_name}.{key}")
        if set(summary) != {"by_stream"}:
            raise ValueError(f"{field_name}.{key} fields do not match contract")
        streams = _mapping(summary["by_stream"], f"{field_name}.{key}.by_stream")
        totals = {
            stream: _totals_from_mapping(
                _mapping(total, f"{field_name}.{key}.by_stream.{stream}")
            )
            for stream, total in streams.items()
        }
        if set(totals) != {"TICK", "BIDASK"}:
            raise ValueError(f"{field_name}.{key} must contain Tick and BidAsk totals")
        result[_non_empty(key, field_name)] = LateDeliverySymbolSummary(by_stream=totals)
    return result


def _late_event_from_mapping(raw: Mapping[str, object]) -> LateDeliveryEvent:
    phase_raw = raw.get("session_phase")
    return LateDeliveryEvent(
        session_id=_non_empty(raw["session_id"], "session_id"),
        session_date=_date(raw["session_date"], "session_date"),
        symbol=_symbol(raw["symbol"]),
        stream_kind=_non_empty(raw["stream_kind"], "stream_kind"),
        record_index=_integer(raw["record_index"], "record_index"),
        ingress_record_index=_integer(raw["ingress_record_index"], "ingress_record_index"),
        event_id=_non_empty(raw["event_id"], "event_id"),
        source_ts=_aware(raw["source_ts"], "source_ts"),
        received_ts=_aware(raw["received_ts"], "received_ts"),
        previous_watermark_source_ts=_aware(
            raw["previous_watermark_source_ts"], "previous_watermark_source_ts"
        ),
        previous_watermark_ingress_sequence=_integer(
            raw["previous_watermark_ingress_sequence"],
            "previous_watermark_ingress_sequence",
        ),
        source_regression_ms=_number(raw["source_regression_ms"], "source_regression_ms"),
        receive_progression_ms=(
            _number(raw["receive_progression_ms"], "receive_progression_ms")
            if raw.get("receive_progression_ms") is not None
            else None
        ),
        consecutive_late_count=_integer(
            raw["consecutive_late_count"], "consecutive_late_count"
        ),
        time_since_previous_late_ms=(
            _number(raw["time_since_previous_late_ms"], "time_since_previous_late_ms")
            if raw.get("time_since_previous_late_ms") is not None
            else None
        ),
        session_phase=SessionPhase(phase_raw) if phase_raw is not None else None,
        projection_effect=_non_empty(raw["projection_effect"], "projection_effect"),
        health_effect=_non_empty(raw["health_effect"], "health_effect"),
        admission_effect=_non_empty(raw["admission_effect"], "admission_effect"),
    )


def _totals_from_mapping(raw: Mapping[str, object]) -> LateDeliveryTotals:
    return LateDeliveryTotals(
        total_events=_integer(raw["total_events"], "total_events"),
        accepted_count=_integer(raw["accepted_count"], "accepted_count"),
        rejected_count=_integer(raw["rejected_count"], "rejected_count"),
        late_delivery_count=_integer(raw["late_delivery_count"], "late_delivery_count"),
        late_delivery_ratio=(
            _number(raw["late_delivery_ratio"], "late_delivery_ratio")
            if raw.get("late_delivery_ratio") is not None
            else None
        ),
        regression_abs_p50_ms=(
            _number(raw["regression_abs_p50_ms"], "regression_abs_p50_ms")
            if raw.get("regression_abs_p50_ms") is not None
            else None
        ),
        regression_abs_p90_ms=(
            _number(raw["regression_abs_p90_ms"], "regression_abs_p90_ms")
            if raw.get("regression_abs_p90_ms") is not None
            else None
        ),
        regression_abs_p95_ms=(
            _number(raw["regression_abs_p95_ms"], "regression_abs_p95_ms")
            if raw.get("regression_abs_p95_ms") is not None
            else None
        ),
        regression_abs_p99_ms=(
            _number(raw["regression_abs_p99_ms"], "regression_abs_p99_ms")
            if raw.get("regression_abs_p99_ms") is not None
            else None
        ),
        regression_abs_max_ms=(
            _number(raw["regression_abs_max_ms"], "regression_abs_max_ms")
            if raw.get("regression_abs_max_ms") is not None
            else None
        ),
        consecutive_late_max=_integer(raw["consecutive_late_max"], "consecutive_late_max"),
    )


def _validate_session_windows(value: object) -> None:
    windows = _object_list(value, "session_windows")
    expected = {phase.value: (starts, ends) for phase, starts, ends in _PHASE_WINDOWS}
    actual: dict[str, tuple[time, time]] = {}
    for item in windows:
        if set(item) != {"phase", "start_local", "end_local"}:
            raise ValueError("session window fields do not match contract")
        phase = _non_empty(item["phase"], "session_window.phase")
        actual[phase] = (
            _time(item["start_local"], "session_window.start_local"),
            _time(item["end_local"], "session_window.end_local"),
        )
    if actual != expected:
        raise ValueError("session windows do not match OPEN/MID/CLOSE collection contract")


def _admission(health_state: str) -> str:
    return "OPEN" if health_state == "HEALTHY" else "BLOCK_NEW_ENTRY"


def _transition(before: str, after: str) -> str:
    return "NO_TRANSITION" if before == after else f"{before}_TO_{after}"


def _percentile(values: list[float], percentile: float) -> float | None:
    if not values:
        return None
    position = (len(values) - 1) * percentile
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()


def _mapping(value: object, field_name: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _object_list(value: object, field_name: str) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        raise ValueError(f"{field_name} must be a list")
    return [_mapping(item, field_name) for item in value]


def _non_empty(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _symbol(value: object) -> str:
    symbol = _non_empty(value, "symbol").upper()
    if symbol != str(value).strip().upper():
        raise ValueError("symbol must be normalized")
    return symbol


def _date(value: object, field_name: str) -> date:
    try:
        return date.fromisoformat(_non_empty(value, field_name))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO date") from error


def _aware(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_non_empty(value, field_name))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO datetime") from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")
    return parsed


def _time(value: object, field_name: str) -> time:
    try:
        return time.fromisoformat(_non_empty(value, field_name))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO local time") from error


def _integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be an integer")
    return value


def _number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a number")
    return float(value)
