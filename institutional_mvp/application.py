"""Application service for one explicit FinMind institutional MVP daily run."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from institutional_mvp.domain import (
    InstitutionalMvpCalendarEvidence,
    InstitutionalMvpCandidateBatchV1,
    InstitutionalMvpCandidateEntry,
    InstitutionalMvpDailyError,
    InstitutionalMvpDailyPolicy,
    InstitutionalMvpSourceEvidence,
    InstitutionalMvpSourceNotReady,
    source_fingerprint,
)
from institutional_mvp.finmind import (
    FinMindMvpSchemaError,
    finmind_mvp_row_count,
    parse_finmind_mvp_flows,
    select_three_way_buy_candidates,
)
from institutional_mvp.ports import (
    InstitutionalFlowProvider,
    InstitutionalMvpArtifactPublication,
    InstitutionalMvpCandidateBatchRepository,
    ReviewedEquitySessionCalendar,
)


TAIPEI = ZoneInfo("Asia/Taipei")
TARGET_SESSION_EXPIRY = time(13, 30)


class DailyInstitutionalMvpService:
    """Resolve T+1, fetch T data, normalize, rank, and publish one batch."""

    def __init__(
        self,
        *,
        provider: InstitutionalFlowProvider,
        repository: InstitutionalMvpCandidateBatchRepository,
        calendar: ReviewedEquitySessionCalendar,
        policy: InstitutionalMvpDailyPolicy,
        expected_calendar_schema_version: str,
        expected_calendar_timezone: str,
        expected_calendar_source_digest: str,
        calendar_scope: str,
        clock: Callable[[], datetime] = lambda: datetime.now().astimezone(),
    ) -> None:
        self._provider = provider
        self._repository = repository
        self._calendar = calendar
        self._policy = policy
        self._expected_calendar_schema_version = expected_calendar_schema_version
        self._expected_calendar_timezone = expected_calendar_timezone
        self._expected_calendar_source_digest = expected_calendar_source_digest
        self._calendar_scope = calendar_scope
        self._clock = clock

    def run(self, source_session: date) -> InstitutionalMvpArtifactPublication:
        target_session, calendar_evidence = self._resolve_target_before_provider_call(
            source_session
        )
        snapshot = self._provider.fetch_daily(source_session)
        try:
            observed_wide_rows = finmind_mvp_row_count(
                snapshot.wide_payload,
                "TaiwanStockInstitutionalInvestorsBuySellWide",
            )
            observed_stock_info_rows = finmind_mvp_row_count(
                snapshot.stock_info_payload,
                "TaiwanStockInfo",
            )
        except FinMindMvpSchemaError as error:
            raise InstitutionalMvpDailyError(
                "SOURCE_SCHEMA_INVALID", "FinMind source envelope is invalid"
            ) from error
        if (
            observed_wide_rows != snapshot.wide_row_count
            or observed_stock_info_rows != snapshot.stock_info_row_count
        ):
            raise InstitutionalMvpDailyError(
                "SOURCE_METADATA_MISMATCH",
                "Provider snapshot row counts do not match raw response bodies",
            )
        if observed_wide_rows == 0:
            raise InstitutionalMvpSourceNotReady()
        if observed_stock_info_rows == 0:
            raise InstitutionalMvpDailyError(
                "STOCK_INFO_MAPPING_UNAVAILABLE",
                "FinMind current stock mapping is empty",
            )

        try:
            flows = parse_finmind_mvp_flows(
                wide_payload=snapshot.wide_payload,
                stock_info_payload=snapshot.stock_info_payload,
                session_date=source_session,
                usable_from_session=target_session,
            )
        except FinMindMvpSchemaError as error:
            raise InstitutionalMvpDailyError(
                "SOURCE_SCHEMA_INVALID", "FinMind institutional payload is invalid"
            ) from error
        if not flows:
            raise InstitutionalMvpDailyError(
                "STOCK_INFO_MAPPING_UNAVAILABLE",
                "No institutional rows map to current TWSE/TPEx identities",
            )

        all_candidates = select_three_way_buy_candidates(flows)
        selected = select_three_way_buy_candidates(
            flows, limit=self._policy.candidate_limit
        )
        expires_at = datetime.combine(
            target_session, TARGET_SESSION_EXPIRY, tzinfo=TAIPEI
        )
        entries = tuple(
            InstitutionalMvpCandidateEntry.create(
                rank=candidate.rank,
                symbol=candidate.symbol,
                name=candidate.name,
                market=candidate.market,
                source_session=source_session,
                target_session=target_session,
                expires_at=expires_at,
            )
            for candidate in selected
        )
        flow_digest = hashlib.sha256(snapshot.wide_payload).hexdigest()
        stock_info_digest = hashlib.sha256(snapshot.stock_info_payload).hexdigest()
        source_evidence = InstitutionalMvpSourceEvidence(
            provider=snapshot.provider,
            source_version=snapshot.source_version,
            retrieved_at=snapshot.retrieved_at,
            flow_raw_sha256=flow_digest,
            stock_info_raw_sha256=stock_info_digest,
            stock_info_source_rows=observed_stock_info_rows,
            flow_source_rows=observed_wide_rows,
            mapped_flow_rows=len(flows),
            unmapped_flow_rows=observed_wide_rows - len(flows),
            candidate_count_before_limit=len(all_candidates),
            published_candidate_count=len(entries),
            usage_user_count_before=snapshot.usage_user_count_before,
            usage_request_limit=snapshot.usage_request_limit,
            usage_remaining_before=snapshot.usage_remaining_before,
        )
        fingerprint = source_fingerprint(
            source_session=source_session,
            target_session=target_session,
            policy_digest=self._policy.canonical_sha256,
            calendar_digest=calendar_evidence.source_digest,
            provider=snapshot.provider,
            source_version=snapshot.source_version,
            flow_raw_sha256=flow_digest,
            stock_info_raw_sha256=stock_info_digest,
        )
        generated_at = self._clock()
        if generated_at.tzinfo is None or generated_at.utcoffset() is None:
            raise ValueError("application clock must return a timezone-aware datetime")
        batch = InstitutionalMvpCandidateBatchV1(
            source_session=source_session,
            target_session=target_session,
            generated_at=generated_at,
            expires_at=expires_at,
            source_fingerprint=fingerprint,
            policy=self._policy,
            calendar=calendar_evidence,
            source=source_evidence,
            candidates=entries,
        )
        return self._repository.put_immutable(batch)

    def _resolve_target_before_provider_call(
        self, source_session: date
    ) -> tuple[date, InstitutionalMvpCalendarEvidence]:
        if self._calendar.schema_version != self._expected_calendar_schema_version:
            raise InstitutionalMvpDailyError(
                "CALENDAR_CONTRACT_DRIFT", "Reviewed equity calendar schema drifted"
            )
        if self._calendar.timezone != self._expected_calendar_timezone:
            raise InstitutionalMvpDailyError(
                "CALENDAR_CONTRACT_DRIFT", "Reviewed equity calendar timezone drifted"
            )
        if self._calendar.source_digest != self._expected_calendar_source_digest:
            raise InstitutionalMvpDailyError(
                "CALENDAR_CONTRACT_DRIFT", "Reviewed equity calendar digest drifted"
            )
        try:
            evidence = InstitutionalMvpCalendarEvidence(
                schema_version=self._calendar.schema_version,
                timezone=self._calendar.timezone,
                coverage_start=self._calendar.coverage_start,
                coverage_end=self._calendar.coverage_end,
                source_digest=self._calendar.source_digest,
                scope=self._calendar_scope,
            )
        except ValueError as error:
            raise InstitutionalMvpDailyError(
                "CALENDAR_CONTRACT_DRIFT", "Reviewed equity calendar contract drifted"
            ) from error
        try:
            target_session = self._calendar.next_trading_day(source_session)
        except ValueError as error:
            raise InstitutionalMvpDailyError(
                "CALENDAR_SESSION_UNAVAILABLE",
                "Source or next equity session is not covered by reviewed calendar",
            ) from error
        return target_session, evidence
