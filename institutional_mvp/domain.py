"""Provider-neutral domain contracts for the daily institutional MVP batch."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from enum import Enum
from typing import Any, Mapping

from institutional_data.serialization import canonical_json, sha256_text


BATCH_SCHEMA_VERSION = "institutional_mvp_candidate_batch_v1"
BATCH_STATUS = "MVP_CANDIDATE_OBSERVATION_ONLY"
CHANGE_POLICY = "IMMUTABLE_APPEND_ONLY_REVISIONS"


class DailyRunStatus(str, Enum):
    PUBLISHED = "PUBLISHED"
    IDEMPOTENT_REPLAY = "IDEMPOTENT_REPLAY"
    CONFLICT_REVISION_CREATED = "CONFLICT_REVISION_CREATED"


class InstitutionalMvpDailyError(RuntimeError):
    """A coded fail-closed daily MVP error safe to expose in CLI output."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = _text(code, "code")


class InstitutionalMvpSourceNotReady(InstitutionalMvpDailyError):
    def __init__(self) -> None:
        super().__init__(
            "SOURCE_NOT_READY",
            "FinMind has not published institutional rows for the source session",
        )


@dataclass(frozen=True)
class InstitutionalMvpDailyPolicy:
    artifact_id: str
    base_policy_artifact_id: str
    base_policy_digest: str
    candidate_limit: int
    candidate_rule: str
    dealer_total_net_formula: str
    market_mapping: str
    rank_rule: str
    session_binding: str
    execution_permissions: tuple[tuple[str, bool], ...]
    limitations: tuple[str, ...]

    def __post_init__(self) -> None:
        for value, name in (
            (self.artifact_id, "artifact_id"),
            (self.base_policy_artifact_id, "base_policy_artifact_id"),
            (self.candidate_rule, "candidate_rule"),
            (self.dealer_total_net_formula, "dealer_total_net_formula"),
            (self.market_mapping, "market_mapping"),
            (self.rank_rule, "rank_rule"),
            (self.session_binding, "session_binding"),
        ):
            _text(value, name)
        _sha256(self.base_policy_digest, "base_policy_digest")
        if isinstance(self.candidate_limit, bool) or self.candidate_limit <= 0:
            raise ValueError("candidate_limit must be positive")
        permission_map = dict(self.execution_permissions)
        if len(permission_map) != len(self.execution_permissions):
            raise ValueError("execution permission names must be unique")
        if permission_map.get("mvp_candidate_observation_allowed") is not True:
            raise ValueError("MVP candidate observation permission must be enabled")
        if any(
            value is not False
            for name, value in permission_map.items()
            if name != "mvp_candidate_observation_allowed"
        ):
            raise ValueError("daily MVP policy grants authority beyond observation")
        if not self.limitations or any(not item.strip() for item in self.limitations):
            raise ValueError("limitations must contain non-empty values")

    def body(self) -> dict[str, object]:
        return {
            "artifact_id": self.artifact_id,
            "base_policy_reference": {
                "artifact_id": self.base_policy_artifact_id,
                "canonical_sha256": self.base_policy_digest,
            },
            "candidate_limit": self.candidate_limit,
            "candidate_rule": self.candidate_rule,
            "dealer_total_net_formula": self.dealer_total_net_formula,
            "execution_permissions": dict(self.execution_permissions),
            "limitations": list(self.limitations),
            "market_mapping": self.market_mapping,
            "rank_rule": self.rank_rule,
            "schema_version": "institutional_mvp_daily_candidate_policy_v1",
            "session_binding": self.session_binding,
        }

    @property
    def canonical_sha256(self) -> str:
        return sha256_text(canonical_json(self.body()))

    def to_dict(self) -> dict[str, object]:
        return {**self.body(), "canonical_sha256": self.canonical_sha256}


