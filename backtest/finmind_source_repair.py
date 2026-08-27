"""Append-only, provenance-preserving overlays for FinMind source gaps.

The acquisition partition remains immutable.  A repair case may quarantine that
partition immediately, but only reviewed minute-level evidence can become an
active overlay for a later immutable Dataset snapshot.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime, time
from pathlib import Path
from typing import Any, Mapping, Sequence

from backtest.domain import HistoricalBar, canonical_json
from backtest.finmind_history import TAIPEI, VOLUME_UNIT


REPAIR_SCHEMA_VERSION = "finmind-source-repair-v1"
MINUTE_TIMESTAMP_SEMANTIC = "OBSERVABLE_MINUTE_END"
DAILY_GRAIN = "DAILY"
MINUTE_GRAIN = "MINUTE"
QUARANTINED = "QUARANTINED"
PENDING_REVIEW = "PENDING_REVIEW"
APPROVED = "APPROVED"
ACTIVE = "ACTIVE"
_ALLOWED_REASONS = {
    "OFFICIAL_PRICE_FINMIND_EMPTY",
    "OFFICIAL_VOLUME_MISMATCH",
    "PROVIDER_CORRUPTION",
    "OTHER_REVIEWED_SOURCE_GAP",
}


class FinMindSourceRepairError(ValueError):
    """The requested source-repair transition is unsafe or inconsistent."""


@dataclass(frozen=True)
class RepairResolution:
    case_id: str
    state: str
    evidence_id: str | None = None
    review_id: str | None = None
    activation_id: str | None = None
    evidence_kind: str | None = None
    source_name: str | None = None
    source_uri: str | None = None
    observed_at: str | None = None
    raw_sha256: str | None = None
    canonical_sha256: str | None = None
    volume_unit: str | None = None
    timestamp_semantic: str | None = None
    first_event_at: str | None = None
    last_event_at: str | None = None
    bars: tuple[HistoricalBar, ...] = ()

    @property
    def is_active(self) -> bool:
        return self.state == ACTIVE

    def lineage(self, job_id: str) -> Mapping[str, str]:
        required = (
            self.evidence_id,
            self.review_id,
            self.activation_id,
            self.evidence_kind,
            self.source_name,
            self.source_uri,
            self.observed_at,
            self.raw_sha256,
            self.canonical_sha256,
            self.volume_unit,
            self.timestamp_semantic,
        )
        if not self.is_active or not all(required):
            raise FinMindSourceRepairError("repair overlay is not active")
        return {
            "activation_id": str(self.activation_id),
            "canonical_sha256": str(self.canonical_sha256),
            "case_id": self.case_id,
            "evidence_kind": str(self.evidence_kind),
            "evidence_id": str(self.evidence_id),
            "job_id": job_id,
            "observed_at": str(self.observed_at),
            "raw_sha256": str(self.raw_sha256),
            "review_id": str(self.review_id),
            "schema_version": REPAIR_SCHEMA_VERSION,
            "source_name": str(self.source_name),
            "source_uri": str(self.source_uri),
            "timestamp_semantic": str(self.timestamp_semantic),
            "volume_unit": str(self.volume_unit),
        }


class FinMindSourceRepairStore:
    """Manage reviewed overlays without changing acquisition evidence."""

    def __init__(self, path: Path) -> None:
        if not path.is_file():
            raise FileNotFoundError(path)
        self._connection = sqlite3.connect(path)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys=ON")
        self._connection.execute("PRAGMA journal_mode=WAL")
        self._connection.execute("PRAGMA synchronous=FULL")
        self._connection.executescript(_SCHEMA)

    def close(self) -> None:
        self._connection.close()

    def open_case(
        self,
        *,
        job_id: str,
        symbol: str,
        session_date: date,
        reason_code: str,
        evidence_kind: str,
        source_name: str,
        source_uri: str,
        observed_at: datetime,
        evidence_body: bytes,
    ) -> Mapping[str, Any]:
        reason = _required(reason_code, "reason_code")
        if reason not in _ALLOWED_REASONS:
            raise FinMindSourceRepairError("unsupported source-repair reason_code")
        target = _load_target(self._connection, job_id, symbol, session_date)
        if target["status"] not in {"EMPTY", "INVALID"}:
            raise FinMindSourceRepairError(
                "source-repair cases may only target EMPTY or INVALID partitions"
            )
        observed = _aware_timestamp(observed_at, "observed_at")
        source = _required(source_name, "source_name")
        uri = _required(source_uri, "source_uri")
        kind = _required(evidence_kind, "evidence_kind")
        if not evidence_body:
            raise FinMindSourceRepairError("evidence_body cannot be empty")
        case_projection = {
            "job_id": job_id,
            "original_canonical_sha256": str(target["canonical_sha256"]),
            "original_raw_sha256": str(target["raw_sha256"]),
            "original_status": str(target["status"]),
            "reason_code": reason,
            "schema_version": REPAIR_SCHEMA_VERSION,
            "session_date": session_date.isoformat(),
            "symbol": symbol,
        }
        case_id = f"finmind-repair-{_digest(case_projection)[:20]}"
        evidence_id, raw_sha256 = _evidence_identity(
            case_id=case_id,
            evidence_kind=kind,
            grain=DAILY_GRAIN,
            source_name=source,
            source_uri=uri,
            observed_at=observed,
            evidence_body=evidence_body,
            canonical_bars_sha256=None,
        )
        now = datetime.now(TAIPEI).isoformat()
        with self._connection:
            existing = self._connection.execute(
                """
                SELECT * FROM finmind_source_repair_cases
                WHERE job_id = ? AND symbol = ? AND session_date = ?
                """,
                (job_id, symbol, session_date.isoformat()),
            ).fetchone()
            if existing is not None and str(existing["case_id"]) != case_id:
                raise FinMindSourceRepairError(
                    "existing repair case conflicts with current target evidence"
                )
            if (
                existing is not None
                and str(existing["discrepancy_evidence_id"]) != evidence_id
            ):
                raise FinMindSourceRepairError(
                    "existing repair case has different discrepancy evidence"
                )
            self._connection.execute(
                """
                INSERT OR IGNORE INTO finmind_source_repair_cases (
                    case_id, job_id, symbol, session_date, original_status,
                    original_raw_sha256, original_canonical_sha256, reason_code,
                    state, discrepancy_evidence_id, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    case_id,
                    job_id,
                    symbol,
                    session_date.isoformat(),
                    target["status"],
                    target["raw_sha256"],
                    target["canonical_sha256"],
                    reason,
                    QUARANTINED,
                    evidence_id,
                    now,
                    now,
                ),
            )
            self._insert_evidence(
                evidence_id=evidence_id,
                case_id=case_id,
                evidence_kind=kind,
                grain=DAILY_GRAIN,
                source_name=source,
                source_uri=uri,
                observed_at=observed,
                raw_sha256=raw_sha256,
                evidence_body=evidence_body,
                canonical_bars_sha256=None,
                canonical_bars_payload=None,
                bars=(),
                created_at=now,
            )
        return self.case_status(case_id)

    def propose_minute_evidence(
        self,
        *,
        case_id: str,
        source_name: str,
        source_uri: str,
        observed_at: datetime,
        evidence_body: bytes,
        bars: Sequence[HistoricalBar],
        evidence_kind: str = "ALTERNATE_MINUTE_BARS",
        volume_unit: str = VOLUME_UNIT,
        timestamp_semantic: str = MINUTE_TIMESTAMP_SEMANTIC,
    ) -> Mapping[str, Any]:
        case = self._get_case(case_id)
        if case["state"] == ACTIVE:
            raise FinMindSourceRepairError("active repair case is immutable")
        if volume_unit != VOLUME_UNIT:
            raise FinMindSourceRepairError(
                f"minute repair volume_unit must be {VOLUME_UNIT}"
            )
        if timestamp_semantic != MINUTE_TIMESTAMP_SEMANTIC:
            raise FinMindSourceRepairError(
                f"timestamp_semantic must be {MINUTE_TIMESTAMP_SEMANTIC}"
            )
        normalized = _validate_minute_bars(
            bars,
            symbol=str(case["symbol"]),
            session_date=date.fromisoformat(str(case["session_date"])),
        )
        canonical_payload = canonical_json(
            [bar.to_dict() for bar in normalized]
        ).encode("utf-8")
        canonical_sha256 = hashlib.sha256(canonical_payload).hexdigest()
        observed = _aware_timestamp(observed_at, "observed_at")
        source = _required(source_name, "source_name")
        uri = _required(source_uri, "source_uri")
        kind = _required(evidence_kind, "evidence_kind")
        if not evidence_body:
            raise FinMindSourceRepairError("evidence_body cannot be empty")
        evidence_id, raw_sha256 = _evidence_identity(
            case_id=case_id,
            evidence_kind=kind,
            grain=MINUTE_GRAIN,
            source_name=source,
            source_uri=uri,
            observed_at=observed,
            evidence_body=evidence_body,
            canonical_bars_sha256=canonical_sha256,
        )
        if (
            case["state"] in {PENDING_REVIEW, APPROVED}
            and str(case["candidate_evidence_id"] or "") == evidence_id
        ):
            return self.case_status(case_id)
        if case["state"] == APPROVED:
            raise FinMindSourceRepairError(
                "approved repair case cannot accept replacement evidence"
            )
        now = datetime.now(TAIPEI).isoformat()
        with self._connection:
            self._insert_evidence(
                evidence_id=evidence_id,
                case_id=case_id,
                evidence_kind=kind,
                grain=MINUTE_GRAIN,
                source_name=source,
                source_uri=uri,
                observed_at=observed,
                raw_sha256=raw_sha256,
                evidence_body=evidence_body,
                canonical_bars_sha256=canonical_sha256,
                canonical_bars_payload=canonical_payload,
                bars=normalized,
                created_at=now,
            )
            self._connection.execute(
                """
                UPDATE finmind_source_repair_cases
                SET state = ?, candidate_evidence_id = ?, current_review_id = NULL,
                    current_activation_id = NULL, updated_at = ?
                WHERE case_id = ? AND state != ?
                """,
                (PENDING_REVIEW, evidence_id, now, case_id, ACTIVE),
            )
        return self.case_status(case_id)

    def review(
        self,
        *,
        case_id: str,
        evidence_id: str,
        decision: str,
        reviewer: str,
        rationale: str,
    ) -> Mapping[str, Any]:
        case = self._get_case(case_id)
        evidence = self._get_evidence(evidence_id)
        if evidence["grain"] != MINUTE_GRAIN or int(evidence["bar_count"]) <= 0:
            raise FinMindSourceRepairError("daily-only evidence cannot be approved")
        normalized_decision = _required(decision, "decision").upper()
        if normalized_decision not in {"APPROVE", "REJECT"}:
            raise FinMindSourceRepairError("decision must be APPROVE or REJECT")
        normalized_reviewer = _required(reviewer, "reviewer")
        normalized_rationale = _required(rationale, "rationale")
        review_projection = {
            "case_id": case_id,
            "decision": normalized_decision,
            "evidence_id": evidence_id,
            "evidence_raw_sha256": str(evidence["raw_sha256"]),
            "evidence_canonical_sha256": str(evidence["canonical_bars_sha256"]),
            "rationale": normalized_rationale,
            "reviewer": normalized_reviewer,
            "schema_version": REPAIR_SCHEMA_VERSION,
        }
        review_id = f"finmind-repair-review-{_digest(review_projection)[:20]}"
        if (
            case["state"] in {APPROVED, QUARANTINED}
            and str(case["current_review_id"] or "") == review_id
        ):
            return self.case_status(case_id)
        if case["state"] != PENDING_REVIEW:
            raise FinMindSourceRepairError("repair case is not pending review")
        if str(case["candidate_evidence_id"] or "") != evidence_id:
            raise FinMindSourceRepairError("review evidence does not match candidate")
        now = datetime.now(TAIPEI).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO finmind_source_repair_reviews (
                    review_id, case_id, evidence_id, decision, reviewer,
                    rationale, evidence_raw_sha256, evidence_canonical_sha256,
                    reviewed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    review_id,
                    case_id,
                    evidence_id,
                    normalized_decision,
                    normalized_reviewer,
                    normalized_rationale,
                    evidence["raw_sha256"],
                    evidence["canonical_bars_sha256"],
                    now,
                ),
            )
            self._connection.execute(
                """
                UPDATE finmind_source_repair_cases
                SET state = ?, current_review_id = ?, updated_at = ?
                WHERE case_id = ? AND state = ?
                """,
                (
                    APPROVED if normalized_decision == "APPROVE" else QUARANTINED,
                    review_id,
                    now,
                    case_id,
                    PENDING_REVIEW,
                ),
            )
        return self.case_status(case_id)

    def activate(
        self,
        *,
        case_id: str,
        review_id: str,
        actor: str,
        change_note: str,
    ) -> Mapping[str, Any]:
        case = self._get_case(case_id)
        review = self._connection.execute(
            "SELECT * FROM finmind_source_repair_reviews WHERE review_id = ?",
            (review_id,),
        ).fetchone()
        if review is None or review["decision"] != "APPROVE":
            raise FinMindSourceRepairError("activation requires an approval review")
        evidence = self._get_evidence(str(review["evidence_id"]))
        _verified_evidence_bars(
            evidence,
            str(case["symbol"]),
            date.fromisoformat(str(case["session_date"])),
        )
        normalized_actor = _required(actor, "actor")
        normalized_note = _required(change_note, "change_note")
        activation_projection = {
            "actor": normalized_actor,
            "case_id": case_id,
            "change_note": normalized_note,
            "evidence_id": str(evidence["evidence_id"]),
            "review_id": review_id,
            "schema_version": REPAIR_SCHEMA_VERSION,
        }
        activation_id = f"finmind-repair-activation-{_digest(activation_projection)[:20]}"
        if (
            case["state"] == ACTIVE
            and str(case["current_activation_id"] or "") == activation_id
        ):
            return self.case_status(case_id)
        if case["state"] != APPROVED:
            raise FinMindSourceRepairError("repair case is not approved")
        if str(case["current_review_id"] or "") != review_id:
            raise FinMindSourceRepairError("activation review does not match case")
        now = datetime.now(TAIPEI).isoformat()
        with self._connection:
            self._connection.execute(
                """
                INSERT OR IGNORE INTO finmind_source_repair_activations (
                    activation_id, case_id, evidence_id, review_id, actor,
                    change_note, activated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    activation_id,
                    case_id,
                    evidence["evidence_id"],
                    review_id,
                    normalized_actor,
                    normalized_note,
                    now,
                ),
            )
            self._connection.execute(
                """
                UPDATE finmind_source_repair_cases
                SET state = ?, current_activation_id = ?, updated_at = ?
                WHERE case_id = ? AND state = ?
                """,
                (ACTIVE, activation_id, now, case_id, APPROVED),
            )
        return self.case_status(case_id)

    def case_status(self, case_id: str) -> Mapping[str, Any]:
        case = self._get_case(case_id)
        evidence = self._connection.execute(
            """
            SELECT evidence_id, evidence_kind, grain, source_name, source_uri,
                   observed_at, raw_sha256, canonical_bars_sha256, bar_count,
                   first_event_at, last_event_at, created_at
            FROM finmind_source_repair_evidence
            WHERE case_id = ? ORDER BY created_at, evidence_id
            """,
            (case_id,),
        ).fetchall()
        return {
            "case_id": case_id,
            "job_id": case["job_id"],
            "symbol": case["symbol"],
            "session_date": case["session_date"],
            "state": case["state"],
            "reason_code": case["reason_code"],
            "original_status": case["original_status"],
            "original_raw_sha256": case["original_raw_sha256"],
            "original_canonical_sha256": case["original_canonical_sha256"],
            "discrepancy_evidence_id": case["discrepancy_evidence_id"],
            "candidate_evidence_id": case["candidate_evidence_id"],
            "current_review_id": case["current_review_id"],
            "current_activation_id": case["current_activation_id"],
            "evidence": [dict(row) for row in evidence],
        }

    def audit(self) -> Mapping[str, Any]:
        rows = self._connection.execute(
            "SELECT * FROM finmind_source_repair_cases ORDER BY job_id, symbol, session_date"
        ).fetchall()
        issues: list[str] = []
        states: dict[str, int] = {}
        active_bar_count = 0
        for case in rows:
            case_id = str(case["case_id"])
            states[str(case["state"])] = states.get(str(case["state"]), 0) + 1
            try:
                target = _load_target(
                    self._connection,
                    str(case["job_id"]),
                    str(case["symbol"]),
                    date.fromisoformat(str(case["session_date"])),
                )
                if (
                    target["status"] != case["original_status"]
                    or target["raw_sha256"] != case["original_raw_sha256"]
                    or target["canonical_sha256"] != case["original_canonical_sha256"]
                ):
                    raise FinMindSourceRepairError("original partition drift")
                evidence_rows = self._connection.execute(
                    "SELECT * FROM finmind_source_repair_evidence WHERE case_id = ?",
                    (case_id,),
                ).fetchall()
                for evidence in evidence_rows:
                    _verify_evidence_digests(evidence)
                _verify_case_state(self._connection, case, evidence_rows)
                resolution = load_repair_resolution(
                    self._connection,
                    job_id=str(case["job_id"]),
                    symbol=str(case["symbol"]),
                    session_date=date.fromisoformat(str(case["session_date"])),
                )
                if resolution is not None and resolution.is_active:
                    active_bar_count += len(resolution.bars)
            except (KeyError, OSError, ValueError, json.JSONDecodeError) as error:
                issues.append(f"{case_id}: {error}")
        return {
            "schema_version": REPAIR_SCHEMA_VERSION,
            "case_count": len(rows),
            "state_counts": states,
            "active_bar_count": active_bar_count,
            "verified_cases": len(rows) - len(issues),
            "issue_count": len(issues),
            "issues": issues[:20],
        }

    def _get_case(self, case_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM finmind_source_repair_cases WHERE case_id = ?",
            (case_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown FinMind source-repair case: {case_id}")
        return row

    def _get_evidence(self, evidence_id: str) -> sqlite3.Row:
        row = self._connection.execute(
            "SELECT * FROM finmind_source_repair_evidence WHERE evidence_id = ?",
            (evidence_id,),
        ).fetchone()
        if row is None:
            raise KeyError(f"unknown FinMind source-repair evidence: {evidence_id}")
        return row

    def _insert_evidence(
        self,
        *,
        evidence_id: str,
        case_id: str,
        evidence_kind: str,
        grain: str,
        source_name: str,
        source_uri: str,
        observed_at: str,
        raw_sha256: str,
        evidence_body: bytes,
        canonical_bars_sha256: str | None,
        canonical_bars_payload: bytes | None,
        bars: Sequence[HistoricalBar],
        created_at: str,
    ) -> None:
        self._connection.execute(
            """
            INSERT OR IGNORE INTO finmind_source_repair_evidence (
                evidence_id, case_id, evidence_kind, grain, source_name,
                source_uri, observed_at, raw_sha256, raw_payload,
                canonical_bars_sha256, canonical_bars_payload, bar_count,
                first_event_at, last_event_at, volume_unit,
                timestamp_semantic, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                evidence_id,
                case_id,
                evidence_kind,
                grain,
                source_name,
                source_uri,
                observed_at,
                raw_sha256,
                gzip.compress(evidence_body, mtime=0),
                canonical_bars_sha256,
                (
                    gzip.compress(canonical_bars_payload, mtime=0)
                    if canonical_bars_payload is not None
                    else None
                ),
                len(bars),
                bars[0].timestamp.isoformat() if bars else None,
                bars[-1].timestamp.isoformat() if bars else None,
                VOLUME_UNIT if bars else None,
                MINUTE_TIMESTAMP_SEMANTIC if bars else None,
                created_at,
            ),
        )


