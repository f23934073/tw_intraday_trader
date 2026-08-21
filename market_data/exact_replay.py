"""Exact reconstruction of canonical projections from finalized artifacts."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Mapping

from market_data.events import EventEnvelope, InstrumentReference, MarketStreamKind
from market_data.health import DataHealth, DataHealthReason, DataHealthState
from market_data.ingestion import IngestResult, MarketDataIngestor
from market_data.instrument_reference import InstrumentReferenceStore
from market_data.intraday_bar_store import IntradayBarStore
from market_data.journal import JournalRecordType, verify_market_event_journal
from market_data.order_book_store import OrderBookStore
from market_data.serialization import deserialize_event_envelope


INSTRUMENT_REFERENCE_SCHEMA = "instrument-reference-v1"
BOOTSTRAP_SNAPSHOT_SCHEMA = "bootstrap-snapshot-v1"
PROJECTION_STATE_SCHEMA = "projection-state-v1"
PROJECTION_DIGEST_SET_SCHEMA = "projection-digest-set-v1"
EXACT_REPLAY_ENGINE_VERSION = "exact-projection-replay-v1"

_DIGEST_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
_ROOT_IDENTITY_FIELDS = {
    "artifact_id",
    "session_id",
    "session_date",
    "timezone",
    "status",
}
_REFERENCE_ROOT_FIELDS = _ROOT_IDENTITY_FIELDS | {
    "schema",
    "source",
    "reference_count",
    "content_sha256",
    "references",
}
_REFERENCE_SOURCE_FIELDS = {
    "provider",
    "source_mode",
    "source_identity",
    "captured_at",
}
_REFERENCE_FIELDS = {
    "instrument_id",
    "symbol",
    "exchange",
    "security_type",
    "name",
    "valid_from",
    "valid_to",
    "reference_price",
    "limit_up_price",
    "limit_down_price",
    "price_limit_applies",
    "trading_unit_shares",
    "source_updated_at",
    "source_identity",
}
_BOOTSTRAP_ROOT_FIELDS = _ROOT_IDENTITY_FIELDS | {
    "schema",
    "source",
    "captured_at",
    "received_at",
    "journal_boundary",
    "calendar",
    "coverage",
    "subscriptions",
    "symbols",
    "projection_seed_mode",
    "content_sha256",
}
_BOOTSTRAP_SOURCE_FIELDS = {"provider", "source_mode", "source_identity"}
_BOUNDARY_FIELDS = {
    "first_record_index",
    "first_ingress_sequence",
    "projection_started_at",
}
_CALENDAR_FIELDS = {
    "calendar_id",
    "calendar_version",
    "session_phase",
    "scheduled_open",
    "scheduled_close",
}
_COVERAGE_FIELDS = {
    "required_instrument_ids",
    "captured_instrument_ids",
    "missing_instrument_ids",
}
_SUBSCRIPTION_FIELDS = {
    "instrument_id",
    "stream_kind",
    "state",
    "effective_at",
    "evidence_identity",
}
_SYMBOL_FIELDS = {
    "instrument_id",
    "symbol",
    "prior_session_date",
    "previous_close",
    "previous_session_volume_lots",
    "source_identity",
}
_PROJECTION_ROOT_FIELDS = _ROOT_IDENTITY_FIELDS | {
    "schema",
    "input_digests",
    "versions",
    "initialization",
    "expected_final",
    "content_sha256",
}
_INPUT_DIGEST_FIELDS = {
    "journal_sha256",
    "instrument_reference_sha256",
    "bootstrap_sha256",
}
_VERSION_FIELDS = {
    "ingestor",
    "bar_projection",
    "book_projection",
    "health_projection",
    "replay_engine",
}
_INITIALIZATION_FIELDS = {
    "mode",
    "initialized_at",
    "retention_seconds",
    "reference_store",
    "bar",
    "book",
    "health",
    "ready_transition",
}
_HEALTH_INITIAL_FIELDS = {
    "state",
    "reasons",
    "streams",
    "queue_depth",
    "queue_high_watermark",
    "queue_overflow_count",
    "session_mismatch_count",
    "invalid_count",
    "gap_count",
    "source_clock_skew_count",
    "reconnect_epoch",
    "resync_verified_at",
    "as_of",
}
_DIGEST_NAMES = (
    "disposition_v1",
    "bar_v1",
    "book_v1",
    "health_v1",
)
_DIGEST_CONTRACTS = {
    "disposition_v1": ("ingest-disposition-digest-v1", "MarketDataIngestor"),
    "bar_v1": ("bar-projection-digest-v1", "IntradayBarStore"),
    "book_v1": ("book-projection-digest-v1", "OrderBookStore"),
    "health_v1": (
        "data-health-replay-v1",
        "ReplaySemanticHealthProjection",
    ),
}
_MISMATCH_CODES = {
    "disposition_v1": "DISPOSITION_MISMATCH",
    "bar_v1": "BAR_DIGEST_MISMATCH",
    "book_v1": "BOOK_DIGEST_MISMATCH",
    "health_v1": "DATA_HEALTH_DIGEST_MISMATCH",
}


class ExactReplayError(ValueError):
    def __init__(self, code: str, detail: str) -> None:
        self.code = code
        self.detail = detail
        super().__init__(f"{code}: {detail}")


@dataclass(frozen=True)
class ProjectionDigestEntry:
    contract: str
    owner: str
    sha256: str

    def to_contract_dict(self) -> dict[str, str]:
        return {
            "contract": self.contract,
            "owner": self.owner,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class ProjectionDigestSet:
    disposition_v1: ProjectionDigestEntry
    bar_v1: ProjectionDigestEntry
    book_v1: ProjectionDigestEntry
    health_v1: ProjectionDigestEntry

    def to_contract_dict(self) -> dict[str, object]:
        return {
            "digest_set_schema": PROJECTION_DIGEST_SET_SCHEMA,
            **{
                name: getattr(self, name).to_contract_dict()
                for name in _DIGEST_NAMES
            },
        }


@dataclass(frozen=True)
class ProjectionDigestComparison:
    name: str
    expected: str
    actual: str
    match: bool
    first_divergence: str | int | None


@dataclass(frozen=True)
class ExactReplayVerificationResult:
    valid: bool
    errors: tuple[str, ...]
    comparisons: tuple[ProjectionDigestComparison, ...]
    actual: ProjectionDigestSet | None
    repeat_count: int


@dataclass(frozen=True)
class ExactReplayInputs:
    session_id: str
    session_date: date
    timezone: str
    journal_sha256: str
    records: tuple[Mapping[str, object], ...]
    references: tuple[InstrumentReference, ...]
    initialized_at: datetime
    retention: timedelta
    ready_at: datetime | None
    ready_evidence: str | None
    expected_reference_digest: str
    expected_bar_initial_digest: str
    expected_book_initial_digest: str
    expected: ProjectionDigestSet
    repeat_count: int


def build_live_projection_digest_set(
    *,
    session_id: str,
    session_date: date,
    records: tuple[Mapping[str, object], ...],
    health: DataHealth,
    bar_digest: str,
    book_digest: str,
    initial_state: DataHealthState,
) -> ProjectionDigestSet:
    """Build expected digests from durable records and live projections.

    This is the capture-side boundary.  It deliberately does not invoke the
    replay runtime, so a qualification cannot manufacture its expected result
    by replaying the same Journal it is supposed to verify.
    """
    disposition_payloads: list[dict[str, object]] = []
    transitions: list[dict[str, object]] = []
    incidents: list[dict[str, object]] = []
    semantic_state = initial_state
    for record in records:
        record_type = str(record["record_type"])
        record_index = int(record["record_index"])
        if record_type == JournalRecordType.DISPOSITION:
            result = dict(_mapping(record, "result"))
            disposition_payloads.append(
                {
                    "record_index": record_index,
                    "ingress_record_index": int(record["ingress_record_index"]),
                    "result": result,
                }
            )
            transition = _health_transition_payload(record_index, result)
            if transition is not None:
                transitions.append(transition)
            semantic_state = DataHealthState(str(result["health_after"]))
        elif record_type == JournalRecordType.SYSTEM_INCIDENT:
            incident, semantic_state = _semantic_incident(
                record_index,
                _mapping(record, "incident"),
                semantic_state,
            )
            incidents.append(incident)
    health_payload = _semantic_health_payload(
        session_id=session_id,
        session_date=session_date,
        health=health,
        transitions=transitions,
        incidents=incidents,
        semantic_state=semantic_state,
    )
    return ProjectionDigestSet(
        disposition_v1=_digest_entry("disposition_v1", disposition_payloads),
        bar_v1=_digest_entry("bar_v1", bar_digest),
        book_v1=_digest_entry("book_v1", book_digest),
        health_v1=_digest_entry("health_v1", health_payload),
    )


def load_exact_replay_inputs(
    *,
    session_dir: Path,
    bootstrap_path: Path,
    instrument_reference_path: Path,
) -> ExactReplayInputs:
    journal = verify_market_event_journal(session_dir)
    if not journal.valid:
        code = (
            "INCOMPLETE_REPLAY_INPUT"
            if journal.manifest is not None
            and journal.manifest.get("status") == "INCOMPLETE"
            else "JOURNAL_INTEGRITY_FAILED"
        )
        raise ExactReplayError(code, "; ".join(journal.errors))
    if journal.manifest is None or journal.calculated_sha256 is None:
        raise ExactReplayError("JOURNAL_INTEGRITY_FAILED", "manifest is unavailable")

    reference_raw = _load_artifact(
        instrument_reference_path,
        "MISSING_REFERENCE_ARTIFACT",
    )
    bootstrap_raw = _load_artifact(
        bootstrap_path,
        "MISSING_BOOTSTRAP_ARTIFACT",
    )
    projection_raw = _load_artifact(
        session_dir / "projection_state.json",
        "MISSING_PROJECTION_STATE",
    )

    references, reference_digest = _load_references(reference_raw)
    bootstrap_digest, initialized_at = _validate_bootstrap(bootstrap_raw)
    _validate_projection_state(projection_raw)
    manifest = journal.manifest
    identity = (
        str(manifest["session_id"]),
        date.fromisoformat(str(manifest["session_date"])),
        str(manifest["timezone"]),
    )
    for artifact_name, raw in (
        ("instrument reference", reference_raw),
        ("bootstrap", bootstrap_raw),
        ("projection state", projection_raw),
    ):
        artifact_identity = (
            str(raw["session_id"]),
            date.fromisoformat(str(raw["session_date"])),
            str(raw["timezone"]),
        )
        if artifact_identity != identity:
            raise ExactReplayError(
                "SESSION_IDENTITY_MISMATCH",
                f"{artifact_name} does not match Journal",
            )

    _validate_journal_boundary_and_coverage(
        records=journal.records,
        bootstrap=bootstrap_raw,
        references=reference_raw,
    )

    input_digests = _mapping(projection_raw, "input_digests")
    expected_inputs = {
        "journal_sha256": journal.calculated_sha256,
        "instrument_reference_sha256": reference_digest,
        "bootstrap_sha256": bootstrap_digest,
    }
    if dict(input_digests) != expected_inputs:
        raise ExactReplayError(
            "INPUT_DIGEST_MISMATCH",
            "projection state does not bind the supplied input artifacts",
        )

    required_ids = set(_string_list(_mapping(bootstrap_raw, "coverage"), "required_instrument_ids"))
    reference_ids = {
        _non_empty(item, "instrument_id")
        for item in _object_list(reference_raw, "references")
    }
    if required_ids != reference_ids:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "bootstrap coverage and instrument references differ",
        )

    initialization = _mapping(projection_raw, "initialization")
    if initialized_at != _aware(initialization["initialized_at"], "initialized_at"):
        raise ExactReplayError(
            "SESSION_IDENTITY_MISMATCH",
            "bootstrap and projection initialization times differ",
        )
    ready = initialization.get("ready_transition")
    ready_at: datetime | None = None
    ready_evidence: str | None = None
    if ready is not None:
        if not isinstance(ready, dict) or set(ready) != {"occurred_at", "evidence"}:
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "ready_transition fields do not match contract",
            )
        ready_at = _aware(ready["occurred_at"], "ready_transition.occurred_at")
        ready_evidence = _non_empty(ready, "evidence")

    expected = _digest_set(_mapping(_mapping(projection_raw, "expected_final"), "digest_set"))
    manifest_projection = _mapping(manifest, "projection_digest")
    if (
        expected.bar_v1.sha256 != manifest_projection.get("bar")
        or expected.book_v1.sha256 != manifest_projection.get("book")
    ):
        raise ExactReplayError(
            "INPUT_DIGEST_MISMATCH",
            "versioned Bar/Book digests do not match the Journal manifest",
        )

    return ExactReplayInputs(
        session_id=identity[0],
        session_date=identity[1],
        timezone=identity[2],
        journal_sha256=journal.calculated_sha256,
        records=journal.records,
        references=references,
        initialized_at=initialized_at,
        retention=timedelta(seconds=_integer(initialization, "retention_seconds")),
        ready_at=ready_at,
        ready_evidence=ready_evidence,
        expected_reference_digest=_non_empty(
            _mapping(initialization, "reference_store"),
            "expected_initial_digest",
        ),
        expected_bar_initial_digest=_initial_projection_digest(
            initialization,
            "bar",
        ),
        expected_book_initial_digest=_initial_projection_digest(
            initialization,
            "book",
        ),
        expected=expected,
        repeat_count=_integer(_mapping(projection_raw, "expected_final"), "repeat_count"),
    )


class ExactProjectionReplayRuntime:
    """Pure artifact-to-projection reconstruction; no CLI or wall clock access."""

    def reconstruct(self, inputs: ExactReplayInputs) -> ProjectionDigestSet:
        references = InstrumentReferenceStore(inputs.session_date)
        for reference in inputs.references:
            references.put(reference)
        bars = IntradayBarStore(inputs.session_date, retention=inputs.retention)
        books = OrderBookStore(inputs.session_date, retention=inputs.retention)
        health = DataHealth(inputs.session_date, started_at=inputs.initialized_at)

        if references.digest != inputs.expected_reference_digest:
            raise ExactReplayError(
                "INITIAL_STATE_DIGEST_MISMATCH",
                "InstrumentReferenceStore initial digest differs",
            )
        if bars.digest != inputs.expected_bar_initial_digest:
            raise ExactReplayError(
                "INITIAL_STATE_DIGEST_MISMATCH",
                "Bar initial digest differs",
            )
        if books.digest != inputs.expected_book_initial_digest:
            raise ExactReplayError(
                "INITIAL_STATE_DIGEST_MISMATCH",
                "Book initial digest differs",
            )
        if inputs.ready_at is not None:
            health.mark_ready(
                occurred_at=inputs.ready_at,
                evidence=inputs.ready_evidence or "",
            )

        ingestor = MarketDataIngestor(
            session_id=inputs.session_id,
            session_date=inputs.session_date,
            references=references,
            bars=bars,
            books=books,
            health=health,
        )
        ingress: dict[int, EventEnvelope] = {}
        disposition_payloads: list[dict[str, object]] = []
        health_transitions: list[dict[str, object]] = []
        incidents: list[dict[str, object]] = []
        semantic_state = health.state

        for record in inputs.records:
            record_type = str(record["record_type"])
            record_index = int(record["record_index"])
            if record_type == JournalRecordType.INGRESS:
                event = record["event"]
                ingress[record_index] = deserialize_event_envelope(
                    json.dumps(event, sort_keys=True, separators=(",", ":"))
                )
            elif record_type == JournalRecordType.DISPOSITION:
                ingress_index = int(record["ingress_record_index"])
                result = ingestor.ingest(ingress[ingress_index])
                actual_result = _ingest_result_payload(result)
                if actual_result != record["result"]:
                    raise ExactReplayError(
                        "DISPOSITION_MISMATCH",
                        f"record_index={record_index}, ingress_record_index={ingress_index}",
                    )
                disposition_payloads.append(
                    {
                        "record_index": record_index,
                        "ingress_record_index": ingress_index,
                        "result": actual_result,
                    }
                )
                transition = _health_transition(record_index, result)
                if transition is not None:
                    health_transitions.append(transition)
                semantic_state = result.health_after
            elif record_type == JournalRecordType.SYSTEM_INCIDENT:
                incident = dict(_mapping(record, "incident"))
                semantic_incident, semantic_state = _semantic_incident(
                    record_index,
                    incident,
                    semantic_state,
                )
                incidents.append(semantic_incident)

        health_payload = _semantic_health_payload(
            session_id=inputs.session_id,
            session_date=inputs.session_date,
            health=health,
            transitions=health_transitions,
            incidents=incidents,
            semantic_state=semantic_state,
        )
        return ProjectionDigestSet(
            disposition_v1=_digest_entry(
                "disposition_v1",
                disposition_payloads,
            ),
            bar_v1=_digest_entry("bar_v1", bars.finalize_session()),
            book_v1=_digest_entry("book_v1", books.finalize_session()),
            health_v1=_digest_entry("health_v1", health_payload),
        )


def verify_exact_projection_replay(
    *,
    session_dir: Path,
    bootstrap_path: Path,
    instrument_reference_path: Path,
) -> ExactReplayVerificationResult:
    try:
        inputs = load_exact_replay_inputs(
            session_dir=session_dir,
            bootstrap_path=bootstrap_path,
            instrument_reference_path=instrument_reference_path,
        )
        actual_runs = tuple(
            ExactProjectionReplayRuntime().reconstruct(inputs)
            for _ in range(inputs.repeat_count)
        )
    except ExactReplayError as error:
        return ExactReplayVerificationResult(
            valid=False,
            errors=(str(error),),
            comparisons=(),
            actual=None,
            repeat_count=0,
        )
    if not actual_runs:
        return ExactReplayVerificationResult(
            valid=False,
            errors=("INCOMPLETE_REPLAY_INPUT: repeat_count must be positive",),
            comparisons=(),
            actual=None,
            repeat_count=0,
        )
    first = actual_runs[0]
    if any(item != first for item in actual_runs[1:]):
        return ExactReplayVerificationResult(
            valid=False,
            errors=("NON_DETERMINISTIC_REPLAY: repeated digest sets differ",),
            comparisons=(),
            actual=first,
            repeat_count=len(actual_runs),
        )
    comparisons = tuple(
        ProjectionDigestComparison(
            name=name,
            expected=getattr(inputs.expected, name).sha256,
            actual=getattr(first, name).sha256,
            match=(
                getattr(inputs.expected, name).sha256
                == getattr(first, name).sha256
            ),
            first_divergence=(
                None
                if getattr(inputs.expected, name).sha256
                == getattr(first, name).sha256
                else "UNKNOWN_NOT_RECORDED"
            ),
        )
        for name in _DIGEST_NAMES
    )
    errors = tuple(
        _MISMATCH_CODES[item.name]
        for item in comparisons
        if not item.match
    )
    return ExactReplayVerificationResult(
        valid=not errors,
        errors=errors,
        comparisons=comparisons,
        actual=first,
        repeat_count=len(actual_runs),
    )


def _load_references(
    raw: Mapping[str, object],
) -> tuple[tuple[InstrumentReference, ...], str]:
    _exact_fields(raw, _REFERENCE_ROOT_FIELDS, "instrument reference")
    _require_finalized(raw, INSTRUMENT_REFERENCE_SCHEMA)
    _exact_fields(_mapping(raw, "source"), _REFERENCE_SOURCE_FIELDS, "reference source")
    _validate_non_empty_fields(
        _mapping(raw, "source"),
        ("provider", "source_mode", "source_identity"),
    )
    _aware(_mapping(raw, "source")["captured_at"], "source.captured_at")
    content_digest = _verify_content_digest(
        raw,
        {"status", "reference_count", "content_sha256"},
    )
    session_date = _date(raw["session_date"], "session_date")
    references_raw = _object_list(raw, "references")
    if _integer(raw, "reference_count") != len(references_raw) or not references_raw:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "instrument reference_count is incomplete",
        )
    identities: set[str] = set()
    symbol_keys: set[tuple[str, str]] = set()
    runtime: list[InstrumentReference] = []
    sort_keys: list[tuple[str, str, str]] = []
    for item in references_raw:
        _exact_fields(item, _REFERENCE_FIELDS, "instrument reference entry")
        _validate_non_empty_fields(
            item,
            (
                "instrument_id",
                "symbol",
                "exchange",
                "security_type",
                "name",
                "source_identity",
            ),
        )
        instrument_id = _non_empty(item, "instrument_id")
        symbol = _non_empty(item, "symbol")
        exchange = _non_empty(item, "exchange")
        if symbol != symbol.strip().upper() or exchange != exchange.strip().upper():
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "instrument symbol/exchange must be normalized",
            )
        if instrument_id != f"{exchange}:{symbol}":
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "instrument_id must equal exchange:symbol",
            )
        valid_from = _date(item["valid_from"], "valid_from")
        valid_to = _date(item["valid_to"], "valid_to")
        source_updated = _date(item["source_updated_at"], "source_updated_at")
        if not valid_from <= session_date <= valid_to or source_updated != session_date:
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "instrument validity/source date does not qualify the session",
            )
        reference_price = _decimal(item["reference_price"], "reference_price")
        price_limit_applies = _boolean(item, "price_limit_applies")
        limit_up = _optional_decimal(item["limit_up_price"], "limit_up_price")
        limit_down = _optional_decimal(item["limit_down_price"], "limit_down_price")
        if price_limit_applies and (
            limit_up is None
            or limit_down is None
            or not limit_down <= reference_price <= limit_up
        ):
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "instrument price limits are invalid",
            )
        if not price_limit_applies and (limit_up is not None or limit_down is not None):
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "non-limited instrument must have null limits",
            )
        key = (exchange, symbol)
        if instrument_id in identities or key in symbol_keys:
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "duplicate instrument identity",
            )
        identities.add(instrument_id)
        symbol_keys.add(key)
        sort_keys.append((exchange, symbol, instrument_id))
        runtime.append(
            InstrumentReference(
                symbol=symbol,
                exchange=exchange,
                session_date=session_date,
                reference_price=reference_price,
                limit_up_price=limit_up,
                limit_down_price=limit_down,
                price_limit_applies=price_limit_applies,
                trading_unit_shares=_positive_integer(
                    item,
                    "trading_unit_shares",
                ),
                source_updated_at=source_updated,
            )
        )
    if sort_keys != sorted(sort_keys):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "instrument references are not canonically ordered",
        )
    return tuple(runtime), content_digest


def _validate_bootstrap(raw: Mapping[str, object]) -> tuple[str, datetime]:
    _exact_fields(raw, _BOOTSTRAP_ROOT_FIELDS, "bootstrap")
    _require_finalized(raw, BOOTSTRAP_SNAPSHOT_SCHEMA)
    _exact_fields(_mapping(raw, "source"), _BOOTSTRAP_SOURCE_FIELDS, "bootstrap source")
    _validate_non_empty_fields(
        _mapping(raw, "source"),
        ("provider", "source_mode", "source_identity"),
    )
    captured_at = _aware(raw["captured_at"], "captured_at")
    received_at = _aware(raw["received_at"], "received_at")
    boundary = _mapping(raw, "journal_boundary")
    _exact_fields(boundary, _BOUNDARY_FIELDS, "journal boundary")
    if _integer(boundary, "first_record_index") != 1:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "bootstrap first_record_index must be 1",
        )
    if _integer(boundary, "first_ingress_sequence") < 0:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "bootstrap first_ingress_sequence must be non-negative",
        )
    initialized_at = _aware(
        boundary["projection_started_at"],
        "projection_started_at",
    )
    if captured_at > received_at or received_at > initialized_at:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "bootstrap capture/receipt must precede projection start",
        )
    calendar = _mapping(raw, "calendar")
    _exact_fields(calendar, _CALENDAR_FIELDS, "calendar")
    _validate_non_empty_fields(
        calendar,
        ("calendar_id", "calendar_version", "session_phase"),
    )
    scheduled_open = _aware(calendar["scheduled_open"], "scheduled_open")
    scheduled_close = _aware(calendar["scheduled_close"], "scheduled_close")
    if not scheduled_open <= initialized_at <= scheduled_close:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "calendar does not cover projection initialization",
        )
    coverage = _mapping(raw, "coverage")
    _exact_fields(coverage, _COVERAGE_FIELDS, "coverage")
    required = _string_list(coverage, "required_instrument_ids")
    captured = _string_list(coverage, "captured_instrument_ids")
    missing = _string_list(coverage, "missing_instrument_ids")
    if required != sorted(set(required)) or captured != required or missing:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "bootstrap symbol coverage is incomplete or unordered",
        )
    subscriptions = _object_list(raw, "subscriptions")
    subscription_keys: list[tuple[str, str]] = []
    for item in subscriptions:
        _exact_fields(item, _SUBSCRIPTION_FIELDS, "subscription")
        _validate_non_empty_fields(
            item,
            ("instrument_id", "state", "evidence_identity"),
        )
        kind = MarketStreamKind(_non_empty(item, "stream_kind"))
        if _non_empty(item, "state") == "UNKNOWN":
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "bootstrap subscription state is UNKNOWN",
            )
        if _aware(item["effective_at"], "effective_at") > initialized_at:
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "subscription state is after the Journal boundary",
            )
        subscription_keys.append((_non_empty(item, "instrument_id"), kind.value))
    if subscription_keys != sorted(set(subscription_keys)):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "subscriptions are duplicate or unordered",
        )
    symbols = _object_list(raw, "symbols")
    symbol_ids: list[str] = []
    for item in symbols:
        _exact_fields(item, _SYMBOL_FIELDS, "bootstrap symbol")
        _validate_non_empty_fields(
            item,
            ("instrument_id", "symbol", "source_identity"),
        )
        _date(item["prior_session_date"], "prior_session_date")
        _decimal(item["previous_close"], "previous_close")
        _non_negative_integer(item, "previous_session_volume_lots")
        symbol_ids.append(_non_empty(item, "instrument_id"))
    if symbol_ids != required:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "bootstrap symbol entries do not match coverage",
        )
    if raw["projection_seed_mode"] != "EMPTY_SESSION":
        raise ExactReplayError(
            "RESTORED_STATE_UNSUPPORTED",
            "projection_seed_mode must be EMPTY_SESSION",
        )
    return _verify_content_digest(raw, {"status", "content_sha256"}), initialized_at


def _validate_projection_state(raw: Mapping[str, object]) -> None:
    _exact_fields(raw, _PROJECTION_ROOT_FIELDS, "projection state")
    _require_finalized(raw, PROJECTION_STATE_SCHEMA)
    _exact_fields(_mapping(raw, "input_digests"), _INPUT_DIGEST_FIELDS, "input digests")
    for value in _mapping(raw, "input_digests").values():
        _require_digest(value, "input digest")
    versions = _mapping(raw, "versions")
    _exact_fields(versions, _VERSION_FIELDS, "versions")
    expected_versions = {
        "ingestor": "market-data-ingestor-v1",
        "bar_projection": "bar-projection-digest-v1",
        "book_projection": "book-projection-digest-v1",
        "health_projection": "data-health-replay-v1",
        "replay_engine": EXACT_REPLAY_ENGINE_VERSION,
    }
    if dict(versions) != expected_versions:
        raise ExactReplayError(
            "PROJECTION_VERSION_MISMATCH",
            "projection implementation versions are unsupported",
        )
    initialization = _mapping(raw, "initialization")
    _exact_fields(initialization, _INITIALIZATION_FIELDS, "initialization")
    if initialization["mode"] != "EMPTY_SESSION":
        raise ExactReplayError(
            "RESTORED_STATE_UNSUPPORTED",
            "projection initialization mode must be EMPTY_SESSION",
        )
    if _integer(initialization, "retention_seconds") < 1200:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "projection retention must be at least 1200 seconds",
        )
    for name in ("reference_store", "bar", "book"):
        _mapping(initialization, name)
    for name in ("bar", "book"):
        value = _mapping(initialization, name)
        _exact_fields(
            value,
            {"mode", "finalized", "expected_initial_digest"},
            f"{name} initialization",
        )
        if value["mode"] != "EMPTY" or value["finalized"] is not False:
            raise ExactReplayError(
                "RESTORED_STATE_UNSUPPORTED",
                f"{name} initialization must be empty and unfinalized",
            )
    health = _mapping(initialization, "health")
    _exact_fields(health, _HEALTH_INITIAL_FIELDS, "health initialization")
    fixed_health = {
        "state": "STARTING",
        "reasons": [],
        "streams": [],
        "queue_depth": 0,
        "queue_high_watermark": 0,
        "queue_overflow_count": 0,
        "session_mismatch_count": 0,
        "invalid_count": 0,
        "gap_count": 0,
        "source_clock_skew_count": 0,
        "reconnect_epoch": 0,
        "resync_verified_at": None,
    }
    for key, value in fixed_health.items():
        if health[key] != value:
            raise ExactReplayError(
                "RESTORED_STATE_UNSUPPORTED",
                f"health initialization field {key} is not empty-session state",
            )
    initialized_at = _aware(initialization["initialized_at"], "initialized_at")
    if _aware(health["as_of"], "health.as_of") != initialized_at:
        raise ExactReplayError(
            "INITIAL_STATE_DIGEST_MISMATCH",
            "health as_of differs from initialized_at",
        )
    expected_final = _mapping(raw, "expected_final")
    _exact_fields(expected_final, {"repeat_count", "digest_set"}, "expected_final")
    if _integer(expected_final, "repeat_count") != 10:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "exact replay repeat_count must be 10",
        )
    _digest_set(_mapping(expected_final, "digest_set"))
    _verify_content_digest(raw, {"status", "content_sha256"})


def _digest_set(raw: Mapping[str, object]) -> ProjectionDigestSet:
    expected_fields = {"digest_set_schema", *_DIGEST_NAMES}
    _exact_fields(raw, expected_fields, "projection digest set")
    if raw["digest_set_schema"] != PROJECTION_DIGEST_SET_SCHEMA:
        raise ExactReplayError(
            "PROJECTION_VERSION_MISMATCH",
            "unsupported projection digest set schema",
        )
    entries: dict[str, ProjectionDigestEntry] = {}
    for name in _DIGEST_NAMES:
        value = _mapping(raw, name)
        _exact_fields(value, {"contract", "owner", "sha256"}, name)
        expected_contract, expected_owner = _DIGEST_CONTRACTS[name]
        if (
            value["contract"] != expected_contract
            or value["owner"] != expected_owner
        ):
            raise ExactReplayError(
                "PROJECTION_VERSION_MISMATCH",
                f"{name} digest ownership is incompatible",
            )
        entries[name] = ProjectionDigestEntry(
            contract=expected_contract,
            owner=expected_owner,
            sha256=_require_digest(value["sha256"], f"{name}.sha256"),
        )
    return ProjectionDigestSet(**entries)


def _semantic_health_payload(
    *,
    session_id: str,
    session_date: date,
    health: DataHealth,
    transitions: list[dict[str, object]],
    incidents: list[dict[str, object]],
    semantic_state: DataHealthState,
) -> dict[str, object]:
    snapshot = health.snapshot()
    reasons = {reason.value for reason in snapshot.reasons}
    for incident in incidents:
        if incident["severity"] in {"DEGRADED", "BLOCKED"}:
            reasons.add(str(incident["incident_type"]))
    semantic_times = [snapshot.as_of]
    semantic_times.extend(
        datetime.fromisoformat(str(item["occurred_at"])) for item in incidents
    )
    return {
        "schema": "data-health-replay-v1",
        "session_id": session_id,
        "session_date": session_date.isoformat(),
        "transitions": transitions,
        "incidents": incidents,
        "final_reasons": sorted(reasons),
        "final_state": semantic_state.value,
        "final_admission": _admission(semantic_state),
        "streams": [
            {
                "symbol": item.symbol,
                "stream_kind": item.stream_kind.value,
                "last_event_at": (
                    item.last_event_at.isoformat()
                    if item.last_event_at is not None
                    else None
                ),
                "last_received_at": (
                    item.last_received_at.isoformat()
                    if item.last_received_at is not None
                    else None
                ),
                "applied_count": item.applied_count,
                "duplicate_count": item.duplicate_count,
                "out_of_order_count": item.out_of_order_count,
            }
            for item in snapshot.streams
        ],
        "counters": {
            "queue_overflow_count": snapshot.queue_overflow_count,
            "session_mismatch_count": snapshot.session_mismatch_count,
            "invalid_count": snapshot.invalid_count,
            "gap_count": snapshot.gap_count,
            "source_clock_skew_count": snapshot.source_clock_skew_count,
        },
        "reconnect_epoch": snapshot.reconnect_epoch,
        "resync_verified_at": (
            snapshot.resync_verified_at.isoformat()
            if snapshot.resync_verified_at is not None
            else None
        ),
        "as_of": max(semantic_times).isoformat(),
    }


def _health_transition(
    record_index: int,
    result: IngestResult,
) -> dict[str, object] | None:
    if result.health_before is result.health_after:
        return None
    return {
        "record_index": record_index,
        "evidence_type": "DISPOSITION",
        "event_id": result.event_id,
        "incident_type": None,
        "reason": result.reason,
        "severity": _severity(result.health_after),
        "health_before": result.health_before.value,
        "health_after": result.health_after.value,
        "admission_before": _admission(result.health_before),
        "admission_after": _admission(result.health_after),
    }


def _health_transition_payload(
    record_index: int,
    result: Mapping[str, object],
) -> dict[str, object] | None:
    before = DataHealthState(str(result["health_before"]))
    after = DataHealthState(str(result["health_after"]))
    if before is after:
        return None
    return {
        "record_index": record_index,
        "evidence_type": "DISPOSITION",
        "event_id": str(result["event_id"]),
        "incident_type": None,
        "reason": result.get("reason"),
        "severity": _severity(after),
        "health_before": before.value,
        "health_after": after.value,
        "admission_before": _admission(before),
        "admission_after": _admission(after),
    }


def _semantic_incident(
    record_index: int,
    incident: Mapping[str, object],
    health_before: DataHealthState,
) -> tuple[dict[str, object], DataHealthState]:
    incident_type = str(incident["incident_type"])
    if incident_type in {
        DataHealthReason.QUEUE_OVERFLOW.value,
        DataHealthReason.RECORDER_FAILURE.value,
        DataHealthReason.PROVIDER_DISCONNECTED.value,
        DataHealthReason.REQUIRED_STREAM_STALE.value,
    }:
        health_after = DataHealthState.BLOCKED
    elif incident_type in {
        DataHealthReason.SOURCE_CLOCK_SKEW.value,
        DataHealthReason.OUT_OF_ORDER.value,
    }:
        health_after = (
            health_before
            if health_before is DataHealthState.BLOCKED
            else DataHealthState.DEGRADED
        )
    else:
        health_after = health_before
    return {
        "record_index": record_index,
        "evidence_type": "SYSTEM_INCIDENT",
        "event_id": incident["event_id"],
        "incident_type": incident_type,
        "reason": incident["reason"],
        "severity": (
            "INFO"
            if health_after is health_before
            else _severity(health_after)
        ),
        "health_before": health_before.value,
        "health_after": health_after.value,
        "admission_before": _admission(health_before),
        "admission_after": _admission(health_after),
        "occurred_at": incident["occurred_at"],
        "ingress_sequence": incident["ingress_sequence"],
    }, health_after


def _ingest_result_payload(result: IngestResult) -> dict[str, object]:
    return {
        "status": result.status.value,
        "event_id": result.event_id,
        "symbol": result.symbol,
        "stream_kind": result.stream_kind.value,
        "previous_watermark": _watermark_payload(result.previous_watermark),
        "new_watermark": _watermark_payload(result.new_watermark),
        "projection_applied": result.projection_applied,
        "reason": result.reason,
        "health_before": result.health_before.value,
        "health_after": result.health_after.value,
    }


def _watermark_payload(value) -> dict[str, object] | None:
    if value is None:
        return None
    return {
        "event_time": value.event_time.isoformat(),
        "ingress_sequence": value.ingress_sequence,
    }


def _digest_entry(name: str, payload: object) -> ProjectionDigestEntry:
    contract, owner = _DIGEST_CONTRACTS[name]
    if isinstance(payload, str) and _DIGEST_PATTERN.fullmatch(payload):
        digest = payload
    else:
        digest = hashlib.sha256(_canonical_json(payload)).hexdigest()
    return ProjectionDigestEntry(contract=contract, owner=owner, sha256=digest)


def _load_artifact(path: Path, missing_code: str) -> Mapping[str, object]:
    try:
        content = path.read_bytes()
    except OSError as error:
        raise ExactReplayError(missing_code, str(error)) from error
    if not content.endswith(b"\n"):
        raise ExactReplayError("INCOMPLETE_REPLAY_INPUT", f"{path.name} lacks newline")
    try:
        value = json.loads(content)
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{path.name} is invalid JSON: {error}",
        ) from error
    if not isinstance(value, dict):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{path.name} root must be an object",
        )
    if content != _canonical_json(value) + b"\n":
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{path.name} is not canonical JSON",
        )
    return value


def _validate_journal_boundary_and_coverage(
    *,
    records: tuple[Mapping[str, object], ...],
    bootstrap: Mapping[str, object],
    references: Mapping[str, object],
) -> None:
    ingress_records = [
        record
        for record in records
        if record.get("record_type") == JournalRecordType.INGRESS
    ]
    if not ingress_records:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            "exact replay requires at least one market ingress",
        )
    first = records[0]
    if first.get("record_type") == JournalRecordType.INGRESS:
        first_sequence = _mapping(first, "event")["ingress_sequence"]
    elif first.get("record_type") == JournalRecordType.SYSTEM_INCIDENT:
        first_sequence = _mapping(first, "incident")["ingress_sequence"]
    else:
        raise ExactReplayError(
            "SESSION_IDENTITY_MISMATCH",
            "first Journal row has no ingress sequence",
        )
    boundary = _mapping(bootstrap, "journal_boundary")
    if (
        boundary["first_record_index"] != first["record_index"]
        or boundary["first_ingress_sequence"] != first_sequence
    ):
        raise ExactReplayError(
            "SESSION_IDENTITY_MISMATCH",
            "bootstrap Journal boundary does not match first ingress",
        )
    reference_entries = _object_list(references, "references")
    reference_by_symbol = {
        _non_empty(item, "symbol"): _non_empty(item, "instrument_id")
        for item in reference_entries
    }
    reference_by_id = {
        _non_empty(item, "instrument_id"): _non_empty(item, "symbol")
        for item in reference_entries
    }
    covered_ids = set(
        _string_list(_mapping(bootstrap, "coverage"), "required_instrument_ids")
    )
    for item in _object_list(bootstrap, "symbols"):
        instrument_id = _non_empty(item, "instrument_id")
        if reference_by_id.get(instrument_id) != _non_empty(item, "symbol"):
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "bootstrap symbol identity differs from InstrumentReference",
            )
    for item in _object_list(bootstrap, "subscriptions"):
        if _non_empty(item, "instrument_id") not in covered_ids:
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "subscription identity is outside bootstrap coverage",
            )
    calendar = _mapping(bootstrap, "calendar")
    scheduled_open = _aware(calendar["scheduled_open"], "scheduled_open")
    scheduled_close = _aware(calendar["scheduled_close"], "scheduled_close")
    for record in ingress_records:
        event = _mapping(record, "event")
        symbol = _non_empty(event, "symbol")
        if reference_by_symbol.get(symbol) not in covered_ids:
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                f"Journal symbol {symbol} is outside bootstrap coverage",
            )
        event_at = _aware(event["event_at"], "event_at")
        if not scheduled_open <= event_at <= scheduled_close:
            raise ExactReplayError(
                "INCOMPLETE_REPLAY_INPUT",
                "Journal event is outside the captured session calendar",
            )


def _verify_content_digest(
    raw: Mapping[str, object],
    excluded: set[str],
) -> str:
    expected = _require_digest(raw.get("content_sha256"), "content_sha256")
    payload = {key: value for key, value in raw.items() if key not in excluded}
    actual = hashlib.sha256(_canonical_json(payload)).hexdigest()
    if actual != expected:
        raise ExactReplayError(
            "INPUT_DIGEST_MISMATCH",
            "artifact content_sha256 does not match canonical content",
        )
    return actual


def _require_finalized(raw: Mapping[str, object], schema: str) -> None:
    if raw.get("schema") != schema:
        raise ExactReplayError(
            "PROJECTION_VERSION_MISMATCH",
            f"expected schema {schema}",
        )
    if raw.get("status") != "FINALIZED":
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{schema} status must be FINALIZED",
        )
    _validate_non_empty_fields(raw, ("artifact_id", "session_id", "timezone"))
    _date(raw.get("session_date"), "session_date")


def _initial_projection_digest(
    initialization: Mapping[str, object],
    name: str,
) -> str:
    return _require_digest(
        _mapping(initialization, name).get("expected_initial_digest"),
        f"{name}.expected_initial_digest",
    )


def _mapping(raw: Mapping[str, object], field_name: str) -> Mapping[str, object]:
    value = raw.get(field_name)
    if not isinstance(value, dict):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be an object",
        )
    return value


def _object_list(
    raw: Mapping[str, object],
    field_name: str,
) -> list[Mapping[str, object]]:
    value = raw.get(field_name)
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be a list of objects",
        )
    return value


def _string_list(raw: Mapping[str, object], field_name: str) -> list[str]:
    value = raw.get(field_name)
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be a list of non-empty strings",
        )
    return value


def _exact_fields(
    raw: Mapping[str, object],
    expected: set[str],
    context: str,
) -> None:
    if set(raw) != expected:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{context} fields do not match contract",
        )


def _validate_non_empty_fields(
    raw: Mapping[str, object],
    field_names: tuple[str, ...],
) -> None:
    for field_name in field_names:
        _non_empty(raw, field_name)


def _non_empty(raw: Mapping[str, object], field_name: str) -> str:
    value = raw.get(field_name)
    if not isinstance(value, str) or not value.strip():
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be a non-empty string",
        )
    return value


def _require_digest(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not _DIGEST_PATTERN.fullmatch(value):
        raise ExactReplayError(
            "INPUT_DIGEST_MISMATCH",
            f"{field_name} must be a lowercase SHA-256 digest",
        )
    return value


def _integer(raw: Mapping[str, object], field_name: str) -> int:
    value = raw.get(field_name)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be an integer",
        )
    return value


def _positive_integer(raw: Mapping[str, object], field_name: str) -> int:
    value = _integer(raw, field_name)
    if value <= 0:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be positive",
        )
    return value


def _non_negative_integer(raw: Mapping[str, object], field_name: str) -> int:
    value = _integer(raw, field_name)
    if value < 0:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be non-negative",
        )
    return value


def _boolean(raw: Mapping[str, object], field_name: str) -> bool:
    value = raw.get(field_name)
    if not isinstance(value, bool):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be boolean",
        )
    return value


def _date(value: object, field_name: str) -> date:
    if not isinstance(value, str):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be an ISO date",
        )
    try:
        return date.fromisoformat(value)
    except ValueError as error:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be an ISO date",
        ) from error


def _aware(value: object, field_name: str) -> datetime:
    if not isinstance(value, str):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be an aware ISO timestamp",
        )
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as error:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be an aware ISO timestamp",
        ) from error
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be timezone-aware",
        )
    return parsed


def _decimal(value: object, field_name: str) -> Decimal:
    if not isinstance(value, str):
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be a decimal string",
        )
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be a decimal string",
        ) from error
    if not parsed.is_finite() or parsed <= 0:
        raise ExactReplayError(
            "INCOMPLETE_REPLAY_INPUT",
            f"{field_name} must be a positive finite decimal",
        )
    return parsed


def _optional_decimal(value: object, field_name: str) -> Decimal | None:
    return None if value is None else _decimal(value, field_name)


def _severity(state: DataHealthState) -> str:
    return "BLOCKED" if state is DataHealthState.BLOCKED else "DEGRADED"


def _admission(state: DataHealthState) -> str:
    return "OPEN" if state is DataHealthState.HEALTHY else "BLOCK_NEW_ENTRY"


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