@dataclass(frozen=True)
class InstitutionalMvpCalendarEvidence:
    schema_version: str
    timezone: str
    coverage_start: date
    coverage_end: date
    source_digest: str
    scope: str

    def __post_init__(self) -> None:
        _text(self.schema_version, "calendar schema_version")
        _text(self.timezone, "calendar timezone")
        _sha256(self.source_digest, "calendar source_digest")
        _text(self.scope, "calendar scope")
        if self.coverage_end < self.coverage_start:
            raise ValueError("calendar coverage is invalid")
        if self.schema_version != "twse_calendar_2026_v1":
            raise ValueError("calendar schema differs from daily MVP contract")
        if self.timezone != "Asia/Taipei":
            raise ValueError("calendar timezone differs from daily MVP contract")
        if self.scope != "TWSE_REVIEWED_PROXY_FOR_CURRENT_TWSE_TPEX_MVP":
            raise ValueError("calendar scope differs from daily MVP contract")

    def to_dict(self) -> dict[str, object]:
        return {
            "coverage_end": self.coverage_end,
            "coverage_start": self.coverage_start,
            "schema_version": self.schema_version,
            "scope": self.scope,
            "source_digest": self.source_digest,
            "timezone": self.timezone,
        }


@dataclass(frozen=True)
class InstitutionalMvpSourceEvidence:
    provider: str
    source_version: str
    retrieved_at: datetime
    flow_raw_sha256: str
    stock_info_raw_sha256: str
    stock_info_source_rows: int
    flow_source_rows: int
    mapped_flow_rows: int
    unmapped_flow_rows: int
    candidate_count_before_limit: int
    published_candidate_count: int
    usage_user_count_before: int
    usage_request_limit: int
    usage_remaining_before: int

    def __post_init__(self) -> None:
        _text(self.provider, "provider")
        _text(self.source_version, "source_version")
        if self.provider != "FINMIND" or self.source_version != "FINMIND_API_V4":
            raise ValueError("source provider contract drifted")
        _aware(self.retrieved_at, "retrieved_at")
        _sha256(self.flow_raw_sha256, "flow_raw_sha256")
        _sha256(self.stock_info_raw_sha256, "stock_info_raw_sha256")
        counts = (
            self.flow_source_rows,
            self.mapped_flow_rows,
            self.unmapped_flow_rows,
            self.candidate_count_before_limit,
            self.published_candidate_count,
            self.stock_info_source_rows,
            self.usage_user_count_before,
            self.usage_request_limit,
            self.usage_remaining_before,
        )
        if any(isinstance(item, bool) or item < 0 for item in counts):
            raise ValueError("source evidence counts must be non-negative integers")
        if self.flow_source_rows != self.mapped_flow_rows + self.unmapped_flow_rows:
            raise ValueError("flow source rows must equal mapped plus unmapped rows")
        if self.candidate_count_before_limit < self.published_candidate_count:
            raise ValueError("published candidates exceed candidates before limit")
        if self.candidate_count_before_limit > self.mapped_flow_rows:
            raise ValueError("candidate count exceeds mapped flow rows")
        if self.usage_request_limit <= 0:
            raise ValueError("usage_request_limit must be positive")
        if self.stock_info_source_rows <= 0:
            raise ValueError("stock_info_source_rows must be positive")
        if self.usage_remaining_before != max(
            0, self.usage_request_limit - self.usage_user_count_before
        ):
            raise ValueError("usage remaining does not match provider counts")

    def to_dict(self) -> dict[str, object]:
        return {
            "candidate_count_before_limit": self.candidate_count_before_limit,
            "flow_raw_sha256": self.flow_raw_sha256,
            "flow_source_rows": self.flow_source_rows,
            "mapped_flow_rows": self.mapped_flow_rows,
            "provider": self.provider,
            "published_candidate_count": self.published_candidate_count,
            "retrieved_at": self.retrieved_at,
            "source_version": self.source_version,
            "stock_info_raw_sha256": self.stock_info_raw_sha256,
            "stock_info_source_rows": self.stock_info_source_rows,
            "unmapped_flow_rows": self.unmapped_flow_rows,
            "usage": {
                "api_request_limit": self.usage_request_limit,
                "remaining_before": self.usage_remaining_before,
                "user_count_before": self.usage_user_count_before,
            },
        }