def load_repair_resolution(
    connection: sqlite3.Connection,
    *,
    job_id: str,
    symbol: str,
    session_date: date,
) -> RepairResolution | None:
    """Return the verified case state and active overlay, if the schema exists."""

    if not _table_exists(connection, "finmind_source_repair_cases"):
        return None
    case = connection.execute(
        """
        SELECT * FROM finmind_source_repair_cases
        WHERE job_id = ? AND symbol = ? AND session_date = ?
        """,
        (job_id, symbol, session_date.isoformat()),
    ).fetchone()
    if case is None:
        return None
    target = _load_target(connection, job_id, symbol, session_date)
    if (
        target["status"] != case["original_status"]
        or target["raw_sha256"] != case["original_raw_sha256"]
        or target["canonical_sha256"] != case["original_canonical_sha256"]
    ):
        raise FinMindSourceRepairError("repair target original partition drift")
    state = str(case["state"])
    if state not in {QUARANTINED, PENDING_REVIEW, APPROVED, ACTIVE}:
        raise FinMindSourceRepairError("repair case state is invalid")
    if state != ACTIVE:
        return RepairResolution(case_id=str(case["case_id"]), state=state)
    activation = connection.execute(
        """
        SELECT * FROM finmind_source_repair_activations
        WHERE activation_id = ? AND case_id = ?
        """,
        (case["current_activation_id"], case["case_id"]),
    ).fetchone()
    if activation is None:
        raise FinMindSourceRepairError("active repair is missing activation evidence")
    review = connection.execute(
        "SELECT * FROM finmind_source_repair_reviews WHERE review_id = ?",
        (activation["review_id"],),
    ).fetchone()
    evidence = connection.execute(
        "SELECT * FROM finmind_source_repair_evidence WHERE evidence_id = ?",
        (activation["evidence_id"],),
    ).fetchone()
    if (
        review is None
        or evidence is None
        or review["decision"] != "APPROVE"
        or review["case_id"] != case["case_id"]
        or review["evidence_id"] != evidence["evidence_id"]
        or review["evidence_raw_sha256"] != evidence["raw_sha256"]
        or review["evidence_canonical_sha256"] != evidence["canonical_bars_sha256"]
    ):
        raise FinMindSourceRepairError("active repair approval chain is invalid")
    bars = _verified_evidence_bars(evidence, symbol, session_date)
    return RepairResolution(
        case_id=str(case["case_id"]),
        state=state,
        evidence_id=str(evidence["evidence_id"]),
        review_id=str(review["review_id"]),
        activation_id=str(activation["activation_id"]),
        evidence_kind=str(evidence["evidence_kind"]),
        source_name=str(evidence["source_name"]),
        source_uri=str(evidence["source_uri"]),
        observed_at=str(evidence["observed_at"]),
        raw_sha256=str(evidence["raw_sha256"]),
        canonical_sha256=str(evidence["canonical_bars_sha256"]),
        volume_unit=str(evidence["volume_unit"]),
        timestamp_semantic=str(evidence["timestamp_semantic"]),
        first_event_at=str(evidence["first_event_at"]),
        last_event_at=str(evidence["last_event_at"]),
        bars=bars,
    )