@dataclass(frozen=True)
class InstitutionalMvpCandidateEntry:
    rank: int
    symbol: str
    name: str
    market: str
    source_session: date
    target_session: date
    expires_at: datetime
    entry_digest: str

    @classmethod
    def create(
        cls,
        *,
        rank: int,
        symbol: str,
        name: str,
        market: str,
        source_session: date,
        target_session: date,
        expires_at: datetime,
    ) -> "InstitutionalMvpCandidateEntry":
        body = _candidate_entry_body(
            rank=rank,
            symbol=symbol,
            name=name,
            market=market,
            source_session=source_session,
            target_session=target_session,
            expires_at=expires_at,
        )
        return cls(**body, entry_digest=sha256_text(canonical_json(body)))

    def __post_init__(self) -> None:
        if isinstance(self.rank, bool) or self.rank <= 0:
            raise ValueError("candidate rank must be positive")
        for value, name in (
            (self.symbol, "symbol"),
            (self.name, "name"),
            (self.market, "market"),
        ):
            _text(value, name)
        if self.market not in {"TWSE", "TPEX"}:
            raise ValueError("candidate market must be TWSE or TPEX")
        if self.target_session <= self.source_session:
            raise ValueError("target_session must follow source_session")
        _aware(self.expires_at, "expires_at")
        if self.expires_at.date() != self.target_session:
            raise ValueError("candidate expiry must fall on target_session")
        _taipei_expiry(self.expires_at, "candidate expires_at")
        expected = sha256_text(canonical_json(self.body()))
        if self.entry_digest != expected:
            raise ValueError("candidate entry digest mismatch")

    def body(self) -> dict[str, object]:
        return _candidate_entry_body(
            rank=self.rank,
            symbol=self.symbol,
            name=self.name,
            market=self.market,
            source_session=self.source_session,
            target_session=self.target_session,
            expires_at=self.expires_at,
        )

    def to_dict(self) -> dict[str, object]:
        return {**self.body(), "entry_digest": self.entry_digest}


@dataclass(frozen=True)
class InstitutionalMvpCandidateBatchV1:
    source_session: date
    target_session: date
    generated_at: datetime
    expires_at: datetime
    source_fingerprint: str
    policy: InstitutionalMvpDailyPolicy
    calendar: InstitutionalMvpCalendarEvidence
    source: InstitutionalMvpSourceEvidence
    candidates: tuple[InstitutionalMvpCandidateEntry, ...]

    def __post_init__(self) -> None:
        if self.target_session <= self.source_session:
            raise ValueError("target_session must follow source_session")
        _aware(self.generated_at, "generated_at")
        _aware(self.expires_at, "expires_at")
        if self.expires_at.date() != self.target_session:
            raise ValueError("batch expiry must fall on target_session")
        _taipei_expiry(self.expires_at, "batch expires_at")
        _sha256(self.source_fingerprint, "source_fingerprint")
        if tuple(item.rank for item in self.candidates) != tuple(
            range(1, len(self.candidates) + 1)
        ):
            raise ValueError("candidate ranks must be contiguous")
        if len({item.symbol for item in self.candidates}) != len(self.candidates):
            raise ValueError("candidate symbols must be unique")
        if any(
            item.source_session != self.source_session
            or item.target_session != self.target_session
            or item.expires_at != self.expires_at
            for item in self.candidates
        ):
            raise ValueError("candidate session binding differs from batch")
        if self.source.published_candidate_count != len(self.candidates):
            raise ValueError("published candidate count differs from batch")
        if self.source.published_candidate_count != min(
            self.source.candidate_count_before_limit,
            self.policy.candidate_limit,
        ):
            raise ValueError("published candidates differ from complete policy projection")
        expected_fingerprint = source_fingerprint(
            source_session=self.source_session,
            target_session=self.target_session,
            policy_digest=self.policy.canonical_sha256,
            calendar_digest=self.calendar.source_digest,
            provider=self.source.provider,
            source_version=self.source.source_version,
            flow_raw_sha256=self.source.flow_raw_sha256,
            stock_info_raw_sha256=self.source.stock_info_raw_sha256,
        )
        if self.source_fingerprint != expected_fingerprint:
            raise ValueError("source_fingerprint mismatch")

    def identity_body(self) -> dict[str, object]:
        return {
            "calendar_evidence": self.calendar.to_dict(),
            "candidate_observation": {
                "candidates": [item.to_dict() for item in self.candidates],
                "count": len(self.candidates),
            },
            "candidate_policy": self.policy.to_dict(),
            "change_policy": CHANGE_POLICY,
            "evidence_scope": {
                "backtest_or_holdout_read": False,
                "institutional_flow_fields_read": True,
                "price_or_kbar_read": False,
                "provider_call_performed": True,
                "return_or_pnl_read": False,
            },
            "execution_permissions": dict(self.policy.execution_permissions),
            "expires_at": self.expires_at,
            "generated_at": self.generated_at,
            "limitations": list(self.policy.limitations),
            "research_eligibility": {
                "formal_pit_eligible": False,
                "research_eligible": False,
            },
            "schema_version": BATCH_SCHEMA_VERSION,
            "source_evidence": self.source.to_dict(),
            "source_fingerprint": self.source_fingerprint,
            "source_session": self.source_session,
            "status": BATCH_STATUS,
            "target_session": self.target_session,
        }

    @property
    def artifact_digest(self) -> str:
        return sha256_text(canonical_json(self.identity_body()))

    @property
    def artifact_id(self) -> str:
        return (
            "finmind-institutional-mvp-batch-v1-"
            f"{self.target_session.isoformat()}-{self.artifact_digest[:16]}"
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "artifact_digest": self.artifact_digest,
            "artifact_id": self.artifact_id,
            **self.identity_body(),
        }