def _load_target(
    connection: sqlite3.Connection,
    job_id: str,
    symbol: str,
    session_date: date,
) -> sqlite3.Row:
    row = connection.execute(
        """
        SELECT status, raw_sha256, canonical_sha256
        FROM finmind_history_partitions
        WHERE job_id = ? AND symbol = ? AND session_date = ?
        """,
        (job_id, symbol, session_date.isoformat()),
    ).fetchone()
    if row is None:
        raise KeyError(
            f"FinMind history partition not found: {job_id}/{symbol}/{session_date.isoformat()}"
        )
    return row


def _verified_evidence_bars(
    evidence: sqlite3.Row,
    symbol: str,
    session_date: date,
) -> tuple[HistoricalBar, ...]:
    _verify_evidence_digests(evidence)
    if evidence["grain"] != MINUTE_GRAIN:
        raise FinMindSourceRepairError("active repair evidence is not minute-level")
    payload = gzip.decompress(bytes(evidence["canonical_bars_payload"]))
    values = json.loads(payload)
    if not isinstance(values, list):
        raise FinMindSourceRepairError("canonical repair payload is not a list")
    bars = tuple(HistoricalBar.from_dict(value) for value in values)
    normalized = _validate_minute_bars(bars, symbol=symbol, session_date=session_date)
    if len(normalized) != int(evidence["bar_count"]):
        raise FinMindSourceRepairError("repair evidence bar_count mismatch")
    return normalized


def _verify_case_state(
    connection: sqlite3.Connection,
    case: sqlite3.Row,
    evidence_rows: Sequence[sqlite3.Row],
) -> None:
    evidence_by_id = {str(row["evidence_id"]): row for row in evidence_rows}
    discrepancy = evidence_by_id.get(str(case["discrepancy_evidence_id"]))
    if discrepancy is None or discrepancy["grain"] != DAILY_GRAIN:
        raise FinMindSourceRepairError(
            "repair case is missing daily discrepancy evidence"
        )
    state = str(case["state"])
    if state not in {QUARANTINED, PENDING_REVIEW, APPROVED, ACTIVE}:
        raise FinMindSourceRepairError("repair case state is invalid")
    if state == QUARANTINED:
        return
    candidate_id = str(case["candidate_evidence_id"] or "")
    candidate = evidence_by_id.get(candidate_id)
    if (
        candidate is None
        or candidate["grain"] != MINUTE_GRAIN
        or int(candidate["bar_count"]) <= 0
    ):
        raise FinMindSourceRepairError(
            "repair case is missing minute candidate evidence"
        )
    if state == PENDING_REVIEW:
        return
    review = connection.execute(
        "SELECT * FROM finmind_source_repair_reviews WHERE review_id = ?",
        (case["current_review_id"],),
    ).fetchone()
    if (
        review is None
        or review["case_id"] != case["case_id"]
        or review["evidence_id"] != candidate_id
        or review["decision"] != "APPROVE"
        or review["evidence_raw_sha256"] != candidate["raw_sha256"]
        or review["evidence_canonical_sha256"]
        != candidate["canonical_bars_sha256"]
    ):
        raise FinMindSourceRepairError("repair approval chain is invalid")
    if state == APPROVED:
        return
    activation = connection.execute(
        """
        SELECT * FROM finmind_source_repair_activations
        WHERE activation_id = ? AND case_id = ?
        """,
        (case["current_activation_id"], case["case_id"]),
    ).fetchone()
    if (
        activation is None
        or activation["evidence_id"] != candidate_id
        or activation["review_id"] != review["review_id"]
    ):
        raise FinMindSourceRepairError("repair activation chain is invalid")