def source_fingerprint(
    *,
    source_session: date,
    target_session: date,
    policy_digest: str,
    calendar_digest: str,
    provider: str,
    source_version: str,
    flow_raw_sha256: str,
    stock_info_raw_sha256: str,
) -> str:
    return sha256_text(
        canonical_json(
            {
                "calendar_digest": calendar_digest,
                "flow_raw_sha256": flow_raw_sha256,
                "policy_digest": policy_digest,
                "provider": provider,
                "source_session": source_session,
                "source_version": source_version,
                "stock_info_raw_sha256": stock_info_raw_sha256,
                "target_session": target_session,
            }
        )
    )


def verify_candidate_batch_payload(
    payload: Mapping[str, Any],
    *,
    next_session_resolver: Callable[[date], date],
    expected_policy_digest: str | None = None,
    expected_base_policy_digest: str | None = None,
    expected_calendar_digest: str | None = None,
) -> None:
    """Verify canonical identity plus the complete observation-only contract."""
    required = {
        "artifact_digest",
        "artifact_id",
        "calendar_evidence",
        "candidate_observation",
        "candidate_policy",
        "change_policy",
        "evidence_scope",
        "execution_permissions",
        "expires_at",
        "generated_at",
        "limitations",
        "research_eligibility",
        "schema_version",
        "source_evidence",
        "source_fingerprint",
        "source_session",
        "status",
        "target_session",
    }
    if set(payload) != required:
        raise ValueError("candidate batch fields differ from schema")
    if payload["schema_version"] != BATCH_SCHEMA_VERSION:
        raise ValueError("unsupported candidate batch schema")
    if payload["status"] != BATCH_STATUS:
        raise ValueError("candidate batch status is not observation-only")
    if payload["change_policy"] != CHANGE_POLICY:
        raise ValueError("candidate batch change policy drifted")
    identity = dict(payload)
    observed_digest = _sha256(identity.pop("artifact_digest"), "artifact_digest")
    observed_id = _text(identity.pop("artifact_id"), "artifact_id")
    expected_digest = sha256_text(canonical_json(identity))
    if observed_digest != expected_digest:
        raise ValueError("candidate batch artifact digest mismatch")
    source_session = date.fromisoformat(
        _text(payload["source_session"], "source_session")
    )
    target_session = date.fromisoformat(
        _text(payload["target_session"], "target_session")
    )
    if target_session <= source_session:
        raise ValueError("candidate batch target_session must follow source_session")
    try:
        reviewed_target_session = next_session_resolver(source_session)
    except ValueError as error:
        raise ValueError("candidate source session is unavailable in reviewed calendar") from error
    if target_session != reviewed_target_session:
        raise ValueError("candidate target_session differs from reviewed next session")
    generated_at = _datetime_value(payload["generated_at"], "generated_at")
    expires_at = _datetime_value(payload["expires_at"], "expires_at")
    if expires_at.date() != target_session:
        raise ValueError("candidate batch expiry must fall on target_session")
    _taipei_expiry(expires_at, "candidate batch expires_at")
    del generated_at
    expected_id = (
        "finmind-institutional-mvp-batch-v1-"
        f"{target_session.isoformat()}-{expected_digest[:16]}"
    )
    if observed_id != expected_id:
        raise ValueError("candidate batch artifact id mismatch")

    policy = _mapping(payload["candidate_policy"], "candidate_policy")
    _exact_fields(
        policy,
        {
            "artifact_id",
            "base_policy_reference",
            "candidate_limit",
            "candidate_rule",
            "canonical_sha256",
            "dealer_total_net_formula",
            "execution_permissions",
            "limitations",
            "market_mapping",
            "rank_rule",
            "schema_version",
            "session_binding",
        },
        "candidate_policy",
    )
    policy_body = dict(policy)
    policy_digest = _sha256(
        policy_body.pop("canonical_sha256", None), "candidate policy digest"
    )
    if sha256_text(canonical_json(policy_body)) != policy_digest:
        raise ValueError("candidate policy digest mismatch")
    if expected_policy_digest is not None and policy_digest != _sha256(
        expected_policy_digest, "expected policy digest"
    ):
        raise ValueError("candidate policy does not match reviewed daily policy")
    if policy["schema_version"] != "institutional_mvp_daily_candidate_policy_v1":
        raise ValueError("candidate policy schema drifted")
    if policy["session_binding"] != (
        "EXPLICIT_SOURCE_SESSION_TO_REVIEWED_NEXT_EQUITY_SESSION_V1"
    ):
        raise ValueError("candidate policy session binding drifted")
    if policy["market_mapping"] != (
        "LATEST_TAIWAN_STOCK_INFO_ROW_PER_SYMBOL;_CURRENT_MAPPING_ONLY"
    ):
        raise ValueError("candidate policy market mapping drifted")
    candidate_limit = _positive_integer(policy["candidate_limit"], "candidate_limit")

    base_reference = _mapping(
        policy["base_policy_reference"], "base_policy_reference"
    )
    _exact_fields(
        base_reference,
        {"artifact_id", "canonical_sha256"},
        "base_policy_reference",
    )
    _text(base_reference["artifact_id"], "base policy artifact_id")
    base_digest = _sha256(
        base_reference["canonical_sha256"], "base policy digest"
    )
    if expected_base_policy_digest is not None and base_digest != _sha256(
        expected_base_policy_digest, "expected base policy digest"
    ):
        raise ValueError("candidate policy base lineage drifted")

    policy_permissions = _boolean_mapping(
        policy["execution_permissions"], "candidate policy permissions"
    )
    if policy_permissions.get("mvp_candidate_observation_allowed") is not True:
        raise ValueError("candidate observation permission is not enabled")
    if any(
        value is not False
        for name, value in policy_permissions.items()
        if name != "mvp_candidate_observation_allowed"
    ):
        raise ValueError("candidate policy grants non-observation authority")
    top_permissions = _boolean_mapping(
        payload["execution_permissions"], "execution_permissions"
    )
    if top_permissions != policy_permissions:
        raise ValueError("candidate batch permissions differ from policy")

    policy_limitations = _string_list(policy["limitations"], "policy limitations")
    top_limitations = _string_list(payload["limitations"], "limitations")
    if top_limitations != policy_limitations:
        raise ValueError("candidate batch limitations differ from policy")
    required_limitations = {
        "CURRENT_MARKET_MAPPING_CAN_HAVE_SURVIVORSHIP_AND_TRANSFER_BIAS",
        "NO_ORDER_OR_PRODUCTION_STRATEGY_AUTHORITY",
        "NO_PRICE_COVERAGE_OR_RETURN_EVIDENCE",
        "TWSE_CALENDAR_IS_OPERATIONAL_PROXY_FOR_CURRENT_TWSE_TPEX_MVP",
    }
    if not required_limitations.issubset(policy_limitations):
        raise ValueError("candidate batch required MVP limitations are missing")

    if _mapping(payload["research_eligibility"], "research_eligibility") != {
        "formal_pit_eligible": False,
        "research_eligible": False,
    }:
        raise ValueError("candidate batch research eligibility drifted")
    if _mapping(payload["evidence_scope"], "evidence_scope") != {
        "backtest_or_holdout_read": False,
        "institutional_flow_fields_read": True,
        "price_or_kbar_read": False,
        "provider_call_performed": True,
        "return_or_pnl_read": False,
    }:
        raise ValueError("candidate batch evidence scope drifted")

    observation = _mapping(payload["candidate_observation"], "candidate_observation")
    _exact_fields(observation, {"candidates", "count"}, "candidate_observation")
    candidates = observation.get("candidates")
    if not isinstance(candidates, list):
        raise ValueError("candidate observation candidates must be a list")
    count = _nonnegative_integer(observation["count"], "candidate count")
    if count != len(candidates):
        raise ValueError("candidate observation count differs from candidate list")
    if count > candidate_limit:
        raise ValueError("candidate observation exceeds policy limit")
    ranks: list[int] = []
    symbols: list[str] = []
    for candidate in candidates:
        candidate_map = _mapping(candidate, "candidate")
        _exact_fields(
            candidate_map,
            {
                "entry_digest",
                "expires_at",
                "market",
                "name",
                "rank",
                "source_session",
                "symbol",
                "target_session",
            },
            "candidate",
        )
        body = dict(candidate_map)
        digest = _sha256(body.pop("entry_digest", None), "entry_digest")
        if sha256_text(canonical_json(body)) != digest:
            raise ValueError("candidate entry digest mismatch")
        rank = _positive_integer(candidate_map["rank"], "candidate rank")
        symbol = _text(candidate_map["symbol"], "candidate symbol")
        _text(candidate_map["name"], "candidate name")
        if candidate_map["market"] not in {"TWSE", "TPEX"}:
            raise ValueError("candidate market must be TWSE or TPEX")
        if candidate_map["source_session"] != source_session.isoformat():
            raise ValueError("candidate source session differs from batch")
        if candidate_map["target_session"] != target_session.isoformat():
            raise ValueError("candidate target session differs from batch")
        if candidate_map["expires_at"] != expires_at.isoformat():
            raise ValueError("candidate expiry differs from batch")
        ranks.append(rank)
        symbols.append(symbol)
    if ranks != list(range(1, count + 1)):
        raise ValueError("candidate ranks must be contiguous")
    if len(set(symbols)) != len(symbols):
        raise ValueError("candidate symbols must be unique")

    calendar = _mapping(payload["calendar_evidence"], "calendar_evidence")
    _exact_fields(
        calendar,
        {
            "coverage_end",
            "coverage_start",
            "schema_version",
            "scope",
            "source_digest",
            "timezone",
        },
        "calendar_evidence",
    )
    calendar_digest = _sha256(calendar["source_digest"], "calendar digest")
    if expected_calendar_digest is not None and calendar_digest != _sha256(
        expected_calendar_digest, "expected calendar digest"
    ):
        raise ValueError("candidate batch calendar lineage drifted")
    if calendar["timezone"] != "Asia/Taipei":
        raise ValueError("candidate batch calendar timezone drifted")
    if calendar["schema_version"] != "twse_calendar_2026_v1":
        raise ValueError("candidate batch calendar schema drifted")
    if calendar["scope"] != "TWSE_REVIEWED_PROXY_FOR_CURRENT_TWSE_TPEX_MVP":
        raise ValueError("candidate batch calendar scope drifted")
    coverage_start = date.fromisoformat(
        _text(calendar["coverage_start"], "calendar coverage_start")
    )
    coverage_end = date.fromisoformat(
        _text(calendar["coverage_end"], "calendar coverage_end")
    )
    if not coverage_start <= source_session < target_session <= coverage_end:
        raise ValueError("candidate sessions fall outside calendar coverage")

    source = _mapping(payload["source_evidence"], "source_evidence")
    _exact_fields(
        source,
        {
            "candidate_count_before_limit",
            "flow_raw_sha256",
            "flow_source_rows",
            "mapped_flow_rows",
            "provider",
            "published_candidate_count",
            "retrieved_at",
            "source_version",
            "stock_info_raw_sha256",
            "stock_info_source_rows",
            "unmapped_flow_rows",
            "usage",
        },
        "source_evidence",
    )
    _datetime_value(source["retrieved_at"], "source retrieved_at")
    _positive_integer(source["stock_info_source_rows"], "stock_info_source_rows")
    flow_source_rows = _nonnegative_integer(
        source["flow_source_rows"], "flow_source_rows"
    )
    mapped_rows = _positive_integer(source["mapped_flow_rows"], "mapped_flow_rows")
    unmapped_rows = _nonnegative_integer(
        source["unmapped_flow_rows"], "unmapped_flow_rows"
    )
    if flow_source_rows != mapped_rows + unmapped_rows:
        raise ValueError("source row counts are inconsistent")
    candidate_count_before_limit = _nonnegative_integer(
        source["candidate_count_before_limit"], "candidate_count_before_limit"
    )
    published_count = _nonnegative_integer(
        source["published_candidate_count"], "published_candidate_count"
    )
    if (
        published_count != count
        or candidate_count_before_limit < published_count
        or candidate_count_before_limit > mapped_rows
    ):
        raise ValueError("source candidate counts are inconsistent")
    if published_count != min(candidate_count_before_limit, candidate_limit):
        raise ValueError(
            "published candidate count differs from complete policy projection"
        )
    usage = _mapping(source["usage"], "source usage")
    _exact_fields(
        usage,
        {"api_request_limit", "remaining_before", "user_count_before"},
        "source usage",
    )
    request_limit = _positive_integer(usage["api_request_limit"], "api_request_limit")
    user_count = _nonnegative_integer(usage["user_count_before"], "user_count_before")
    remaining = _nonnegative_integer(usage["remaining_before"], "remaining_before")
    if remaining != max(0, request_limit - user_count):
        raise ValueError("source usage counts are inconsistent")

    expected_fingerprint = source_fingerprint(
        source_session=source_session,
        target_session=target_session,
        policy_digest=policy_digest,
        calendar_digest=calendar_digest,
        provider=_expected_text(source.get("provider"), "provider", "FINMIND"),
        source_version=_expected_text(
            source.get("source_version"), "source_version", "FINMIND_API_V4"
        ),
        flow_raw_sha256=_sha256(source.get("flow_raw_sha256"), "flow digest"),
        stock_info_raw_sha256=_sha256(
            source.get("stock_info_raw_sha256"), "stock info digest"
        ),
    )
    if _sha256(payload["source_fingerprint"], "source_fingerprint") != expected_fingerprint:
        raise ValueError("candidate batch source fingerprint mismatch")