def _verify_evidence_digests(evidence: sqlite3.Row) -> None:
    raw = gzip.decompress(bytes(evidence["raw_payload"]))
    if hashlib.sha256(raw).hexdigest() != evidence["raw_sha256"]:
        raise FinMindSourceRepairError("repair raw evidence digest mismatch")
    canonical_blob = evidence["canonical_bars_payload"]
    canonical_sha256 = evidence["canonical_bars_sha256"]
    if canonical_blob is None:
        if canonical_sha256 is not None or int(evidence["bar_count"]) != 0:
            raise FinMindSourceRepairError("daily repair evidence carries minute metadata")
        return
    canonical = gzip.decompress(bytes(canonical_blob))
    if hashlib.sha256(canonical).hexdigest() != canonical_sha256:
        raise FinMindSourceRepairError("repair canonical evidence digest mismatch")


def _validate_minute_bars(
    bars: Sequence[HistoricalBar],
    *,
    symbol: str,
    session_date: date,
) -> tuple[HistoricalBar, ...]:
    normalized = tuple(bars)
    if not normalized:
        raise FinMindSourceRepairError("minute repair evidence cannot be empty")
    timestamps = [bar.timestamp for bar in normalized]
    if timestamps != sorted(timestamps) or len(set(timestamps)) != len(timestamps):
        raise FinMindSourceRepairError(
            "minute repair timestamps must be unique and strictly increasing"
        )
    for bar in normalized:
        local = bar.timestamp.astimezone(TAIPEI)
        local_time = local.timetz().replace(tzinfo=None)
        if bar.symbol != symbol or bar.session_date != session_date:
            raise FinMindSourceRepairError("minute repair target does not match case")
        if bar.name or bar.market or bar.session_open_at is not None:
            raise FinMindSourceRepairError(
                "minute repair bars must not embed reference or daily-session metadata"
            )
        if bar.amount != bar.close * bar.volume:
            raise FinMindSourceRepairError(
                "minute repair amount must follow close times volume proxy contract"
            )
        if local.date() != session_date:
            raise FinMindSourceRepairError("minute repair timestamp is outside session date")
        if local.second or local.microsecond:
            raise FinMindSourceRepairError("minute repair timestamp is not minute-aligned")
        if not (
            time(9, 1) <= local_time <= time(13, 30)
            or local_time == time(13, 33)
        ):
            raise FinMindSourceRepairError(
                "minute repair timestamp is outside observable regular-session bounds"
            )
    return normalized


def _evidence_identity(
    *,
    case_id: str,
    evidence_kind: str,
    grain: str,
    source_name: str,
    source_uri: str,
    observed_at: str,
    evidence_body: bytes,
    canonical_bars_sha256: str | None,
) -> tuple[str, str]:
    raw_sha256 = hashlib.sha256(evidence_body).hexdigest()
    projection = {
        "canonical_bars_sha256": canonical_bars_sha256,
        "case_id": case_id,
        "evidence_kind": evidence_kind,
        "grain": grain,
        "observed_at": observed_at,
        "raw_sha256": raw_sha256,
        "schema_version": REPAIR_SCHEMA_VERSION,
        "source_name": source_name,
        "source_uri": source_uri,
    }
    return f"finmind-repair-evidence-{_digest(projection)[:20]}", raw_sha256


def _digest(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(canonical_json(dict(value)).encode("utf-8")).hexdigest()


def _required(value: str, field: str) -> str:
    normalized = str(value).strip()
    if not normalized:
        raise FinMindSourceRepairError(f"{field} cannot be blank")
    return normalized


def _aware_timestamp(value: datetime, field: str) -> str:
    if value.tzinfo is None or value.utcoffset() is None:
        raise FinMindSourceRepairError(f"{field} must be timezone-aware")
    return value.isoformat()


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    return (
        connection.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
            (table,),
        ).fetchone()
        is not None
    )