def _candidate_entry_body(
    *,
    rank: int,
    symbol: str,
    name: str,
    market: str,
    source_session: date,
    target_session: date,
    expires_at: datetime,
) -> dict[str, object]:
    return {
        "expires_at": expires_at,
        "market": market,
        "name": name,
        "rank": rank,
        "source_session": source_session,
        "symbol": symbol,
        "target_session": target_session,
    }


def _text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _expected_text(value: object, field_name: str, expected: str) -> str:
    observed = _text(value, field_name)
    if observed != expected:
        raise ValueError(f"{field_name} differs from expected contract")
    return observed


def _sha256(value: object, field_name: str) -> str:
    text = _text(value, field_name).lower()
    if len(text) != 64 or any(character not in "0123456789abcdef" for character in text):
        raise ValueError(f"{field_name} must be a SHA256 digest")
    return text


def _aware(value: datetime, field_name: str) -> None:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must be timezone-aware")


def _taipei_expiry(value: datetime, field_name: str) -> None:
    _aware(value, field_name)
    if value.utcoffset() != timedelta(hours=8):
        raise ValueError(f"{field_name} must use Asia/Taipei UTC+08:00")
    if (
        value.hour != 13
        or value.minute != 30
        or value.second != 0
        or value.microsecond != 0
    ):
        raise ValueError(f"{field_name} must be exactly 13:30:00")


def _mapping(value: object, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be an object")
    return value


def _exact_fields(
    value: Mapping[str, Any], expected: set[str], field_name: str
) -> None:
    if set(value) != expected:
        raise ValueError(f"{field_name} fields differ from schema")


def _datetime_value(value: object, field_name: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(_text(value, field_name))
    except ValueError as error:
        raise ValueError(f"{field_name} must be an ISO datetime") from error
    _aware(parsed, field_name)
    return parsed


def _nonnegative_integer(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field_name} must be a non-negative integer")
    return value


def _positive_integer(value: object, field_name: str) -> int:
    parsed = _nonnegative_integer(value, field_name)
    if parsed == 0:
        raise ValueError(f"{field_name} must be positive")
    return parsed


def _boolean_mapping(value: object, field_name: str) -> dict[str, bool]:
    mapping = _mapping(value, field_name)
    if not mapping or any(
        not isinstance(name, str) or not isinstance(item, bool)
        for name, item in mapping.items()
    ):
        raise ValueError(f"{field_name} must contain boolean values")
    return dict(mapping)


def _string_list(value: object, field_name: str) -> tuple[str, ...]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{field_name} must be a non-empty list")
    result = tuple(_text(item, field_name) for item in value)
    if len(set(result)) != len(result):
        raise ValueError(f"{field_name} values must be unique")
    return result