_SCHEMA = """
CREATE TABLE IF NOT EXISTS finmind_source_repair_cases (
    case_id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES finmind_history_jobs(job_id),
    symbol TEXT NOT NULL,
    session_date TEXT NOT NULL,
    original_status TEXT NOT NULL,
    original_raw_sha256 TEXT NOT NULL,
    original_canonical_sha256 TEXT NOT NULL,
    reason_code TEXT NOT NULL,
    state TEXT NOT NULL,
    discrepancy_evidence_id TEXT NOT NULL,
    candidate_evidence_id TEXT NULL,
    current_review_id TEXT NULL,
    current_activation_id TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    UNIQUE (job_id, symbol, session_date)
);
CREATE TABLE IF NOT EXISTS finmind_source_repair_evidence (
    evidence_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES finmind_source_repair_cases(case_id),
    evidence_kind TEXT NOT NULL,
    grain TEXT NOT NULL,
    source_name TEXT NOT NULL,
    source_uri TEXT NOT NULL,
    observed_at TEXT NOT NULL,
    raw_sha256 TEXT NOT NULL,
    raw_payload BLOB NOT NULL,
    canonical_bars_sha256 TEXT NULL,
    canonical_bars_payload BLOB NULL,
    bar_count INTEGER NOT NULL,
    first_event_at TEXT NULL,
    last_event_at TEXT NULL,
    volume_unit TEXT NULL,
    timestamp_semantic TEXT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS finmind_source_repair_reviews (
    review_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL REFERENCES finmind_source_repair_cases(case_id),
    evidence_id TEXT NOT NULL REFERENCES finmind_source_repair_evidence(evidence_id),
    decision TEXT NOT NULL,
    reviewer TEXT NOT NULL,
    rationale TEXT NOT NULL,
    evidence_raw_sha256 TEXT NOT NULL,
    evidence_canonical_sha256 TEXT NOT NULL,
    reviewed_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS finmind_source_repair_activations (
    activation_id TEXT PRIMARY KEY,
    case_id TEXT NOT NULL UNIQUE REFERENCES finmind_source_repair_cases(case_id),
    evidence_id TEXT NOT NULL REFERENCES finmind_source_repair_evidence(evidence_id),
    review_id TEXT NOT NULL REFERENCES finmind_source_repair_reviews(review_id),
    actor TEXT NOT NULL,
    change_note TEXT NOT NULL,
    activated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS finmind_source_repair_cases_target
ON finmind_source_repair_cases (job_id, symbol, session_date);
CREATE INDEX IF NOT EXISTS finmind_source_repair_evidence_case
ON finmind_source_repair_evidence (case_id, created_at);
"""
